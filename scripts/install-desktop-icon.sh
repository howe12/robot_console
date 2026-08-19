#!/usr/bin/env bash
# Robot Console 桌面图标安装脚本
# - 把 .desktop 复制到 ~/.local/share/applications/ 和 ~/Desktop/
# - 设置可执行权限
# - 刷新桌面数据库（让新图标立即出现）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

DESKTOP="$HOME/.local/share/applications/robot_console.desktop"
DESKTOP_FILE="$PROJECT_DIR/scripts/robot_console.desktop"

mkdir -p "$HOME/.local/share/applications"
cp "$DESKTOP_FILE" "$DESKTOP"
cp "$DESKTOP_FILE" "$HOME/Desktop/robot_console.desktop"
chmod +x "$DESKTOP" "$HOME/Desktop/robot_console.desktop"

# 刷新桌面数据库（GNOME/XFCE 需要）
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi
if command -v xdg-desktop-menu >/dev/null; then
    xdg-desktop-menu forceupdate || true
fi

echo ""
echo "✓ Robot Console 桌面图标已安装："
echo "  应用菜单: $DESKTOP"
echo "  桌面:      $HOME/Desktop/robot_console.desktop"
echo ""
echo "  如未显示，注销/重新登录桌面环境。"
