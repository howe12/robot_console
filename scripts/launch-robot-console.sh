#!/usr/bin/env bash
# robot-console desktop launcher wrapper
# - 启动 run.sh（ROS2 + venv + uvicorn）
# - 等服务 ready
# - 打印 LAN IP 给用户
# - 不打开浏览器（用户在手机/电脑访问）
# - 不退出（service 持续运行；用户 Ctrl+C 终止）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 调用项目的 run.sh（保留 IP 打印 + uvicorn 启动）
exec ./run.sh
