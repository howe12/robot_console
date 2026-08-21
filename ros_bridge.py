"""ROS2 桥接：相机 MJPEG 推流 + /cmd_vel 发布。

设计：
  - /api/camera/stream 支持 query 参数 topic / width / quality / fps
  - 每个 HTTP 流请求创建独立 StreamContext（独立订阅、参数）
  - 支持多个浏览器同时看不同话题
  - /api/ros/image_topics 列出所有 sensor_msgs/Image 话题
"""
import threading
import time

import subprocess
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
    import numpy as np
    ros_available = True
except Exception as _e:
    ros_import_error = str(_e)
    print("[ros_bridge] ROS2 不可用：", ros_import_error)

CMD_TOPIC = "cmd_vel"
DEFAULT_TOPIC = "camera/color/image_raw"
DEFAULT_WIDTH = 640
DEFAULT_QUALITY = 80
DEFAULT_FPS = 15


_shared_node = None
_shared_executor = None
_shared_spin_thread = None
_node_lock = threading.Lock()


def _get_shared_node():
    """全局共享 rclpy 节点（所有 StreamContext 复用，避免每个流创建独立 node 的 rclpy context 冲突）"""
    global _shared_node, _shared_executor, _shared_spin_thread
    with _node_lock:
        if _shared_node is not None:
            return _shared_node
        if not rclpy.ok():
            rclpy.init()
        _shared_node = rclpy.create_node("spark_console_shared")
        _shared_executor = rclpy.executors.SingleThreadedExecutor()
        _shared_executor.add_node(_shared_node)
        _shared_spin_thread = threading.Thread(target=_shared_spin_loop, daemon=True)
        _shared_spin_thread.start()
        return _shared_node


def _shared_spin_loop():
    while rclpy.ok() and _shared_node is not None:
        try:
            _shared_executor.spin_once(timeout_sec=0.05)
        except Exception:
            break


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
            # rclpy.init() 整个进程只能调一次
            if not rclpy.ok():
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
            self._node = _get_shared_node()
            self._sub = self._node.create_subscription(
                Image, self.topic, self._on_image,
                QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
            print(f"[stream] 启动: {self.topic} {self.width}p {self.fps}fps q{self.quality}")
            return True
        except Exception as e:
            print(f"[stream] 启动失败: {e}")
            return False

    def _on_image(self, msg):
        now = time.monotonic()
        if now - self._last_enc < 1.0 / self.fps: return
        try:
            w, h = msg.width, msg.height
            # 用 numpy 从 raw bytes 解码（cv_bridge 不支持 16UC1/32FC1）
            # ROS image data 是 row-major，msg.data 是 bytes
            dtype_map = {
                "rgb8": (np.uint8, 3), "bgr8": (np.uint8, 3),
                "rgba8": (np.uint8, 4), "bgra8": (np.uint8, 4),
                "mono8": (np.uint8, 1), "8uc1": (np.uint8, 1),
                "mono16": (np.uint16, 1), "16uc1": (np.uint16, 1),
                "32fc1": (np.float32, 1),
            }
            enc = msg.encoding.lower()
            if enc not in dtype_map:
                # 只打印一次不重复刷屏
                _logged = getattr(StreamContext, '_logged_encs', set())
                if enc not in _logged:
                    _logged.add(enc)
                    StreamContext._logged_encs = _logged
                    print(f"[on_image] unsupported encoding: {enc}", flush=True)
                return
            dtype, ch = dtype_map[enc]
            arr = np.frombuffer(msg.data, dtype=dtype).reshape((h, w, ch)) if ch > 1 else np.frombuffer(msg.data, dtype=dtype).reshape((h, w))
            # 转成 bgr 图像用于 JPEG 编码
            if enc in ("bgr8",):
                bgr = arr
            elif enc in ("rgb8",):
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            elif enc in ("rgba8",):
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            elif enc in ("bgra8",):
                bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            elif enc in ("mono8", "8uc1", "mono16"):
                # 8/16 位灰度：归一化到 0-255
                if arr.dtype != np.uint8:
                    arr = (arr / 256).astype(np.uint8)
                bgr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            elif enc == "16uc1":
                # 深度图：用 99 百分位做 max，0 映射到白色（无效区）
                valid = arr[arr > 0]
                if valid.size == 0:
                    return  # 无有效数据
                max_v = float(np.percentile(valid, 99)) or 1.0
                gray = np.clip(arr.astype(np.float32) / max_v * 255, 0, 255).astype(np.uint8)
                gray[arr == 0] = 255
                bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            elif enc == "32fc1":
                valid = arr[(arr > 0) & np.isfinite(arr)]
                if valid.size == 0:
                    return
                max_v = float(np.percentile(valid, 99)) or 1.0
                norm = np.clip(arr / max_v, 0, 1)
                gray = (norm * 255).astype(np.uint8)
                gray[~np.isfinite(arr) | (arr == 0)] = 255
                bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            else:
                return
            h2, w2 = bgr.shape[:2]
            if w2 > self.width:
                nh = int(h2 * self.width / w2)
                bgr = cv2.resize(bgr, (self.width, nh), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
            if ok:
                self._last_enc = now
                with self._lock:
                    self._latest = (jpg.tobytes(), time.time_ns())
        except Exception as e:
            # 只打印第一次同类型错误，避免日志刷屏
            _key = (self.topic, type(e).__name__)
            _err = getattr(StreamContext, '_logged_errs', set())
            if _key not in _err:
                _err.add(_key)
                StreamContext._logged_errs = _err
                print(f"[on_image ERROR] {self.topic} enc={msg.encoding} {type(e).__name__}: {e}", flush=True)

    def latest_frame(self):
        with self._lock:
            return self._latest

    def stop(self):
        # 共享 node 不 destroy，只是把 self._node 置空
        self._node = None
        # 不 shutdown rclpy


def list_image_topics() -> list:
    """列出 ROS 图中所有 sensor_msgs/Image 话题。

    不用 rclpy 直接调用（init/shutdown 会影响同进程其他 rclpy 节点），
    直接 subprocess 跑 'ros2 topic list -t' 更安全。
    """
    if not ros_available: return []
    out = []
    try:
        r = subprocess.run(
            ['ros2', 'topic', 'list', '-t'],
            capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if '[' in line and ']' in line and 'Image' in line:
                name = line.split('[')[0].strip()
                typ = line.split('[')[1].rstrip(']').strip()
                out.append({"name": name, "types": [typ]})
    except Exception as e:
        print(f"[list_image_topics] 失败: {e}")
    return sorted(out, key=lambda x: x["name"])


def get_bridge():
    """返回 /cmd_vel 发布器单例（供 main.py 兼容）"""
    return _TwistPublisher.get()

def publish_twist(linear: float, angular: float) -> bool:
    return _TwistPublisher.get().publish(linear, angular)
