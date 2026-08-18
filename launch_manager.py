"""launch 进程管理器：start/stop/status/日志（基于 subprocess + SIGINT 优雅停止）。"""
import os
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

LOG_LINES_PER_TASK = 2000  # 内存环形日志上限


@dataclass
class RunningTask:
    id: str
    cmd: str
    proc: subprocess.Popen
    started_at: float = field(default_factory=time.time)
    stopped: bool = False
    exit_code: Optional[int] = None


class LaunchManager:
    def __init__(self, workspace: str, ros_distro: str = "humble"):
        self.workspace = workspace
        self.ros_distro = ros_distro
        self._tasks: dict[str, RunningTask] = {}
        self._logs: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._listeners: list[Callable[[str, object], None]] = []  # (task_id, entry)
        self._seq = 0

    # ---- 日志 ----
    def on_log(self, listener: Callable[[str, object], None]):
        self._listeners.append(listener)

    @staticmethod
    def parse_log_line(line: str) -> dict:
        """解析 ROS2/RCL 日志行，提取 level 与 node。

        常见格式：
          [INFO 1726479491.123] [node_name]: message
          [INFO] [1726479491.123] [node]: message
          [WARN] [node]: message
        非标准行则 level='info'、node=None。
        """
        line = line.rstrip("\n")
        ts = None
        level = "info"
        node = None
        # 形式一：[LEVEL ts]
        import re
        m = re.match(r'^\s*\[(?P<level>[A-Z]+)\s+(?P<ts>\d+\.\d+)\]\s*\[(?P<node>[^\]]+)\]:\s*(?P<msg>.*)$', line)
        if m:
            level = m.group("level").lower()
            ts = float(m.group("ts"))
            node = m.group("node")
            line = m.group("msg")
        else:
            m = re.match(r'^\s*\[(?P<level>[A-Z]+)\]\s*\[(?P<ts>\d+\.\d+)\]\s*\[(?P<node>[^\]]+)\]:\s*(?P<msg>.*)$', line)
            if m:
                level = m.group("level").lower()
                ts = float(m.group("ts"))
                node = m.group("node")
                line = m.group("msg")
            else:
                m = re.match(r'^\s*\[(?P<level>[A-Z]+)\]\s*\[(?P<node>[^\]]+)\]:\s*(?P<msg>.*)$', line)
                if m:
                    level = m.group("level").lower()
                    node = m.group("node")
                    line = m.group("msg")
        if level not in ("debug", "info", "warn", "error", "fatal"):
            level = "info"
        return {"line": line, "level": level, "node": node, "ts": ts}

    def _push_log(self, task_id: str, line: str):
        self._seq += 1
        entry = self.parse_log_line(line)
        entry["task_id"] = task_id
        entry["seq"] = self._seq
        with self._lock:
            q = self._logs.setdefault(task_id, deque(maxlen=LOG_LINES_PER_TASK))
            q.append(entry)
        for cb in self._listeners:
            try:
                cb(task_id, entry)
            except Exception:
                pass

    def get_log(self, task_id: str, tail: int = 200, node: str | None = None,
                level: str | None = None) -> list:
        """获取日志；支持按 node 与 level 过滤（level 取 debug<=info<=warn<=error<=fatal）。"""
        with self._lock:
            q = self._logs.get(task_id, deque())
            items = list(q)
        order = {"debug": 0, "info": 1, "warn": 2, "error": 3, "fatal": 4}
        if node:
            items = [i for i in items if (i["node"] or "") == node]
        if level and level in order:
            thresh = order[level]
            items = [i for i in items if order.get(i["level"], 1) >= thresh]
        return items[-tail:]

    def available_filter(self) -> dict:
        """返回可用的 node 与 level 过滤器维度。"""
        nodes, levels = set(), set()
        with self._lock:
            for q in self._logs.values():
                for i in q:
                    if i.get("node"):
                        nodes.add(i["node"])
                    if i.get("level"):
                        levels.add(i["level"])
        return {"nodes": sorted(nodes), "levels": sorted(levels, key=lambda x: ["debug","info","warn","error","fatal"].index(x))}

    # ---- 命令构建 ----
    @staticmethod
    def build_command(task: dict, devices_vars: dict, overrides: dict) -> str:
        """展开 choices + params 占位符，组装 ros2 launch 命令行。"""
        kind = task.get("kind", "launch")
        if kind == "build":
            return "colcon build"
        if kind == "echo":
            # 自检/调试用：长跑任务，验证 start/stop 生命周期
            return "echo [echo-task] running && sleep 30"
        if kind == "ros2run":
            # ros2 run <package> <executable> [args...]（args 支持 $VAR 设备变量展开）
            cmd = "ros2 run %s %s" % (task["package"], task.get("executable", ""))
            for a in task.get("args", []):
                for var, val in devices_vars.items():
                    a = a.replace("$" + var, str(val))
                cmd += " " + a
            return cmd

        # 1) choices：主键选中值 + option 附加元数据（engine_pkg 等）
        choice_vals: dict = {}
        opt_meta: dict = {}
        pass_as_param: dict = {}  # 需要透传为 launch 参数的 choice（如 voice 的 language）
        for ch in task.get("choices", []):
            key = ch["key"]
            sel = overrides.pop(key, None) or ch.get("default")
            opt = next((o for o in ch["options"] if o["value"] == sel), ch["options"][0])
            choice_vals[key] = opt["value"]
            for k, v in opt.items():
                if k not in ("value", "label"):
                    opt_meta[k] = v
            if ch.get("pass_as_param"):
                pass_as_param[key] = opt["value"]

        # 2) 展开 package / launch 里的 {key} 占位符（优先 option 元数据）
        def _expand(tpl: str) -> str:
            for k, v in {**choice_vals, **opt_meta}.items():
                tpl = tpl.replace("{%s}" % k, str(v))
            return tpl

        pkg = _expand(task["package"])
        launch_name = _expand(task["launch"])

        # 3) 组装参数：仅 pass_as_param 的 choices + params（$VAR 展开 + overrides 覆盖）
        def expand_var(v: str) -> str:
            for var, val in devices_vars.items():
                v = v.replace("$" + var, str(val))
            return v

        args = []
        for key, val in pass_as_param.items():
            args.append("%s:=%s" % (key, val))
        for key, meta in task.get("params", {}).items():
            val = expand_var(str(overrides.get(key, meta.get("default", ""))))
            if val == "":
                continue  # 空值参数不传（如 namespace 默认空）
            args.append("%s:=%s" % (key, val))

        # 引擎无雷达时去掉 lidar 参数（tensorflow 不接 lidar）
        if opt_meta.get("with_lidar") is False:
            args = [a for a in args if not a.startswith("lidar_type_tel:=")]

        return "ros2 launch %s %s %s" % (pkg, launch_name, " ".join(args))

    # ---- 生命周期 ----
    def start(self, task: dict, devices_vars: dict, overrides: dict | None = None) -> dict:
        overrides = dict(overrides or {})
        task_id = task["id"]
        with self._lock:
            old_rt = self._tasks.get(task_id)
            if old_rt and old_rt.proc.poll() is None:
                return {"ok": False, "error": "任务已在运行"}
            if old_rt:
                self._tasks.pop(task_id)  # 旧条目已退出，允许重新启动

        # 工具类任务
        if task.get("kind") == "kill":
            self.kill_all()
            return {"ok": True, "id": task_id, "pid": 0, "cmd": "kill_all_ros"}

        cmd = self.build_command(task, devices_vars, overrides)
        kind = task.get("kind", "launch")
        if kind == "launch":
            setup = (
                "source /opt/ros/%s/setup.bash && source %s/install/setup.bash && "
                "exec %s" % (self.ros_distro, self.workspace, cmd)
            )
        else:
            # 工具类任务（build/echo 等）：不走 exec；先 source ROS 再执行
            setup = (
                "source /opt/ros/%s/setup.bash && cd %s && %s"
                % (self.ros_distro, self.workspace, cmd)
            )
        proc = subprocess.Popen(
            ["bash", "-c", setup],
            cwd=self.workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,  # 独立进程组，便于整组停止
        )
        rt = RunningTask(id=task_id, cmd=cmd, proc=proc)
        with self._lock:
            self._tasks[task_id] = rt

        def _reader():
            assert proc.stdout is not None
            for line in proc.stdout:
                self._push_log(task_id, line.rstrip("\n"))
            code = proc.wait()
            rt.exit_code = code
            rt.stopped = True
            self._push_log(task_id, "[launch-manager] 进程退出, exit=%s" % code)

        threading.Thread(target=_reader, daemon=True).start()
        return {"ok": True, "id": task_id, "pid": proc.pid, "cmd": cmd}

    def stop(self, task_id: str) -> dict:
        with self._lock:
            rt = self._tasks.get(task_id)
        if not rt or rt.proc.poll() is not None:
            return {"ok": True, "already": True}
        proc = rt.proc
        self._push_log(task_id, "[launch-manager] 发送 SIGINT 优雅停止...")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except ProcessLookupError:
            pass
        # 最多等 10s，超时 SIGTERM
        for _ in range(50):
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        if proc.poll() is None:
            self._push_log(task_id, "[launch-manager] 超时，发送 SIGTERM")
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._push_log(task_id, "[launch-manager] 强制 SIGKILL")
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        return {"ok": True}

    def status(self) -> list[dict]:
        with self._lock:
            items = list(self._tasks.items())
        out = []
        for tid, rt in items:
            code = rt.proc.poll()
            if code is not None and rt.exit_code is None:
                rt.exit_code = code
                rt.stopped = True
            out.append({
                "id": rt.id,
                "pid": rt.proc.pid,
                "running": code is None,
                "exit_code": rt.exit_code,
                "started_at": rt.started_at,
                "cmd": rt.cmd,
            })
        return out

    def kill_all(self) -> dict:
        """等同 onekey 菜单 101：清掉所有 ros 进程。"""
        self._push_log("kill_nodes", "[launch-manager] kill 所有 ros 进程")
        os.system(
            "ps aux | grep -E 'ros2|/ros/|ros_' | grep -v grep | "
            "grep -v spark_console | awk '{print $2}' | xargs -r kill -9"
        )
        return {"ok": True}

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            rt = self._tasks.get(task_id)
        return bool(rt and rt.proc.poll() is None)
