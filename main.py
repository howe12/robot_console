"""Spark 可视化控制台后端（升级版）。

原有接口：
  GET  /api/tasks           任务清单（含展开后的参数默认值）
  GET  /api/devices         设备检测（相机/雷达/底盘/机械臂）
  POST /api/tasks/{id}/start  启动任务  body: {"params": {...}}
  POST /api/tasks/{id}/stop   停止任务（SIGINT 优雅停止）
  GET  /api/status          当前运行任务状态 + ROS/相机状态
  GET  /api/logs/{id}?tail=N 任务日志
  WS   /ws/logs             实时日志流（结构化：node/level/line）
  GET  /api/camera/stream   MJPEG 相机推流（camera/color/image_raw 或自定义）
  POST /api/cmd_vel         发布速度  body: {"linear": x, "angular": z}
  GET  /                    前端单页

本版本新增：
  GET  /api/system/status   系统健康快照（资源/软件/设备/传感器/ROS图）
  GET  /api/workspace       工作空间功能分析（包→launch→参数）
  GET  /api/tasks/{id}/logs 日志（node/level 过滤）
  GET  /api/logs/filters   可用 node/level 过滤器
  POST /api/tasks/custom    按工作空间分析的包/launch 自定义启动
  GET  /api/graph           实时 ROS2 图（节点/话题）

运行：run.sh（会 source ROS2 环境）或 uvicorn main:app --host 0.0.0.0 --port 8080
"""
import asyncio
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from device_detect import detect_devices
from launch_manager import LaunchManager
from ros_bridge import get_bridge, ros_available
import system_monitor
import workspace_analysis

BASE = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((BASE / "spark_tasks.yaml").read_text())
STATIC = BASE / "static"

app = FastAPI(title="Spark Console", version="0.6.0")

# 活跃 WebSocket 客户端集合（用于 /api/system/stats 显示连接数）
_ws_clients: set = set()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

manager = LaunchManager(workspace=CONFIG["workspace"])
bridge = get_bridge()

app.mount("/static", StaticFiles(directory=STATIC), name="static")


class StartBody(BaseModel):
    params: dict = {}


class CustomStartBody(BaseModel):
    package: str
    launch: str
    params: dict = {}


class TemplateStartBody(BaseModel):
    template_id: str
    algorithm_id: str
    params: dict = {}


class CmdVelBody(BaseModel):
    linear: float = 0.0
    angular: float = 0.0


class ClientErrorBody(BaseModel):
    message: str = ""
    url: str = ""
    at: str = ""
    ua: str = ""


@app.post("/api/client-error")
def api_client_error(body: ClientErrorBody):
    """前端把未捕获错误上报到这里，便于排查"页面静默变空"类问题。"""
    try:
        with open(BASE / "client_errors.log", "a", encoding="utf-8") as f:
            f.write(f"[{body.at}] {body.url} | {body.ua}\n    {body.message}\n")
    except Exception:
        pass
    return {"ok": True}


def _expand_task_defaults(task: dict, devices: dict) -> dict:
    """把参数默认值里的 $VAR 占位符展开为设备检测结果。"""
    vars_map = devices.get("vars", {})
    t = dict(task)
    t["params"] = {}
    for k, meta in task.get("params", {}).items():
        m = dict(meta)
        v = str(m.get("default", ""))
        for var, val in vars_map.items():
            v = v.replace("$" + var, str(val))
        m["default"] = v
        t["params"][k] = m
    return t


