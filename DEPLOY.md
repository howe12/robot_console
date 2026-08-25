# 部署指南 · SPARK Robot Console

本指南面向**新设备**的完整部署流程（Ubuntu 22.04 + ROS2 Humble）。
适用于把 Spark 控制台（本仓库）部署到另一台机器人或开发机上。

> 当前版本：**v1.0.0**
> 仓库：`https://github.com/howe12/robot_console.git`（SSH: `git@github.com:howe12/robot_console.git`）

---

## ⚠️ 部署前提（先读懂，避免踩坑）

1. **本仓库只含控制台本身，不含机器人 ROS 环境。** 控制台要真正能启动任务 / 相机推流 / 遥控，
   新设备上**必须**具备：
   - ROS2 **Humble**（`/opt/ros/humble`，Desktop-Full）
   - 机器人 ROS2 工作空间（本项目默认在 `/home/spark/Music/spark_humble`，
     包含 spark_base / spark_driver 等驱动包及其 `install/` 目录）
2. **两处路径写死**，新设备路径不同时必须修改：
   - `run.sh:10`：`WS="/home/spark/Music/spark_humble"`
   - `spark_tasks.yaml:9`：`workspace: /home/spark/Music/spark_humble`
   - 这两个文件都入库，改动会出现在 git 状态里（可提交，也可只在目标机本地改）。
3. **前端构建产物不入库**：`static/index.html` 入库，但 `static/assets/*`（JS/CSS bundle）在
   `.gitignore` 中。拉取源码后需重新构建，或用已构建的产物一起拷贝。
4. **默认无认证**，仅适合局域网；放到公网前必须加固（见下文）。

---

## ① 系统环境准备（一次性）

```bash
sudo apt update

# Python 3.10 + venv + git
sudo apt install -y python3 python3-venv python3-pip git curl

# ROS2 Humble（若新设备也需要驱动机器人）
# 按 ROS2 Humble 官方文档安装 Desktop-Full；
# 再把机器人的 spark_humble 工作空间（含 install/）放到 ~/Music/spark_humble

# 前端构建工具（仅当需要从源码构建前端时才需要；Node 18+）
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm
```

---

## ② 获取代码

```bash
cd ~

# 方式 A：HTTPS（网络可访问 GitHub 时）
git clone https://github.com/howe12/robot_console.git

# 方式 B：SSH（推荐，可绕过 https 代理问题；需先配好 SSH key，见 ③）
git clone git@github.com:howe12/robot_console.git
```

---

## ③ 配置 GitHub SSH key（走 SSH 时必做）

```bash
# 生成 key（无则生成）
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# 把公钥内容复制到 GitHub → Settings → SSH and GPG keys → New SSH key
cat ~/.ssh/id_rsa.pub

# 验证
ssh -T git@github.com
# 看到 "Hi howe12! You've successfully authenticated" 即成功
```

> **为什么推荐 SSH**：如果设备环境变量里设置了失效的 http(s) 代理（如
> `http_proxy=http://192.168.100.122:7897`），`https://github.com` 的 git 操作会失败，
> 而 SSH 协议不受 `http_proxy` 影响，直连 443/22 通常更可靠。
> 仓库里 `origin` 已设置为 SSH 方式：
> ```bash
> git remote -v   # 应显示 git@github.com:howe12/robot_console.git
> ```

---

## ④ 对齐工作空间路径

**方案 A（推荐）**：让新设备的工作空间与写死路径一致，无需改代码。

```bash
mkdir -p ~/Music
# 把 spark_humble（含 install/）放到 ~/Music/spark_humble
```

**方案 B**：路径不同时修改两处：

```bash
nano run.sh                 # 改  WS="/你的/spark_humble"  （约第 10 行）
nano spark_tasks.yaml       # 改  workspace: /你的/spark_humble  （第 9 行）
```

---

## ⑤ 启动

```bash
cd ~/spark_console
./run.sh
```

`run.sh` 自动完成：
1. `source /opt/ros/humble/setup.bash` + 工作空间 `install/setup.bash`（rclpy/cv_bridge 注入 venv）
2. 无 `.venv` 时自动创建并 `pip install -r requirements.txt`（fastapi / uvicorn / websockets / pyyaml / psutil）
3. 检测 8080 端口占用，防多开
4. 打印局域网访问地址后启动 uvicorn（`0.0.0.0:8080`）

访问：

- 本机：`http://127.0.0.1:8080`
- 局域网：`http://<机器人IP>:8080`（`hostname -I` 查看 IP）

**防火墙放行**（如连不上）：

```bash
sudo ufw allow 8080/tcp          # UFW
sudo firewall-cmd --permanent --add-port=8080/tcp && sudo firewall-cmd --reload   # firewalld
```

---

## ⑥ 修改前端源码 / 重新构建（可选）

```bash
cd web
pnpm install
pnpm build          # vite 构建，产物输出到 ../static/ 并更新 index.html 的 bundle 引用
```

---

## ⑦ 以 systemd 服务常驻（可选）

```ini
# /etc/systemd/system/spark-console.service
[Unit]
Description=Spark Robot Console
After=network.target

[Service]
User=spark
WorkingDirectory=/home/spark/spark_console
ExecStart=/home/spark/spark_console/run.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now spark-console
```

---

## ⑧ 公网部署安全加固（务必）

默认**无认证**——局域网内任何设备都能控制机器人（含各任务启停、`/api/cmd_vel`、`/api/stop-all`）。
放公网前必须：

- 前置 **nginx + basic auth**，或 **oauth2-proxy**；
- 必要时对危险接口（`/api/cmd_vel`、`/api/stop-all`、`/api/tasks/*/start`）单独加白名单/鉴权。

---

## 🔍 常见问题排查

| 现象 | 处理 |
|---|---|
| 启动报 `rclpy` / `cv_bridge` 找不到 | 必须用 `./run.sh` 启动（它负责 source ROS2）；不要直接敲 `uvicorn` |
| `/api/adapter/config` 话题为空、相机无画面 | 机器人驱动未启动，先在控制台「Tasks」启动 bringup / teleop 任务 |
| 8080 被占用 | `pkill -f 'uvicorn main:ap[p]'` 后重新 `./run.sh` |
| 页面空白 / 控制无响应 | 浏览器强制刷新（`Ctrl+Shift+R`）加载新 bundle；查 `~/spark_console/client_errors.log` |
| 方向键与运动相反 | 已按驱动约定（正角速度=左转）写死，若硬件接线镜像需调 `web/src/views/Visual.vue` 的 `desiredVel()` 并重新构建 |
| git push/fetch 失败 | 检查代理：`env \| grep -i proxy`，改用 SSH 方式（见 ②③） |
| 前端页面 404（资源没加载） | 确认 `static/assets/` 下存在 `index.html` 引用的 bundle；缺失则执行 ⑥ 重新构建 |

---

## 版本说明

| 版本 | 说明 |
|---|---|
| v0.6 | 初版功能（引入仓库同步卡、adapter 自动发现、任务模板等） |
| v1.0 | 修复 Visual 页空白崩溃、`/api/cmd_vel` 500、A/D 转向反、急停不刹停、git 同步统计错误；连续遥操作循环；全局错误上报 |