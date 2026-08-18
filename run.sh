#!/usr/bin/env bash
# Spark 控制台后端启动脚本
# 需要 ROS2 环境（rclpy/cv_bridge）供相机推流与遥控使用
set -e
cd "$(dirname "$0")"

# 1) ROS2 + 工作空间环境（rclpy 等 python 包通过 PYTHONPATH 注入 venv）
if [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
    WS="/home/spark/Music/spark_humble"
    if [ -f "$WS/install/setup.bash" ]; then
        source "$WS/install/setup.bash"
    fi
else
    echo "[run.sh] 警告: 未找到 /opt/ros/humble，相机/遥控接口将不可用" >&2
fi

# 2) venv
if [ ! -d .venv ]; then
    echo "[run.sh] 创建 venv 并安装依赖..."
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
fi
source .venv/bin/activate

# 3) 防双开：8080 已被监听则退出（多实例会导致 launch 状态错乱/幽灵停止）
if ss -tlnp 2>/dev/null | grep -q ":8080 "; then
    echo "[run.sh] 错误: 8080 已被占用（可能有旧实例在跑），请先: pkill -f 'uvicorn main:ap[p]'" >&2
    exit 1
fi

echo "[run.sh] 启动后端 http://0.0.0.0:8080"
exec uvicorn main:app --host 0.0.0.0 --port 8080 "$@"