def _task_launch_info(task: dict, devices_vars: dict) -> dict:
    """计算每个功能的启动信息：完整命令 / launch 文件名 / 绝对路径。"""
    info = {"launch_cmd": "", "launch_file": "", "launch_path": None, "launch_pkg": ""}
    try:
        cmd = manager.build_command(task, devices_vars, {})
        info["launch_cmd"] = cmd
    except Exception:  # noqa: BLE001
        pass
    # 单独展开 package / launch 文件名（与 build_command 一致：choices → {key} 占位符）
    try:
        choice_vals, opt_meta = {}, {}
        for ch in task.get("choices", []):
            sel = ch.get("default")
            opt = next((o for o in ch["options"] if o["value"] == sel), ch["options"][0])
            choice_vals[ch["key"]] = opt["value"]
            for k, v in opt.items():
                if k not in ("value", "label"):
                    opt_meta[k] = v
        repl = {**choice_vals, **opt_meta}
        pkg = task.get("package", "")
        for k, v in repl.items():
            pkg = pkg.replace("{%s}" % k, str(v))
        launch_name = task.get("launch", "")
        for k, v in repl.items():
            launch_name = launch_name.replace("{%s}" % k, str(v))
        info["launch_pkg"] = pkg
        info["launch_file"] = launch_name
        info["launch_path"] = workspace_analysis.find_launch_path(
            CONFIG["workspace"], pkg, launch_name)
    except Exception:  # noqa: BLE001
        pass
    return info


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/tasks")
def api_tasks():
    devices = detect_devices(CONFIG["device"])
    tasks = [_expand_task_defaults(t, devices) for t in CONFIG["tasks"]]
    vars_map = devices.get("vars", {})
    for t in tasks:
        t.update(_task_launch_info(t.copy(), vars_map))
    return {"ok": True, "devices": devices, "tasks": tasks}


@app.get("/api/launch/source")
def api_launch_source(package: str = Query(""), launch: str = Query("")):
    """返回某个 launch 文件的源码与绝对路径（供前端跳转/查看）。"""
    from pathlib import Path as _P
    path = workspace_analysis.find_launch_path(CONFIG["workspace"], package, launch)
    if not path:
        return {"ok": False, "error": "未找到 launch 文件: %s / %s" % (package, launch)}
    try:
        src = _P(path).read_text(errors="replace")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "读取失败: %s" % e}
    return {"ok": True, "package": package, "launch": launch, "path": path, "source": src}


@app.get("/api/devices")
def api_devices():
    return {"ok": True, "devices": detect_devices(CONFIG["device"])}


def _running_task_id() -> str | None:
    """返回当前正在运行的任务 ID（互斥：只允许一个 demo 同时运行）。"""
    for r in manager.status():
        if r.get("running"):
            return r["id"]
    return None


@app.post("/api/tasks/{task_id}/start")
def api_start(task_id: str, body: StartBody):
    task = next((t for t in CONFIG["tasks"] if t["id"] == task_id), None)
    if not task:
        return {"ok": False, "error": "未知任务: %s" % task_id}
    if not task.get("enabled", True):
        return {"ok": False, "error": "任务已禁用: %s" % task_id}
    # 互斥：已有其他任务运行时拒绝
    running = _running_task_id()
    if running and running != task_id:
        return {"ok": False, "error": "已有功能正在运行（%s），请先停止后再启动新功能" % running}
    devices = detect_devices(CONFIG["device"])
    result = manager.start(task, devices.get("vars", {}), body.params)
    return {"ok": result["ok"], **result}


@app.post("/api/tasks/custom")
def api_task_custom(body: CustomStartBody):
    """按工作空间分析出的 包/launch 自定义启动（绕开精编 YAML）。"""
    # 互斥
    running = _running_task_id()
    if running:
        return {"ok": False, "error": "已有功能正在运行（%s），请先停止后再启动新功能" % running}
    devices = detect_devices(CONFIG["device"])
    task = {
        "id": "custom_" + body.package + "__" + body.launch.replace(".launch.py", ""),
        "name": "%s / %s" % (body.package, body.launch),
        "kind": "launch",
        "package": body.package,
        "launch": body.launch,
        "params": {k: {"default": v} for k, v in body.params.items()},
    }
    result = manager.start(task, devices.get("vars", {}), body.params)
    return {"ok": result["ok"], **result}


