# SPARK Robot Console · ROS2 机器人前后端管理系统

基于 ROS2（humble）机器人的可视化前后端管理系统，为 NXROBO Spark 机器人定制，
但同样适用于任何 ROS2 机器人。FastAPI 后端 + Vue3 + Vite 前端，**本地一键运行**。

![架构](https://img.shields.io/badge/ROS2-Humble-blue) ![后端](https://img.shields.io/badge/Backend-FastAPI-green) ![前端](https://img.shields.io/badge/Frontend-Vue3%20%2B%20Vite-brightgreen) ![Python](https://img.shields.io/badge/Python-3.10+-yellow)

---

## ✨ 主要功能

### 📊 系统状态（自动 5s 刷新）
- 系统资源：CPU / 内存 / 磁盘 / 负载 / 运行时长
- 外接设备：相机 / 底盘 / 雷达 / 机械臂（基于 `lsusb` + `/opt/lidar.txt`）
- 底盘 & 传感器实时读数：航向角、里程、线速度、IMU、防撞/跌落/轮毂过流
- ROS2 图：节点 / 话题 / 服务 / 动作
- 软件版本：ROS 发行版、`ROS_DOMAIN_ID`、工作空间包数

### 🚀 机器人功能控制
- **精选任务**（YAML 配置）：键鼠遥控、跟随、建图（2D/3D）、导航（2D/3D）、机械臂、深度学习检测、语音控制等
- **自动分析 ROS2 工作空间**：扫描 `install/<pkg>/share/<pkg>/launch` 自动发现 40+ launch 文件
- 每个功能显示完整**启动命令**（带复制按钮）+ **launch 源码查看**（含绝对路径）
- **互斥保护**：已有任务运行时禁止启动其他任务，避免硬件冲突
- 全页面「🛑 紧急停止」按钮：一键停掉所有任务 + kill 全部 ROS 节点

### 📜 实时监控（rqt 风格）
- **ROS2 拓扑图**（dagre 分层有向图）：节点按功能包着色、可缩放平移、点击聚焦高亮
- **终端日志**：按任务 / 节点 / 日志等级过滤，实时滚动
- 新任务启动时插入 **醒目分割线** 区分
- 一键清除当前日志

### 🖥️ 可视化控制
- 相机 MJPEG 实时推流（`camera/color/image_raw`）
- 速度遥控面板：WASD / 方向键 / 触屏按钮（持续发布 `/cmd_vel`）
- **Foxglove 3D 可视化内嵌**（端口 8765）

---

## 📦 目录结构

```
spark_console/
├── 后端（Python / FastAPI）
│   ├── main.py              # FastAPI 主入口、API 路由
│   ├── system_monitor.py    # 系统健康 + rclpy 传感器订阅
│   ├── workspace_analysis.py # ROS2 工作空间自动分析
│   ├── launch_manager.py    # launch 进程生命周期 + 日志解析
│   ├── ros_bridge.py        # 相机 MJPEG + /cmd_vel 发布
│   ├── device_detect.py     # lsusb 设备检测
│   ├── spark_tasks.yaml     # 精选任务清单
│   ├── run.sh               # 启动脚本（source ROS2 环境）
│   └── requirements.txt
│
├── 前端源码（Vue3 + Vite）
│   └── web/
│       ├── index.html
│       ├── vite.config.js
│       ├── package.json
│       └── src/
│           ├── main.js
│           ├── App.vue
│           ├── api.js
│           ├── style.css
│           └── views/
│               ├── Dashboard.vue       # 系统状态
│               ├── Tasks.vue           # 机器人功能控制
│               ├── Logs.vue            # 实时监控（含拓扑图）
│               ├── TopologyView.vue    # 拓扑图容器
│               ├── TopoCanvas.vue      # dagre SVG 画布
│               └── Visual.vue          # 可视化控制
│
├── static/                  # 构建后的前端产物（被 FastAPI 直接托管）
├── .venv/                   # Python 虚拟环境（已忽略）
└── run.sh                   # 一键启动
```

---

## 🚀 安装与运行

### 环境要求
- **操作系统**：Ubuntu 22.04+（其他发行版需自行调整设备检测路径）
- **ROS2**：Humble（Desktop-Full Install）
- **Python**：3.10+
- **Node.js**：18+（仅开发前端源码时需要；构建产物已内置到 `static/`）
- **机器人**：NXROBO Spark 或任意 ROS2 兼容机器人（默认话题配置按 Spark 调优）

### 快速启动（8080 端口）

```bash
# 1. 克隆仓库
git clone https://github.com/<your-name>/robot_console.git
cd robot_console

# 2. 启动（脚本会自动 source ROS2 + 工作空间 + 创建 venv）
./run.sh
```

`run.sh` 会自动：
1. source `/opt/ros/humble/setup.bash` 和 `~/Music/spark_humble/install/setup.bash`（路径可在脚本内调整）
2. 若 `.venv` 不存在则创建并 `pip install -r requirements.txt`
3. 检测 8080 端口占用（防止多开冲突）
4. 启动 uvicorn：`http://0.0.0.0:8080`

打开浏览器访问 **`http://127.0.0.1:8080`** 即可。

### 局域网访问（手机/平板/另一台电脑）

后端默认绑定 `0.0.0.0:8080`，同一局域网的**任何设备**都能直接访问：

1. 找机器人在 LAN 里的 IP：
   ```bash
   hostname -I          # 例如: 192.168.100.143
   ```
2. 在手机/平板/电脑浏览器输入：
   ```
   http://192.168.100.143:8080
   ```
3. **无需 VNC**——纯 HTTP，浏览器原生渲染，体验远优于 VNC 转发。

**防火墙配置**（如果连不上）：
```bash
# UFW（Ubuntu）
sudo ufw allow 8080/tcp

# firewalld（CentOS / RHEL）
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload

# iptables（手动）
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
```

**安全提示**：
- 默认**无认证**——任何 LAN 用户都能控制机器人！
- 部署到公网前必须加密码（建议加 `oauth2-proxy` 或在前置 nginx 加 basic auth）
- 局域网内通常安全，但注意公司网环境

### 手动启动（调试用）

```bash
source /opt/ros/humble/setup.bash
source ~/Music/spark_humble/install/setup.bash   # 你的工作空间

cd spark_console
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 修改前端源码

```bash
cd web
npm install
npm run build   # 构建产物输出到 ../static/
```

开发模式（带热更新）：
```bash
cd web
npm run dev     # 默认 5173 端口，已配置代理到 8080
```

---

## ⚙️ 配置

### 工作空间路径
默认读取 Spark 工作空间：`/home/spark/Music/spark_humble`。
若路径不同，修改 `spark_tasks.yaml` 顶部：

```yaml
workspace: /your/path/to/ros2_ws
```

### 精选任务清单
编辑 `spark_tasks.yaml` 的 `tasks:` 段，每项结构：

```yaml
- id: teleop                    # 唯一 ID
  menu: 1                       # onekey.sh 菜单号（仅注释用）
  name: "键盘遥控"
  desc: "wsad 前后左右移动"
  package: spark_teleop         # ROS2 包名
  launch: teleop.launch.py      # launch 文件名（支持 {key} 占位符）
  enabled: true
  params:                       # 启动参数（占位符 $CAMERATYPE 等会用设备检测结果展开）
    camera_type_tel: {default: "$CAMERATYPE"}
    lidar_type_tel:  {default: "$LIDARTYPE"}
  choices:                      # 动态选择项（如 SLAM 类型）
    - key: slam_type
      label: "SLAM 方式"
      options:
        - {value: gmapping, label: "gmapping"}
        - {value: cartographer, label: "cartographer"}
      default: gmapping
```

### 设备检测
`device_detect.py` 默认通过 `lsusb` 的 `vendor:product` 匹配：

```python
camera:
  vendors:
    "2bc5:0403": astrapro
    "8086:0b07": d435
arm:
  vendors:
    "2341:0042": uarm
base:
  vendors:
    "1a86:7523": spark_base
lidar:
  type_file: /opt/lidar.txt
  usb_id: "10c4:ea60"
```

---

## 🔌 主要 API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/system/status` | 系统健康快照（CPU/内存/设备/传感器/ROS 图） |
| GET | `/api/workspace` | 自动扫描的工作空间功能 |
| GET | `/api/topology` | ROS2 拓扑（节点↔话题关系，用于 rqt 风格图） |
| GET | `/api/tasks` | 精选任务清单（含启动命令、launch 路径） |
| POST | `/api/tasks/{id}/start` | 启动任务（互斥：有其他任务运行时拒绝） |
| POST | `/api/tasks/custom` | 自定义启动（包+launch+参数） |
| POST | `/api/tasks/{id}/stop` | 停止任务（SIGINT 优雅停止） |
| POST | `/api/stop-all` | **紧急停止**：停所有任务 + kill ROS 节点 |
| GET | `/api/launch/source?package=&launch=` | 读取 launch 文件源码（前端弹窗用） |
| WS | `/ws/logs` | 实时日志流（结构化：level/node/line） |
| GET | `/api/camera/stream` | MJPEG 相机推流 |
| POST | `/api/cmd_vel` | 发布速度控制 |
| GET | `/` | 前端 SPA |

完整 Swagger 文档：运行后访问 `http://127.0.0.1:8080/docs`。

---

## 🛠️ 技术栈

**后端**
- FastAPI + Uvicorn（异步 Web 框架）
- rclpy（ROS2 Python 客户端，订阅传感器话题）
- PyYAML、psutil、cv_bridge、opencv-python-headless
- subprocess（启动 ros2 launch 进程）

**前端**
- Vue 3 + Composition API
- Vite 5（构建工具）
- dagre.js（DAG 分层布局）
- d3-zoom（缩放平移）
- 纯 SVG 渲染（无重 UI 框架依赖）

---

## 🐛 故障排查

| 现象 | 原因 / 解决 |
|---|---|
| 后端启动报 `rclpy` 找不到 | 必须用 `./run.sh` 启动，让脚本 `source /opt/ros/humble/setup.bash` |
| 传感器数据为空 | 启动底盘驱动任务（如 spark_base.launch.py），sensor monitor 依赖实际 publisher |
| 相机无画面 | 1) 启动相机驱动任务；2) 话题是否 `camera/color/image_raw` |
| 8080 端口占用 | `pkill -f 'uvicorn main:ap[p]'` 或修改 `run.sh` 端口 |
| 拓扑图打不开 | 启动任何 ROS2 节点后才有内容 |
| `已有功能正在运行` | 设计如此：互斥保护。先停止现有任务，或用「🛑 紧急停止」 |

---

## 📝 License

MIT

---

## 🙏 致谢

- [NXROBO Spark](https://www.nxrobo.com) — 机器人硬件与 ROS2 驱动
- [ROS2 humble](https://docs.ros.org/en/humble/) — 机器人中间件
- [dagre.js](https://github.com/dagrejs/dagre) — DAG 分层布局
- [d3-zoom](https://github.com/d3/d3-zoom) — 缩放平移