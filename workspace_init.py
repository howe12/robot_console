"""工作空间初始化：扫描任意 ROS2 工作空间，适配到 spark_tasks.yaml。

设计：
- scan_workspace(): 扫描 + 启发式（来自 device_adapter）
- compute_diff(): 对比当前 yaml vs adapter 结果，输出 structured diff
- apply_to_yaml(): 备份 + 写新文件（用户确认后才调用）

与 device_adapter 的关系：
- 复用 device_adapter.discover_config() 拿到包/launch/能力/tasks
- compute_diff 不修改任何状态（纯只读）
- apply_to_yaml 才真正写文件（需用户确认）
"""
import datetime
import shutil
from pathlib import Path
from typing import Dict, Optional, Any

import yaml

# 复用 device_adapter 的扫描逻辑
import device_adapter


def scan_workspace(workspace: str) -> dict:
    """扫描任意 ROS2 工作空间：包 + launch + 设备能力。"""
    return device_adapter.discover_config(workspace)


def load_current_yaml(yaml_path: Path) -> dict:
    """读取当前 spark_tasks.yaml，返回 dict。文件不存在时返回最小骨架。"""
    if not yaml_path.exists():
        return {"workspace": ""}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return {"workspace": ""}
        return data
    except Exception as e:
        return {"_error": str(e), "workspace": ""}


def compute_diff(yaml_path: Path, workspace: str) -> dict:
    """对比 spark_tasks.yaml vs adapter 扫描结果。

    返回结构:
    {
      "yaml_path": str,
      "yaml_exists": bool,
      "current_workspace": str,
      "current_task_count": int,
      "current_tasks": [ {id, name, package, launch, ...}, ... ],
      "discovered": { robot: {...}, topics: {...}, tasks: {...} },
      "diff": {
        "added":    [{package, launch, name, menu}, ...],  # 新发现但 yaml 没有
        "removed":  [{package, launch, name, menu?}, ...],  # yaml 有但 launch 文件已不存在
        "kept":     [{package, launch, name}, ...],         # 都在
        "modified":  [],  # TODO: 参数级 diff（暂不实现）
      }
    }
    """
    current = load_current_yaml(yaml_path)
    if "_error" in current:
        # yaml 损坏：让用户重新配置
        return {
            "yaml_path": str(yaml_path),
            "yaml_exists": yaml_path.exists(),
            "current_workspace": "",
            "current_task_count": 0,
            "current_tasks": [],
            "discovered": scan_workspace(workspace) if workspace else {},
            "diff": {"added": [], "removed": [], "kept": [], "modified": []},
            "yaml_error": current.get("_error"),
        }

    # 扫描
    discovered = scan_workspace(workspace) if workspace else {}

    # 当前 yaml 中的所有 task
    cur_tasks = []
    if "tasks" in current and isinstance(current["tasks"], dict):
        cur_tasks = current["tasks"].get("curated", []) or []
        cur_tasks += current["tasks"].get("workspace_pinned", []) or []

    # 扫描结果中的所有 task
    new_tasks = []
    if discovered and "tasks" in discovered:
        new_tasks = discovered["tasks"].get("curated", []) or []
        new_tasks += discovered["tasks"].get("workspace_pinned", []) or []

    # diff 逻辑
    cur_keys = {(t.get("package"), t.get("launch")) for t in cur_tasks}
    new_keys = {(t["package"], t["launch"]) for t in new_tasks}
    added = [t for t in new_tasks if (t["package"], t["launch"]) not in cur_keys]
    removed = [t for t in cur_tasks if (t.get("package"), t.get("launch")) not in new_keys]
    kept = [t for t in cur_tasks if (t.get("package"), t.get("launch")) in new_keys]

    return {
        "yaml_path": str(yaml_path),
        "yaml_exists": yaml_path.exists(),
        "current_workspace": current.get("workspace", ""),
        "current_task_count": len(cur_tasks),
        "current_tasks": cur_tasks,
        "discovered": discovered,
        "diff": {
            "added": added,
            "removed": removed,
            "kept": kept,
            "modified": [],
        },
    }


def apply_to_yaml(
    yaml_path: Path,
    workspace: str,
    current_yaml: Optional[dict] = None,
    auto_backup: bool = True,
) -> dict:
    """把 adapter 扫描结果写为 spark_tasks.yaml。

    - 保留 device 字段（如果当前 yaml 有）
    - 备份原文件到 .bak.YYYYMMDD-HHMMSS
    - 写新文件
    """
    # 1. 备份（如果存在）
    backup_path = None
    if auto_backup and yaml_path.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = yaml_path.with_suffix(f".bak.{ts}.yaml")
        try:
            shutil.copy2(yaml_path, backup_path)
        except Exception as e:
            return {"ok": False, "error": f"备份失败: {e}"}

    # 2. 重新 scan 拿到最新数据
    config = scan_workspace(workspace)
    if not config or "tasks" not in config:
        return {"ok": False, "error": f"扫描失败：{workspace} 不是有效 ROS2 工作空间"}

    # 3. 保留 device 字段（如果当前 yaml 有）
    if current_yaml is None:
        current_yaml = load_current_yaml(yaml_path)
    device = current_yaml.get("device", {"auto_detect": True}) if current_yaml else {"auto_detect": True}

    # 4. 构造新 yaml
    new_yaml = {
        "workspace": workspace,
        "device": device,
        "tasks": {
            "curated": config["tasks"]["curated"],
            "workspace_pinned": config["tasks"]["workspace_pinned"],
        },
    }

    # 5. 写（用 safe_dump 保留中文）
    try:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(new_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception as e:
        return {"ok": False, "error": f"写入失败: {e}", "backup_path": str(backup_path) if backup_path else None}

    new_task_count = len(new_yaml["tasks"]["curated"]) + len(new_yaml["tasks"]["workspace_pinned"])
    return {
        "ok": True,
        "backup_path": str(backup_path) if backup_path else None,
        "yaml_path": str(yaml_path),
        "new_task_count": new_task_count,
        "applied_at": datetime.datetime.now().isoformat(),
    }