@app.post("/api/tasks/{task_id}/stop")
def api_stop(task_id: str, request: Request):
    import datetime
    print("[api_stop] %s 调用停止 %s (client=%s)" % (
        datetime.datetime.now().strftime("%H:%M:%S"), task_id,
        request.client.host if request.client else "?"))
    return {"ok": True, **manager.stop(task_id)}


@app.post("/api/stop-all")
def api_stop_all(request: Request):
    """紧急停止：停掉所有运行中的任务 + kill 全部 ROS 节点。"""
    import datetime
    client = request.client.host if request.client else "?"
    print("[EMERGENCY-STOP] %s from %s" % (datetime.datetime.now().strftime("%H:%M:%S"), client))
    stopped = []
    for r in manager.status():
        if r.get("running"):
            manager.stop(r["id"])
            stopped.append(r["id"])
    manager.kill_all()
    return {"ok": True, "stopped": stopped, "killed_ros": True}


@app.get("/api/status")
def api_status():
    # camera frame 现在由各 StreamContext 自己管理（ros_bridge.StreamContext），
    # /api/status 不再需要走全局 bridge
    return {
        "ok": True,
        "running": manager.status(),
        "ros": {
            "available": ros_available,
            "bridge_started": False,  # 保留字段兼容（无意义，前端不再依赖）
            "camera_frame": False,
            "camera_stamp_ns": None,
        },
    }


@app.get("/api/tasks/{task_id}/logs")
def api_logs(task_id: str, tail: int = 200,
             node: str | None = Query(None), level: str | None = Query(None)):
    return {"ok": True, "task_id": task_id,
            "lines": manager.get_log(task_id, tail, node=node, level=level)}


@app.get("/api/logs/filters")
def api_log_filters():
    return {"ok": True, **manager.available_filter()}


@app.get("/api/system/status")
def api_system_status():
    """系统健康快照：资源 + 软件 + 设备 + 传感器 + ROS 图。"""
    system_monitor.get_sensor_monitor().ensure_started()
    return system_monitor.full_status(CONFIG["workspace"], CONFIG["device"])


@app.get("/api/system/light")
def api_system_light():
    """轻量系统快照（不含 ROS 图）：CPU/内存/设备/传感器/软件。
    响应 <30ms，可高频轮询不卡 UI。Dashboard 主路径用此端点。"""
    system_monitor.get_sensor_monitor().ensure_started()
    from device_detect import detect_devices
    import yaml as _yaml
    cfg = _yaml.safe_load((BASE / "spark_tasks.yaml").read_text())["device"]
    return {
        "ok": True,
        "system": system_monitor.system_metrics(),
        "software": system_monitor.software_info(CONFIG["workspace"]),
        "devices": detect_devices(cfg),
        "sensors": system_monitor.get_sensor_monitor().snapshot(),
        "ts": __import__("time").time(),
    }


@app.get("/api/workspace")
def api_workspace():
    """工作空间功能分析：包 → launch → 参数。"""
    return {"ok": True, "workspace": CONFIG["workspace"],
            **workspace_analysis.discover_workspace(CONFIG["workspace"])}


@app.get("/api/adapter/config")
def api_adapter_config(workspace: str = ""):
    """通用 ROS2 机器人适配器：扫描任意工作空间，
    返回机器人能力、相机话题、底盘话题、自动生成的 Tasks 清单。

    不传 workspace 时使用 spark_tasks.yaml 里的默认。
    适配任意机器人：前端不需要改，只要后端能返回通用格式。
    """
    ws = workspace or CONFIG["workspace"]
    try:
        import device_adapter
        config = device_adapter.discover_config(ws)
        return {"ok": True, **config}
    except Exception as e:
        return {"ok": False, "error": str(e), "workspace": ws}


