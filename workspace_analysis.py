"""ROS2 工作空间分析：自动发现可启动的功能包与 launch 文件及其参数。

设计：
  - 扫描 <workspace>/install/<pkg>/share/<pkg>/launch 下的 *.launch.py
  - 安全解析 launch 文件中的 DeclareLaunchArgument(default_value=...)，
    提取参数名 / 默认值 / 描述，用于前端自动生成参数表单。
  - 合并 spark_tasks.yaml 中的人工精编任务（优先级最高，带菜单归类）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

DEFAULT_LAUNCH = "launch"
_PREFIX_RE = re.compile(r"^\s*(?:\.|/)*")
_ARG_RE = re.compile(
    r"[\('\"](?P<name>[A-Za-z_][A-Za-z0-9_]*)[\"']"
)

# ROS2 常见参数 default_value 形式解析
_STR_PAT = re.compile(r"default_value\s*=\s*(['\"])(?P<val>.*?)\1")
_BOOL_PAT = re.compile(r"default_value\s*=\s*(?:['\"])?(?P<val>true|True|False|false)(?:['\"])?")
_INT_PAT = re.compile(r"default_value\s*=\s*(?P<val>-?\d+)\b")
_FLOAT_PAT = re.compile(r"default_value\s*=\s*(?P<val>-?\d+\.\d+)\b")


def _parse_value(pat_name: str, raw: str) -> dict:
    """根据命中的模式类型，返回 (type, value)。"""
    v = raw.strip()
    if pat_name == "str":
        return {"type": "str", "default": v, "has_default": True}
    if pat_name == "bool":
        return {"type": "bool", "default": v.lower() == "true", "has_default": True}
    if pat_name == "int":
        return {"type": "int", "default": int(v), "has_default": True}
    if pat_name == "float":
        return {"type": "float", "default": float(v), "has_default": True}
    return {"type": "str", "default": v, "has_default": True}


def _extract_args(source: str) -> dict:
    """从 launch 文件源码提取 DeclareLaunchArgument 的参数定义。

    用轻量正则（避免导包执行）。只读声明，不执行文件。
    """
    args: dict = {}
    # 逐段匹配 DeclareLaunchArgument( ... ) 块（非贪婪到首个 ')'，参数块内少见嵌套括号）
    for m in re.finditer(r"DeclareLaunchArgument\s*\((.*?)\)\s*", source, re.S):
        block = m.group(1)
        nm = _ARG_RE.search(block)
        if not nm:
            continue
        name = nm.group("name")
        if name in ("true", "false", "True", "False", "if", "elif", "else", "not", "and", "or"):
            continue
        # 判定 default_value 类型与取值（字符串式优先，布尔次之，再数值）
        pat_order = [("str", _STR_PAT), ("bool", _BOOL_PAT), ("float", _FLOAT_PAT), ("int", _INT_PAT)]
        dv = None
        found_type = None
        for t, pat in pat_order:
            dm = pat.search(block)
            if dm:
                dv = dm.group("val")
                found_type = t
                break
        desc = ""
        dm = re.search(r"description\s*=\s*(['\"])(?P<d>[^'\"]*)\1", block)
        if dm:
            desc = dm.group("d")
        if found_type:
            meta = _parse_value(found_type, dv)
        else:
            meta = {"type": "str", "default": "", "has_default": False}
        meta["desc"] = desc
        if not meta["has_default"]:
            meta["default"] = ""
        args[name] = meta
    return args


def discover_workspace(workspace: str | None) -> dict:
    """扫描工作空间，返回包 → launch 文件列表（含参数）。"""
    if not workspace:
        return {"packages": [], "launches": []}
    ws = Path(workspace)
    install = ws / "install"
    if not install.is_dir():
        install = ws  # 源码 fallback
    packages = []
    launches = []
    for pkg_dir in sorted(install.iterdir()):
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
            continue
        share = pkg_dir / "share" / pkg_dir.name
        launch_dir = share / DEFAULT_LAUNCH
        if not launch_dir.is_dir():
            # 有些包 share 名与包名不同，尝试 share/<pkg>/launch 存在即计
            continue
        files = []
        for lf in sorted(launch_dir.glob("*.launch.py")):
            src = lf.read_text(errors="ignore")
            args = _extract_args(src)
            files.append({
                "path": str(lf),
                "name": lf.name,
                "args": args,
            })
        if files:
            packages.append(pkg_dir.name)
            launches.append({"package": pkg_dir.name, "launch": files})
    return {"packages": packages, "launches": launches}


def find_launch_path(workspace: str | None, package: str, launch_name: str) -> str | None:
    """在 install 与源码目录中查找 launch 文件的绝对路径；找不到返回 None。"""
    if not workspace or not package or not launch_name:
        return None
    ws = Path(workspace)
    candidates = [
        ws / "install" / package / "share" / package / "launch" / launch_name,
        ws / "install" / package / "share" / package / DEFAULT_LAUNCH / launch_name,
    ]
    # 源码目录可能嵌套（src/spark/spark_bringup/launch 等），用 glob 递归找
    for base in (ws / "src",):
        if base.is_dir():
            candidates.extend(sorted(base.glob(f"**/{package}/launch/{launch_name}")))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None
