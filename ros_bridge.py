"""ROS2 桥接：相机 MJPEG 推流 + /cmd_vel 发布。

设计：
  - 惰性初始化：FastAPI 启动时不强制依赖 ROS2；调用方触发 ensure_started()。
  - 订阅 camera/color/image_raw → cv_bridge 转 BGR → resize 到 TARGET_WIDTH → JPEG 缓存最新帧。
  - publish_twist() 发布 geometry_msgs/Twist 到 /cmd_vel。
  - 独立 spin 线程（SingleThreadedExecutor），与 uvicorn 异步循环共存。

若当前进程未 source ROS2 环境（rclpy 导入失败），ros_available=False，
所有接口由调用方返回 503。
"""
import threading
import time

# ---- 防御式导入：没有 ROS2 环境时后端其余功能照常可用 ----
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
    import numpy as np  # noqa: F401  (cv_bridge 依赖)
    ros_available = True
except Exception as _e:  # noqa: BLE001
    ros_import_error = str(_e)
    print("[ros_bridge] ROS2 不可用，相机/遥控接口将返回 503:", ros_import_error)

IMAGE_TOPIC = "camera/color/image_raw"  # realsense D435 标准话题（spark 源码一致）
CMD_TOPIC = "cmd_vel"
TARGET_WIDTH = 640
JPEG_QUALITY = 80
MAX_FPS = 15  # 板载 CPU 上限，避免编解码吃满


class RosBridge:
    def __init__(self):
        self._node = None
        self._executor = None
        self._spin_thread = None
        self._pub = None
        self._lock = threading.Lock()
        self._latest = None  # (jpeg_bytes, stamp_ns)
        self._last_enc = 0.0

    @property
    def available(self) -> bool:
        return ros_available and self._node is not None

    def ensure_started(self) -> bool:
        """初始化 rclpy 节点并启动 spin 线程。幂等。"""
        if not ros_available:
            return False
        if self._node is not None:
            return True
        try:
            rclpy.init()
            self._node = Node("spark_console_bridge")
            self._pub = self._node.create_publisher(Twist, CMD_TOPIC, 10)
            self._sub = self._node.create_subscription(
                Image,
                IMAGE_TOPIC,
                self._on_image,
                QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._spin_thread = threading.Thread(target=self._spin, daemon=True)
            self._spin_thread.start()
            print("[ros_bridge] rclpy 节点已启动，订阅 %s，发布 %s" % (IMAGE_TOPIC, CMD_TOPIC))
            return True
        except Exception as e:  # noqa: BLE001
            print("[ros_bridge] 启动失败:", e)
            self.close()
            return False

    def _spin(self):
        while rclpy.ok() and self._node is not None:
            try:
                self._executor.spin_once(timeout_sec=0.05)
            except Exception:  # noqa: BLE001
                break

    def _on_image(self, msg):
        # 限帧率：MAX_FPS
        now = time.monotonic()
        if now - self._last_enc < 1.0 / MAX_FPS:
            return
        try:
            bgr = CvBridge().imgmsg_to_cv2(msg, "bgr8")
            h, w = bgr.shape[:2]
            if w > TARGET_WIDTH:
                nh = int(h * TARGET_WIDTH / w)
                bgr = cv2.resize(bgr, (TARGET_WIDTH, nh), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(
                ".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            )
            if ok:
                self._last_enc = now
                with self._lock:
                    self._latest = (jpg.tobytes(), msg.header.stamp.nanosec)
        except Exception:  # noqa: BLE001
            pass

    def latest_frame(self):
        """返回最新 JPEG 帧 (bytes, stamp_ns)，无帧时 None。"""
        with self._lock:
            return self._latest

    def publish_twist(self, linear: float, angular: float) -> bool:
        if self._pub is None:
            return False
        t = Twist()
        t.linear.x = float(linear)
        t.angular.z = float(angular)
        self._pub.publish(t)
        return True

    def close(self):
        node, self._node = self._node, None
        if node is not None:
            try:
                node.destroy_node()
            except Exception:  # noqa: BLE001
                pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except Exception:  # noqa: BLE001
                pass


_bridge = RosBridge()


def get_bridge() -> RosBridge:
    return _bridge
