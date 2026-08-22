"""通用 ROS2 机器人适配器：扫描任意 ROS2 工作空间，识别机器人能力。

设计目标：
- 输入：任意 ROS2 工作空间路径
- 输出：机器人类型、能力、相机话题、底盘话题、Tasks 清单
- 前端无需改：通用 Dashboard 框架自动适配

启发式策略：
1. 包名关键词 → 机器人类型（ground / arm / quadrotor）
2. ROS2 话题类型 → 能力（camera / lidar / base / arm）
3. launch 文件名 → 是否"启动器" vs "应用"
"""
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# launch 文件命名启发式
STARTUP_KEYWORDS = ["bringup", "driver", "robot", "base", "start", "core", "system", "boot", "init"]
APP_KEYWORDS = [
    "navigation", "slam", "mapping", "teleop", "follow", "patrol",
    "explore", "arm", "grasp", "pick", "place", "detect", "track",
    "scan", "explore", "navigate", "waypoint",
]

# 机器人类型启发式（包名包含这些关键词 → 推断类型）
ROBOT_TYPE_PATTERNS = {
    "quadrotor": ["quadrotor", "px4", "mavros", "drones", "tello", "bebop"],
    "arm": ["arm", "manipulator", "gripper", "ur5", "ur10", "franka", "moveit"],
    "humanoid": ["humanoid", "atlas", "nao", "pepper"],
    "marine": ["marine", "submarine", "usv", "auv"],
}


def _run_ros2(args: List[str], timeout: int = 5) -> Optional[str]:
    """执行 ros2 命令，超时返回 None。"""
    try:
        r = subprocess.run(
            ["ros2"] + args, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _scan_launch_files(workspace: str) -> List[Dict]:
    """扫描 install/<pkg>/share/<pkg>/launch/*.launch.py。"""
    ws = Path(workspace)
    install = ws / "install"
    if not install.is_dir():
        return []
    launches = []
    for pkg_dir in sorted(install.iterdir()):
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
            continue
        share = pkg_dir / "share" / pkg_dir.name
        if not share.is_dir():
            continue
        launch_dir = share / "launch"
        if not launch_dir.is_dir():
            continue
        for lf in sorted(launch_dir.glob("*.launch.py")):
            launches.append({
                "package": pkg_dir.name,
                "launch": lf.name,
                "path": str(lf),
                "is_starter": any(k in lf.name.lower() for k in STARTUP_KEYWORDS),
                "is_app": any(k in lf.name.lower() for k in APP_KEYWORDS),
            })
    return launches


def _infer_robot_type(packages: List[str]) -> str:
    """根据包名启发式判断机器人类型。"""
    pkg_str = " ".join(packages).lower()
    for rtype, keywords in ROBOT_TYPE_PATTERNS.items():
        if any(k in pkg_str for k in keywords):
            return rtype
    return "ground"  # 默认移动底盘


def _discover_capabilities() -> List[str]:
    """通过 ros2 topic list -t 自动发现机器人能力。"""
    caps = []
    raw = _run_ros2(["topic", "list", "-t"])
    if not raw:
        return caps
    types = set()
    for line in raw.splitlines():
        if "[" in line:
            t = line.split("[")[-1].rstrip("]").strip()
            types.add(t)
    if "sensor_msgs/msg/Image" in types:
        caps.append("camera")
    if "sensor_msgs/msg/PointCloud2" in types:
        caps.append("lidar_3d")
    if "sensor_msgs/msg/LaserScan" in types:
        caps.append("lidar_2d")
    if "sensor_msgs/msg/Imu" in types:
        caps.append("imu")
    if any(t.startswith("geometry_msgs/msg/Twist") for t in types):
        caps.append("base")
    if any("JointState" in t for t in types) or any("JointTrajectory" in t for t in types):
        caps.append("arm")
    if "nav_msgs/msg/Odometry" in types:
        caps.append("odometry")
    if "sensor_msgs/msg/BatteryState" in types:
        caps.append("battery")
    return caps


def discover_camera_topics() -> List[Dict]:
    """找出所有 Image 话题，返回前端选择器。"""
    topics = []
    raw = _run_ros2(["topic", "list", "-t"])
    if not raw:
        return topics
    for line in raw.splitlines():
        if "[sensor_msgs/msg/Image]" in line:
            name = line.split("[")[0].strip()
            # 启发式推断用途
            lname = name.lower()
            purpose = "color" if "color" in lname or "rgb" in lname else \
                      "depth" if "depth" in lname else \
                      "infra" if "infra" in lname or "ir" in lname else "unknown"
            topics.append({
                "name": name,
                "type": "sensor_msgs/msg/Image",
                "default_for": purpose,
            })
    return topics


def discover_cmd_vel_topic() -> str:
    """找出底盘控制话题。"""
    raw = _run_ros2(["topic", "list", "-t"])
    if raw:
        for line in raw.splitlines():
            if "geometry_msgs/msg/Twist" in line and "Stamped" not in line:
                name = line.split("[")[0].strip()
                if "cmd" in name.lower():
                    return name
    return "/cmd_vel"  # ROS 默认


def discover_robot(workspace: str) -> Dict:
    """扫描工作空间，识别机器人类型。
    返回:
      {
        "workspace": str,
        "type": "ground|arm|quadrotor|humanoid|marine|unknown",
        "packages": List[str],
        "launches": List[Dict],  # 每个含 package/launch/path/is_starter/is_app
        "capabilities": List[str],  # camera/lidar_2d/lidar_3d/base/arm/...
      }
    """
    launches = _scan_launch_files(workspace)
    packages = sorted(set(l["package"] for l in launches))
    return {
        "workspace": workspace,
        "type": _infer_robot_type(packages),
        "packages": packages,
        "launches": launches,
        "capabilities": _discover_capabilities(),
    }


def generate_default_tasks(workspace: str) -> Dict:
    """生成 Tasks 页面的默认清单（curated + workspace_pinned）。

    启发式：
    - 含 bringup/driver/robot/base/start 关键字 → curated（启动器）
    - 含 navigation/slam/arm/grasp 等 → curated（应用）
    - 其他 → workspace_pinned（普通列表）
    """
    robot = discover_robot(workspace)
    curated = []
    pinned = []
    for i, lf in enumerate(robot["launches"]):
        if lf["is_starter"] or lf["is_app"]:
            entry = {
                "menu": 1 if lf["is_starter"] else 20 + i,
                "name": lf["launch"].replace(".launch.py", "").replace("_", " ").title(),
                "package": lf["package"],
                "launch": lf["launch"],
                "params": {},
                "auto_discovered": True,
            }
            curated.append(entry)
        else:
            pinned.append({
                "menu": 50 + i,
                "package": lf["package"],
                "launch": lf["launch"],
                "params": {},
                "auto_discovered": True,
            })
    return {
        "curated": curated,
        "workspace_pinned": pinned,
        "robot_type": robot["type"],
    }


def discover_config(workspace: str) -> Dict:
    """一键生成完整适配配置。"""
    robot = discover_robot(workspace)
    topics = {
        "camera_topics": discover_camera_topics(),
        "cmd_vel_topic": discover_cmd_vel_topic(),
    }
    tasks = generate_default_tasks(workspace)
    return {
        "robot": robot,
        "topics": topics,
        "tasks": tasks,
    }