@app.get("/api/task-templates")
def api_task_templates():
    """获取所有 task templates（算法选项 + 参数 schema）。

    前端 Tasks.vue 用这个显示参数选择对话框。
    文件不存在/损坏时返回空 templates（不报错）。
    """
    import yaml
    templates_path = BASE / "spark_task_templates.yaml"
    if not templates_path.exists():
        return {"ok": True, "templates": {}, "exists": False, "yaml_path": str(templates_path)}
    try:
        data = yaml.safe_load(templates_path.read_text(encoding="utf-8"))
        return {"ok": True, "templates": data.get("task_templates", {}), "exists": True, "yaml_path": str(templates_path)}
    except Exception as e:
        return {"ok": False, "error": str(e), "templates": {}, "yaml_path": str(templates_path)}


@app.post("/api/tasks/template")
def api_task_template_start(body: TemplateStartBody):
    """根据 template + 算法 + 参数启动任务。

    用户在 Tasks 页选算法、填完参数后调这个端点。
    互斥：跟现有 task 互斥保护（同一时间只能跑一个）。
    """
    # 互斥
    running = _running_task_id()
    if running:
        return {"ok": False, "error": "已有功能正在运行（%s），请先停止后再启动新功能" % running}

    import yaml
    templates_path = BASE / "spark_task_templates.yaml"
    if not templates_path.exists():
        return {"ok": False, "error": "spark_task_templates.yaml 不存在"}
    try:
        data = yaml.safe_load(templates_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"yaml 解析失败: {e}"}
    templates = data.get("task_templates", {})
    if body.template_id not in templates:
        return {"ok": False, "error": f"未知 template_id: {body.template_id}"}
    template = templates[body.template_id]
    algo = next((a for a in template["algorithms"] if a["id"] == body.algorithm_id), None)
    if not algo:
        return {"ok": False, "error": f"未知 algorithm_id: {body.algorithm_id}"}

    # 构造 task：用 algo 指定的 package + launch + 用户参数
    task = {
        "id": f"{body.template_id}_{body.algorithm_id}",
        "name": f"{template.get('label', body.template_id)} - {algo['name']}",
        "kind": "launch",
        "package": algo["package"],
        "launch": algo["launch"],
        "params": {k: {"default": v} for k, v in (body.params or {}).items()},
        "template_id": body.template_id,
        "algorithm_id": body.algorithm_id,
    }
    result = manager.start(task, CONFIG["device"].get("vars", {}), body.params or {})
    return {"ok": result["ok"], **result}


@app.get("/api/workspace/status")
def api_workspace_status():
    """检查 spark_tasks.yaml 的工作空间是否有效（用于 Dashboard 启动时的引导页判断）。"""
    yaml_path = BASE / "spark_tasks.yaml"
    if not yaml_path.exists():
        return {"ok": False, "reason": "no_yaml", "yaml_path": str(yaml_path)}
    try:
        cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "reason": "yaml_error", "yaml_path": str(yaml_path), "error": str(e)}
    if not isinstance(cfg, dict):
        return {"ok": False, "reason": "invalid_yaml", "yaml_path": str(yaml_path)}
    ws = cfg.get("workspace", "")
    if not ws:
        return {"ok": False, "reason": "no_workspace", "yaml_path": str(yaml_path)}
    ws_path = Path(ws)
    if not ws_path.exists():
        return {"ok": False, "reason": "path_missing", "workspace": ws, "yaml_path": str(yaml_path)}
    if not (ws_path / "install").is_dir():
        return {"ok": False, "reason": "no_install_dir", "workspace": ws}
    return {"ok": True, "workspace": ws, "yaml_path": str(yaml_path)}


