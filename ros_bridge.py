"""ROS2 桥接：相机 MJPEG 推流 + /cmd_vel 发布。

设计：
  - /api/camera/stream 支持 query 参数 topic / width / quality / fps
  - 每个 HTTP 流请求创建独立 StreamContext（独立订阅、参数）
  - 支持多个浏览器同时看不同话题
  - /api/ros/image_topics 列出所有 sensor_msgs/Image 话题
"""
import threading
import time

# ---- 防御式导入 ----
ros_available = False
Image = Twist = CvBridge = None
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import Image
    from geometry_msgs.msg import Twist
    from cv_bridge import CvBridge
    import cv2
    ros_available = True
except Exception as _e:
    ros_import_error = str(_e)
    print("[ros_bridge] ROS2 不可用：", ros_import_error)

CMD_TOPIC = "cmd_vel"
DEFAULT_TOPIC = "camera/color/image_raw"
DEFAULT_WIDTH = 640
DEFAULT_QUALITY = 80
DEFAULT_FPS = 15


class _TwistPublisher:
    """全局单例：/cmd_vel 发布器（多个浏览器共享一个发布器）"""
    _instance = None
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._node = None
        self._executor = None
        self._spin_thread = None
        self._pub = None
        self._lock = threading.Lock()

    def ensure_started(self):
        if not ros_available: return False
        if self._node is not None: return True
        try:
            rclpy.init()
            self._node = Node("spark_console_twist_pub")
            self._pub = self._node.create_publisher(Twist, CMD_TOPIC, 10)
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._spin_thread = threading.Thread(target=self._spin, daemon=True)
            self._spin_thread.start()
            return True
        except Exception as e:
            print("[twist_pub] 启动失败:", e)
            return False

    def _spin(self):
        while rclpy.ok() and self._node is not None:
            try: self._executor.spin_once(timeout_sec=0.05)
            except: break

    def publish(self, linear, angular):
        if not self.ensure_started() or self._pub is None: return False
        t = Twist(); t.linear.x = float(linear); t.angular.z = float(angular)
        self._pub.publish(t); return True


class StreamContext:
    """一个 MJPEG 流订阅的独立上下文（自己的节点、订阅、最新帧缓存）"""
    def __init__(self, topic, width, quality, fps):
        self.topic = topic
        self.width = int(width)
        self.quality = int(quality)
        self.fps = int(fps)
        self._node = None
        self._executor = None
        self._spin_thread = None
        self._sub = None
        self._bridge = CvBridge() if ros_available else None
        self._lock = threading.Lock()
        self._latest = None
        self._last_enc = 0.0
        self._last_seq = 0  # 用于去重

    def start(self):
        if not ros_available: return False
        try:
            rclpy.init()
            self._node = Node(f"spark_cam_{self._last_seq}_{self.topic.replace('/','_')}")
            self._sub = self._node.create_subscription(
                Image, self.topic, self._on_image,
                QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._spin_thread = threading.Thread(target=self._spin, daemon=True)
            self._spin_thread.start()
            print(f"[stream] 启动: {self.topic} {self.width}p {self.fps}fps q{self.quality}")
            return True
        except Exception as e:
            print(f"[stream] 启动失败: {e}")
            return False

    def _spin(self):
        while rclpy.ok() and self._node is not None:
            try: self._executor.spin_once(timeout_sec=0.05)
            except: break

    def _on_image(self, msg):
        now = time.monotonic()
        if now - self._last_enc < 1.0 / self.fps: return
        try:
            bgr = self._bridge.imgmsg_to_cv2(msg, "bgr8")
            h, w = bgr.shape[:2]
            if w > self.width:
                nh = int(h * self.width / w)
                bgr = cv2.resize(bgr, (self.width, nh), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
            if ok:
                self._last_enc = now
                with self._lock:
                    self._latest = (jpg.tobytes(), time.time_ns())
        except: pass

    def latest_frame(self):
        with self._lock:
            return self._latest

    def stop(self):
        node, self._node = self._node, None
        if node is not None:
            try: node.destroy_node()
            except: pass
        # 不 shutdown rclpy（可能有其他流在用）


def list_image_topics() -> list:
    """列出 ROS 图中所有 sensor_msgs/Image 话题"""
    if not ros_available: return []
    out = []
    try:
        # 短生命周期节点 + 单次 spin
        rclpy.init()
        node = Node("_spark_topic_lister_" + str(int(time.time()*1000)))
        # spin 一次
        topics_and_types = node.get_topic_names_and_types()
        for name, types in topics_and_types:
            type_names = [t.typename for t in types]
            if any('Image' in t for t in type_names):
                out.append({"name": name, "types": type_names})
        node.destroy_node()
        rclpy.shutdown()
    except Exception as e:
        print(f"[list_image_topics] 失败: {e}")
        # 备用：直接 ros2 topic list
        import subprocess
        try:
            r = subprocess.run(['ros2', 'topic', 'list', '-t'], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if '[' in line and ']' in line and 'Image' in line:
                    name = line.split('[')[0].strip()
                    typ = line.split('[')[1].rstrip(']').strip()
                    out.append({"name": name, "types": [typ]})
        except: pass
    return sorted(out, key=lambda x: x["name"])


def get_bridge():
    """返回 /cmd_vel 发布器单例（供 main.py 兼容）"""
    return _TwistPublisher.get()

def publish_twist(linear: float, angular: float) -> bool:
    return _TwistPublisher.get().publish(linear, angular)
