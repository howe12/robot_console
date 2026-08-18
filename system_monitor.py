"""系统状态监控模块。

提供：
  - 系统资源指标（CPU / 内存 / 磁盘 / 网络 / 负载 / 温度 / 运行时长）
  - 软件版本信息（ROS 发行版、系统信息、工作空间包列表）
  - ROS2 图（节点 / 话题 / 服务 / 动作）实时列表
  - 底盘 & 传感器实时状态（odom / imu / gyro / spark_base/sensor / wheel_states）

传感器状态由一个轻量 rclpy 后台订阅节点维护（惰性启动），
当机器人驱动节点运行时自动产生数据；否则字段返回 None / false。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------- 系统资源指标（无 ROS 依赖，纯 psutil/子进程） ----------

try:  # psutil 更稳定，非必需（无 psutil 时回退到 /proc 读取）
    import psutil
    HAVE_PSUTIL = True
except Exception:  # noqa: BLE001
    HAVE_PSUTIL = False


def _read_proc(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except Exception:  # noqa: BLE001
        return default


def _first_line(fields: list[str]) -> str:
    if HAVE_PSUTIL:
        return ""
    try:
        cpu = 0.0
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = [int(x) for x in line.split()[1:8]]
                    idle = parts[3]
                    total = sum(parts)
                    cpu = (1 - idle / total) * 100
                    break
        return f"{cpu:.1f}"
    except Exception:  # noqa: BLE001
        return "0.0"


def system_metrics() -> dict:
    """采集一次系统资源快照。"""
    out: dict = {"uptime": None, "cpu_percent": None, "mem": {}, "disk": {}, "net": {}, "load": [], "temp": None, "hostname": None}
    out["hostname"] = os.uname().nodename if hasattr(os, "uname") else "unknown"
    out["kernel"] = f"{os.uname().release} {os.uname().machine}" if hasattr(os, "uname") else ""

    # uptime
    try:
        with open("/proc/uptime", "r") as f:
            out["uptime"] = float(f.read().split()[0])
    except Exception:  # noqa: BLE001
        pass

    if HAVE_PSUTIL:
        out["cpu_percent"] = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        out["mem"] = {"total": vm.total, "used": vm.used, "free": vm.available, "percent": vm.percent}
        du = psutil.disk_usage("/")
        out["disk"] = {"total": du.total, "used": du.used, "free": du.free, "percent": du.percent}
        try:
            nio = psutil.net_io_counters()
            out["net"] = {"sent_bytes": nio.bytes_sent, "recv_bytes": nio.bytes_recv}
        except Exception:  # noqa: BLE001
            pass
        out["load"] = list(os.getloadavg())
        try:
            out["temp"] = psutil.sensors_temperatures().get("coretemp", [{}])[0].get("current", None)
        except Exception:  # noqa: BLE001
            out["temp"] = None
    else:
        # 回退：v1.0 口径（一核 CPU，简化）
        out["cpu_percent"] = float(_first_line([]) or 0)
        try:
            meminfo = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l)
            out["mem"] = {
                "total": int(meminfo["MemTotal"].split()[0]) * 1024,
                "used": (int(meminfo["MemTotal"].split()[0]) - int(meminfo["MemAvailable"].split()[0])) * 1024,
                "free": int(meminfo["MemAvailable"].split()[0]) * 1024,
                "percent": round((1 - int(meminfo["MemAvailable"].split()[0]) / int(meminfo["MemTotal"].split()[0])) * 100, 1),
            }
        except Exception:  # noqa: BLE001
            pass
        try:
            du = shutil.disk_usage("/")
            out["disk"] = {"total": du.total, "used": du.used, "free": du.free, "percent": round(du.used / du.total * 100, 1)}
        except Exception:  # noqa: BLE001
            pass
        out["load"] = list(os.getloadavg())

    return out


def software_info(workspace: str | None = None) -> dict:
    """软件版本信息：ROS 发行版、系统、sourcing 路径、工作空间包列表。"""
    ros_distro = os.environ.get("ROS_DISTRO", "humble")
    info = {
        "ros_distro": ros_distro,
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
        "os_description": "",
        "shell": os.environ.get("SHELL", ""),
        "workspace": workspace,
        "packages": [],
        "launch_count": 0,
    }
    try:
        import platform
        info["os_description"] = f"{platform.system()} {platform.release()}"
    except Exception:  # noqa: BLE001
        pass
    if workspace:
        pkgs = []
        install = Path(workspace) / "install"
        if install.is_dir():
            for p in sorted(install.iterdir()):
                if p.is_dir() and not p.name.startswith(".") and (p / "share").is_dir():
                    pkgs.append(p.name)
            info["packages"] = pkgs
            info["launch_count"] = sum(
                1 for p in install.iterdir()
                for lp in (p / "share" / p.name / "launch").glob("*.launch.py")
            ) if install.is_dir() else 0
    return info


# ---------- ROS2 图 / 命令辅助 ----------

def _run_ros2(args: list[str], timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(
            ["ros2"] + args, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _run_ros2_parallel(args_list: list[list[str]], timeout: float = 8.0) -> list[str]:
    """并行执行多个 ros2 子进程（每个 300-400ms，串行 1.4s → 并行 400ms）。"""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(args_list)) as ex:
        futures = [ex.submit(_run_ros2, args, timeout) for args in args_list]
        return [f.result() for f in futures]


_graph_cache = {"ts": 0.0, "data": None}
_GRAPH_TTL = 6.0  # 加大缓存窗口，确保 Dashboard 8s 间隔必命中


def ros_graph() -> dict:
    """ROS2 图快照：节点 / 话题 / 服务 / 动作。带 3s 缓存。"""
    global _graph_cache
    now = time.time()
    if _graph_cache["data"] is not None and now - _graph_cache["ts"] < _GRAPH_TTL:
        return _graph_cache["data"]

    from ros_bridge import ros_available
    empty = {"nodes": [], "topics": [], "services": [], "actions": [], "topic_type": {}}
    if not ros_available:
        return empty
    # 并行 4 个 ros2 命令（每个 300-400ms → 总 ~400ms 替代 1.4s）
    results = _run_ros2_parallel([
        ["node", "list"],
        ["topic", "list", "-t"],
        ["service", "list"],
        ["action", "list"],
    ])
    nodes_raw, topics_raw_str, services_raw, actions_raw = results
    nodes = [l for l in nodes_raw.splitlines() if l.strip()]
    # 用 `ros2 topic list -t` 一次性拿所有话题+类型（替代逐话题 topic info，快 10x+）
    topics = []
    types = {}
    for line in topics_raw_str.splitlines():
        line = line.strip()
        if not line:
            continue
        # 格式: "/topic_name [pkg/msg/Type]"
        if "[" in line and "]" in line:
            name = line.split("[")[0].strip()
            typ = line.split("[")[1].rstrip("]").strip()
            topics.append(name)
            types[name] = typ
        else:
            topics.append(line)
    services = [l for l in services_raw.splitlines() if l.strip()]
    actions = [l for l in actions_raw.splitlines() if l.strip()]
    result = {"nodes": nodes, "topics": topics, "services": services, "actions": actions, "topic_type": types}
    _graph_cache = {"ts": now, "data": result}
    return result


_topology_cache = {"ts": 0.0, "data": None}
_TOPOLOGY_TTL = 6.0  # 加大缓存窗口，确保 Dashboard 8s 间隔必命中


# 已知功能包 → 分组映射（用于把节点归类到驱动/感知/应用等层）
_PKG_GROUPS = {
    "spark_base": "底盘驱动", "spark_bringup": "底盘驱动", "ydlidar": "雷达驱动",
    "camera": "相机驱动", "realsense2": "相机驱动", "lidar": "雷达驱动",
    "spark_teleop": "遥控", "spark_follower": "跟随",
    "spark_slam": "建图", "spark_cartographer": "建图", "slam": "建图",
    "spark_navigation": "导航", "nav2": "导航", "controller": "导航",
    "spark_rtab": "RTAB", "rtabmap": "RTAB",
    "spark_carry": "机械臂", "arm": "机械臂",
    "spark_yolo": "视觉检测", "tensorflow": "视觉检测", "spark_face": "视觉检测",
    "spark_voice": "语音", "vosk": "语音",
    "foxglove": "可视化", "rviz": "可视化", "robot_state_publisher": "TF",
    "tf": "TF", "ros2cli": "系统",
}


def _infer_node_group(node_name: str) -> str:
    """从节点名推断功能分组（用于前端按包折叠显示）。"""
    s = node_name.lstrip("/")
    # 取第一段作为命名空间/包名候选
    first = s.split("_")[0] if "_" in s else s
    # 在已知表里找包含关系
    for pkg, grp in _PKG_GROUPS.items():
        if pkg in s:
            return grp
    if "ros2cli" in s or "_daemon" in s:
        return "系统"
    if "rviz" in s:
        return "可视化"
    if "gazebo" in s or "robot_state_pub" in s:
        return "仿真/TF"
    return first or "其他"


def ros_topology() -> dict:
    """ROS2 拓扑（rqt_graph 风格）：节点 → 发布/订阅的话题与服务/动作关系。

    用 `ros2 node info <node>` 逐节点解析（含话题类型），TLC 缓存 2s。
    返回：
      {"nodes": [{name, publishers[], subscribers[], srv_servers[], srv_clients[],
                  action_servers[], action_clients[]}],
       "topics": [{name, type, publishers[], subscribers[]}],
       "services": [...], "actions": [...]}
    """
    global _topology_cache
    now = time.time()
    if _topology_cache["data"] is not None and now - _topology_cache["ts"] < _TOPOLOGY_TTL:
        return _topology_cache["data"]

    from ros_bridge import ros_available
    empty = {"ok": True, "nodes": [], "topics": [], "services": [], "actions": [],
             "links": [], "ts": now}
    if not ros_available:
        return empty

    node_names = [l for l in _run_ros2(["node", "list"]).splitlines() if l.strip()]

    # 并行跑 `ros2 node info` 每个节点（30 节点 × 350ms = 10.5s 串行 → ~500ms 并行）
    node_infos = _run_ros2_parallel(
        [["node", "info", n] for n in node_names],
        timeout=6,
    )

    # 解析每个节点
    parsed = []
    for n, info in zip(node_names, node_infos):
        entry = {"name": n, "group": _infer_node_group(n),
                 "publishers": [], "subscribers": [],
                 "srv_servers": [], "srv_clients": [],
                 "action_servers": [], "action_clients": []}
        section = None
        for line in info.splitlines():
            line = line.rstrip()
            if line.endswith(":"):
                key = line.rstrip(":").strip()
                if key in ("Publishers", "Subscribers", "Service Servers",
                           "Service Clients", "Action Servers", "Action Clients"):
                    section = {
                        "Publishers": "publishers", "Subscribers": "subscribers",
                        "Service Servers": "srv_servers", "Service Clients": "srv_clients",
                        "Action Servers": "action_servers", "Action Clients": "action_clients",
                    }[key]
                else:
                    section = None
                continue
            line = line.strip()
            if section and line:
                # 形如 "/topic: type/Message" 或 "/topic"
                if ":" in line:
                    name, typ = line.split(":", 1)
                    entry[section].append({"name": name.strip(), "type": typ.strip()})
                else:
                    entry[section].append({"name": line, "type": ""})
        parsed.append(entry)

    # 组装话题汇总
    topic_map: dict = {}
    for node in parsed:
        for kind, role in (("publishers", "publishers"), ("subscribers", "subscribers")):
            for t in node[kind]:
                key = t["name"]
                tm = topic_map.setdefault(key, {"name": key, "type": t.get("type", ""),
                                                "publishers": [], "subscribers": []})
                if not tm["type"]:
                    tm["type"] = t.get("type", "")
                if node["name"] not in tm[role]:
                    tm[role].append(node["name"])

    # 服务/动作
    srv_map: dict = {}
    act_map: dict = {}
    for node in parsed:
        for s in node["srv_servers"]:
            m = srv_map.setdefault(s["name"], {"name": s["name"], "type": s.get("type", ""),
                                               "servers": [], "clients": []})
            if node["name"] not in m["servers"]: m["servers"].append(node["name"])
            if not m["type"]: m["type"] = s.get("type", "")
        for s in node["srv_clients"]:
            m = srv_map.setdefault(s["name"], {"name": s["name"], "type": s.get("type", ""),
                                               "servers": [], "clients": []})
            if node["name"] not in m["clients"]: m["clients"].append(node["name"])
            if not m["type"]: m["type"] = s.get("type", "")
    for node in parsed:
        for a in node["action_servers"] + node["action_clients"]:
            role = "servers" if a in node["action_servers"] else "clients"
            m = act_map.setdefault(a["name"], {"name": a["name"], "type": a.get("type", ""), "servers": [], "clients": []})
            if node["name"] not in m[role]: m[role].append(node["name"])
            if not m["type"]: m["type"] = a.get("type", "")

    topics = list(topic_map.values())
    services = list(srv_map.values())
    actions = list(act_map.values())

    result = {"ok": True, "nodes": parsed, "topics": topics,
              "services": services, "actions": actions, "ts": now}
    _topology_cache = {"ts": now, "data": result}
    return result


# ---------- 底盘 & 传感器实时状态（rclpy 订阅） ----------

def _import_type(mod: str, name: str):
    """防御式导入 ROS 消息类型；缺失返回 None（不阻塞其他订阅）。"""
    try:
        m = __import__(mod, fromlist=[name])
        return getattr(m, name)
    except Exception:  # noqa: BLE001
        return None


# 消息类型定义（惰性导入）
ODOM_T = _import_type("nav_msgs.msg", "Odometry")
IMU_T = _import_type("sensor_msgs.msg", "Imu")
JOINTSTATE_T = _import_type("sensor_msgs.msg", "JointState")
BATTERY_T = _import_type("sensor_msgs.msg", "BatteryState")
GYRO_T = _import_type("spark_base.msg", "GyroMessage")
BASE_SENSOR_T = _import_type("spark_base.msg", "SparkBaseSensor")


class SensorMonitor:
    """后台 rclpy 订阅节点，维护底盘/传感器最新状态（线程内 spin）。"""

    def __init__(self):
        self._node = None
        self._executor = None
        self._thread = None
        self._latest: dict = {
            "odom": None, "imu": None, "gyro": None,
            "base_sensor": None, "wheel_states": None, "battery": None,
            "last_update": None,
        }
        self._lock = threading.Lock()

    def ensure_started(self) -> bool:
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import QoSProfile, ReliabilityPolicy
        except Exception:
            return False
        if self._node is not None:
            # 检查 spin 线程是否还活着
            if self._thread is not None and self._thread.is_alive():
                return True
            # 线程死了但节点还在，重建线程
            print("[system_monitor] spin 线程已死，重启…")
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
            return True
        try:
            # 兼容 ros_bridge 已 init 的情况
            try:
                if not rclpy.ok():
                    rclpy.init()
            except Exception:  # noqa: BLE001
                pass  # 已 init 或 context 已存在，继续
            self._node = Node("spark_system_monitor")
            exec_ = SingleThreadedExecutor()
            exec_.add_node(self._node)
            self._executor = exec_

            qos = QoSProfile(depth=2, reliability=ReliabilityPolicy.RELIABLE)
            subs = [
                ("odom", "odom", ODOM_T, self._odom),
                ("imu", "imu_data", IMU_T, self._imu),
                ("wheel_states", "wheel_states", JOINTSTATE_T, self._joints),
                ("battery", "battery_state", BATTERY_T, self._battery),
                ("gyro", "spark_base/gyro", GYRO_T, self._gyro),
                ("base_sensor", "spark_base/sensor", BASE_SENSOR_T, self._sensor),
            ]
            for key, topic, msg_type, conv in subs:
                if msg_type is None:
                    continue
                self._node.create_subscription(
                    msg_type, topic,
                    lambda m, k=key, conv=conv: self._on(k, conv(m)),
                    qos,
                )

            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
            print("[system_monitor] 底盘/传感器后台订阅启动（话题: odom, imu_data, spark_base/* 等）")
            return True
        except Exception as e:  # noqa: BLE001
            print("[system_monitor] 后台订阅启动失败:", e)
            self._close()
            return False

    def _spin(self):
        while self._node is not None:
            try:
                self._executor.spin_once(timeout_sec=0.2)
            except Exception:  # noqa: BLE001
                break

    def _on(self, key: str, value):
        with self._lock:
            self._latest[key] = value
            self._latest["last_update"] = time.time()

    def _odom(self, msg):
        return {
            "x": round(msg.pose.pose.position.x, 3),
            "y": round(msg.pose.pose.position.y, 3),
            "z": round(msg.pose.pose.position.z, 3),
            "lin_x": round(msg.twist.twist.linear.x, 3),
            "ang_z": round(msg.twist.twist.angular.z, 3),
        }

    def _imu(self, msg):
        return {
            "ax": round(msg.linear_acceleration.x, 3),
            "ay": round(msg.linear_acceleration.y, 3),
            "az": round(msg.linear_acceleration.z, 3),
            "wx": round(msg.angular_velocity.x, 3),
            "wy": round(msg.angular_velocity.y, 3),
            "wz": round(msg.angular_velocity.z, 3),
            "qx": round(msg.orientation.x, 3),
            "qy": round(msg.orientation.y, 3),
            "qz": round(msg.orientation.z, 3),
            "qw": round(msg.orientation.w, 3),
        }

    def _gyro(self, msg):
        return {
            "roll": round(msg.roll, 1),
            "pitch": round(msg.pitch, 1),
            "yaw": round(msg.yaw, 1),
            "anvx": round(msg.anvx, 1),
            "anvy": round(msg.anvy, 1),
            "anvz": round(msg.anvz, 1),
        }

    def _joints(self, msg):
        names = list(msg.name)
        pos = list(msg.position) if msg.position else []
        vel = list(msg.velocity) if msg.velocity else []
        return [{"name": names[i], "position": round(pos[i], 3) if i < len(pos) else None,
                 "velocity": round(vel[i], 3) if i < len(vel) else None} for i in range(len(names))]

    def _battery(self, msg):
        return {"volt": round(msg.voltage, 2), "percent": round(msg.percentage * 100) if msg.percentage else None,
                "charging": bool(msg.power_supply_status == msg.POWER_SUPPLY_STATUS_CHARGING)}

    def _sensor(self, msg):
        # SparkBaseSensor：bool 字段
        def g(name):
            return bool(getattr(msg, name, False))
        return {
            "ir_bumper_left": g("ir_bumper_left"),
            "ir_bumper_right": g("ir_bumper_right"),
            "ir_bumper_front": g("ir_bumper_front"),
            "cliff_left": g("cliff_left"),
            "cliff_right": g("cliff_right"),
            "cliff_front_left": g("cliff_front_left"),
            "cliff_front_right": g("cliff_front_right"),
            "cliff_back_left": g("cliff_back_left"),
            "cliff_back_right": g("cliff_back_right"),
            "wheel_drop_left": g("wheel_drop_left"),
            "wheel_drop_right": g("wheel_drop_right"),
            "wheel_over_current_left": g("wheel_over_current_left"),
            "wheel_over_current_right": g("wheel_over_current_right"),
        }

    def snapshot(self) -> dict:
        with self._lock:
            return {k: (list(v) if isinstance(v, list) else v) for k, v in self._latest.items()}

    def _close(self):
        node, self._node = self._node, None
        if node is not None:
            try:
                node.destroy_node()
            except Exception:  # noqa: BLE001
                pass


_sensor_monitor = SensorMonitor()


def get_sensor_monitor() -> SensorMonitor:
    return _sensor_monitor


def full_status(workspace: str | None = None, device_cfg: dict | None = None) -> dict:
    """组装一次完整状态快照（供 /api/system/status 调用）。"""
    dev_status = {}
    if device_cfg:
        try:
            from device_detect import detect_devices
            dev_status = detect_devices(device_cfg)
        except Exception:  # noqa: BLE001
            dev_status = {}
    sm = get_sensor_monitor()
    return {
        "ok": True,
        "system": system_metrics(),
        "software": software_info(workspace),
        "devices": dev_status,
        "sensors": sm.snapshot(),
        "ros_graph": ros_graph(),
        "ts": time.time(),
    }