@app.get("/api/workspace/diff")
def api_workspace_diff(workspace: str = ""):
    """对比 spark_tasks.yaml vs adapter 扫描结果。

    用户点"扫描"时调，看修改建议。
    """
    global CONFIG
    yaml_path = BASE / "spark_tasks.yaml"
    if not workspace and yaml_path.exists():
        try:
            cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            workspace = cfg.get("workspace", "") if isinstance(cfg, dict) else ""
        except Exception:
            workspace = ""
    try:
        import workspace_init
        return workspace_init.compute_diff(yaml_path, workspace or "")
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/workspace/apply")
def api_workspace_apply(workspace: str, auto_backup: bool = True):
    """应用 adapter 扫描结果到 spark_tasks.yaml（带自动备份）。

    用户确认修改后调。不会自动 reload CONFIG（需要 GET /api/workspace/reload）。
    """
    if not workspace:
        return {"ok": False, "error": "workspace 参数为空"}
    yaml_path = BASE / "spark_tasks.yaml"
    try:
        import workspace_init
        current_yaml = workspace_init.load_current_yaml(yaml_path)
        result = workspace_init.apply_to_yaml(yaml_path, workspace, current_yaml, auto_backup)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/workspace/reload")
def api_workspace_reload():
    """重新加载 spark_tasks.yaml → 重新初始化 LaunchManager。

    让新工作空间立即生效（不需要重启后端）。
    """
    global CONFIG, manager
    try:
        CONFIG = yaml.safe_load((BASE / "spark_tasks.yaml").read_text(encoding="utf-8"))
        manager = LaunchManager(workspace=CONFIG["workspace"])
        return {"ok": True, "workspace": CONFIG.get("workspace", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/graph")
def api_graph():
    return {"ok": True, **system_monitor.ros_graph()}


@app.get("/api/topology")
def api_topology():
    """ROS2 节点/话题/服务/动作 拓扑（rqt_graph 风格）。"""
    return system_monitor.ros_topology()


def _git_info() -> dict:
    """读取当前仓库 git 状态（仅读，绝不修改）。"""
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parent
    def run(*args):
        try:
            r = subprocess.run(['git'] + list(args), cwd=repo, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None
    info = {
        "ok": True, "repo": str(repo),
        "remote": run('remote', 'get-url', 'origin'),
        "branch": run('branch', '--show-current'),
        "latest": {},
        "uncommitted": 0, "ahead": 0, "behind": 0,
        "in_sync": True,
    }
    # 最新 commit（让 git 输出 6 行，再用 NUL 分隔）
    # 用 0x1f (unit separator) 兼容普通字符
    SEP = chr(0x1f)
    fmt = f'%H{SEP}%h{SEP}%an{SEP}%ae{SEP}%ad{SEP}%s'
    raw = run('log', '-1', f'--pretty=format:{fmt}')
    if raw:
        parts = raw.split(SEP)
        if len(parts) >= 6:
            info["latest"] = {
                "hash": parts[0], "short": parts[1],
                "author": parts[2], "email": parts[3],
                "date": parts[4], "subject": parts[5],
            }
    # 未提交修改文件数
    porcelain = run('status', '--porcelain')
    if porcelain is not None:
        info["uncommitted"] = len([l for l in porcelain.splitlines() if l.strip()])
    # local vs upstream ahead/behind（@u = upstream tracking）
    rev = run('rev-list', '--left-right', '--count', 'HEAD...@{u}')
    if rev:
        try:
            left, right = rev.split('\t')
            info["behind"] = int(left.strip())
            info["ahead"] = int(right.strip())
        except Exception:
            pass
    # 最近 N 个 commits（默认 5）
    commits = []
    raw = run('log', '-5', f'--pretty=format:{fmt}')
    if raw:
        for line in raw.split(chr(10)):
            parts = line.split(SEP)
            if len(parts) >= 6:
                commits.append({
                    "hash": parts[0], "short": parts[1],
                    "author": parts[2], "email": parts[3],
                    "date": parts[4], "subject": parts[5],
                })
    info["recent_commits"] = commits
    # 是否同步
    info["in_sync"] = (info["ahead"] == 0 and info["behind"] == 0 and info["uncommitted"] == 0)
    return info


@app.get("/api/git/info")
def api_git_info():
    """当前 git 仓库同步状态：远程/分支/最新 commit/未提交/落后数。"""
    return _git_info()


@app.get("/api/system/stats")
def api_system_stats():
    """后端进程级运行时统计：CPU / 内存 / WS 客户端 / 启动时间。"""
    import os, time
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        with proc.oneshot():
            cpu = proc.cpu_percent(interval=None)
            mem = proc.memory_info()
            create_time = proc.create_time()
            threads = proc.num_threads()
        return {
            "ok": True,
            "pid": os.getpid(),
            "uptime": time.time() - create_time,
            "cpu_percent": cpu,
            "rss_mb": mem.rss / 1048576,
            "vms_mb": mem.vms / 1048576,
            "threads": threads,
            "ws_clients": len(_ws_clients),
            "running_tasks": sum(1 for r in manager.status() if r.get("running")),
            "ts": time.time(),
        }
    except ImportError:
        # psutil 不可用时降级到基础信息
        return {
            "ok": True, "pid": os.getpid(), "uptime": None,
            "cpu_percent": None, "rss_mb": None, "vms_mb": None,
            "threads": None, "ws_clients": len(_ws_clients),
            "running_tasks": sum(1 for r in manager.status() if r.get("running")),
            "ts": time.time(), "psutil_missing": True,
        }


@app.get("/api/camera/stream")
async def camera_stream(
    topic: str = Query("camera/color/image_raw", description="ROS2 图像话题名"),
    width: int = Query(640, description="最大宽度（等比缩放）"),
    quality: int = Query(80, ge=30, le=95, description="JPEG 质量 30-95"),
    fps: int = Query(15, ge=1, le=60, description="帧率限制 1-60"),
):
    """MJPEG 推流：multipart/x-mixed-replace，客户端断开自动停止。
    支持 query 参数：topic（话题名）、width（宽度）、quality（质量）、fps（帧率）。"""
    if not ros_available:
        raise HTTPException(503, "ROS2 不可用（请确认后端由 run.sh 启动）")

    from ros_bridge import StreamContext
    ctx = StreamContext(topic=topic, width=width, quality=quality, fps=fps)
    if not ctx.start():
        raise HTTPException(503, f"无法订阅话题: {topic}（检查话题名是否正确）")

    async def gen():
        try:
            idle = 0
            while True:
                frame = ctx.latest_frame()
                if frame is None:
                    idle += 1
                    if idle > 50:
                        break
                    await asyncio.sleep(0.2)
                    continue
                idle = 0
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + frame[0]
                    + b"\r\n"
                )
                await asyncio.sleep(1.0 / fps)
        finally:
            ctx.stop()

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/ros/image_topics")
def api_ros_image_topics():
    """列出 ROS 图中所有 sensor_msgs/Image 话题（供前端选择相机话题用）"""
    if not ros_available:
        return {"ok": False, "error": "ROS2 不可用", "topics": []}
    from ros_bridge import list_image_topics
    topics = list_image_topics()
    return {"ok": True, "topics": topics}


@app.post("/api/cmd_vel")
def api_cmd_vel(body: CmdVelBody):
    if not bridge.ensure_started():
        raise HTTPException(503, "ROS2 不可用（请确认后端由 run.sh 启动）")
    bridge.publish(body.linear, body.angular)
    return {"ok": True, "linear": body.linear, "angular": body.angular}


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stopped = {"flag": False}

    def _on_log(task_id: str, entry: object):
        loop.call_soon_threadsafe(queue.put_nowait, {"task_id": task_id, "entry": entry})

    manager.on_log(_on_log)
    # 记录活跃 WS 客户端
    _ws_clients.add(websocket)
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
                await websocket.send_json(item)
            except asyncio.TimeoutError:
                await websocket.send_json({"ping": True})  # 心跳，防断线
    except WebSocketDisconnect:
        pass
    finally:
        stopped["flag"] = True
        _ws_clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
