"""设备检测：复刻 onekey.sh 的 check_dev 逻辑（lsusb + /opt/lidar.txt）。"""
import subprocess
from pathlib import Path


def _lsusb() -> str:
    try:
        return subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return ""


def _detect_vendors(usb_out: str, vendors: dict) -> list:
    """返回命中的设备类型列表（同一类型可能多个）。"""
    found = []
    for vid_pid, name in vendors.items():
        if vid_pid in usb_out:
            found.append(name)
    return found


def detect_devices(cfg: dict) -> dict:
    """cfg 为 spark_tasks.yaml 的 device 段。返回结构化设备状态。"""
    usb = _lsusb()
    result = {"camera": None, "arm": None, "base": None, "lidar": None, "usb_raw": usb}

    # 相机（lsusb 匹配）
    cams = _detect_vendors(usb, cfg["camera"]["vendors"])
    result["camera"] = {"type": cams[0] if cams else None, "connected": bool(cams)}

    # 机械臂
    arms = _detect_vendors(usb, cfg["arm"]["vendors"])
    result["arm"] = {"type": arms[0] if arms else None, "connected": bool(arms)}

    # 底盘
    bases = _detect_vendors(usb, cfg["base"]["vendors"])
    result["base"] = {"type": bases[0] if bases else None, "connected": bool(bases)}

    # 雷达：类型读 /opt/lidar.txt，连接看 USB 计数
    lidar_type = None
    try:
        t = Path(cfg["lidar"]["type_file"]).read_text().strip()
        if t:
            lidar_type = t
    except Exception:
        pass
    usb_count = usb.count(cfg["lidar"]["usb_id"])
    result["lidar"] = {"type": lidar_type, "connected": usb_count >= 1, "usb_count": usb_count}

    # 汇总占位符变量（与 onekey.sh 的 CAMERATYPE/LIDARTYPE/ARMTYPE 对齐）
    result["vars"] = {
        "CAMERATYPE": result["camera"]["type"] or "",
        "LIDARTYPE": result["lidar"]["type"] or "ydlidar_g6",
        "ARMTYPE": result["arm"]["type"] or "uarm",
    }
    return result


if __name__ == "__main__":
    import sys

    # 简易自测：加载 YAML 里的 device 段
    import yaml

    cfg = yaml.safe_load(open(sys.argv[1]))["device"]
    print(detect_devices(cfg))
