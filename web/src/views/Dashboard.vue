<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'

const data = ref(null)
const error = ref('')
const lastFmt = ref('')
let timer = null

function fmtBytes(b) {
  if (b == null) return '-'
  const g = b / 1073741824
  if (g >= 1) return g.toFixed(2) + ' GB'
  return (b / 1048576).toFixed(0) + ' MB'
}
function fmtUptime(s) {
  if (s == null) return '-'
  const d = Math.floor(s / 86400)
  const h = Math.floor(s % 86400 / 3600)
  const m = Math.floor(s % 3600 / 60)
  return d > 0 ? `${d}天 ${h}时 ${m}分` : `${h}时 ${m}分`
}

async function load() {
  try {
    const d = await api.systemStatus()
    data.value = d
    lastFmt.value = new Date(d.ts * 1000).toLocaleTimeString()
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))

const deviceOrder = [
  ['camera', '相机'], ['base', '底盘'], ['lidar', '雷达'], ['arm', '机械臂']
]
</script>

<template>
  <div>
    <div class="page-title">
      <h2>📊 系统状态</h2>
      <small>每 5 秒自动刷新 · 最后更新 {{ lastFmt }}</small>
      <div class="spacer"></div>
      <button class="btn" @click="load">↻ 刷新</button>
    </div>
    <div v-if="error" class="card warn">加载失败：{{ error }}</div>

    <template v-if="data">
      <!-- 资源指标 -->
      <div class="grid grid-4" style="margin-bottom:14px">
        <div class="card metric">
          <div class="val">{{ (data.system.cpu_percent || 0).toFixed(1) }}%</div>
          <div class="label">CPU 使用率</div>
          <div class="bar"><i :style="{ width: data.system.cpu_percent + '%' }"></i></div>
        </div>
        <div class="card metric">
          <div class="val">{{ (data.system.mem.percent || 0).toFixed(0) }}%</div>
          <div class="label">内存 {{ fmtBytes(data.system.mem.used) }} / {{ fmtBytes(data.system.mem.total) }}</div>
          <div class="bar"><i :style="{ width: data.system.mem.percent + '%' }"></i></div>
        </div>
        <div class="card metric">
          <div class="val">{{ (data.system.disk.percent || 0).toFixed(0) }}%</div>
          <div class="label">磁盘 {{ fmtBytes(data.system.disk.free) }} 可用</div>
          <div class="bar"><i :style="{ width: data.system.disk.percent + '%' }"></i></div>
        </div>
        <div class="card metric">
          <div class="val" style="font-size:20px">{{ data.system.hostname }}</div>
          <div class="label">运行时长 {{ fmtUptime(data.system.uptime) }}</div>
        </div>
      </div>

      <div class="grid grid-2">
        <!-- 外接设备 -->
        <div class="card">
          <h3>🔌 外接设备</h3>
          <div class="dev-list">
            <div v-for="[key, name] in deviceOrder" :key="key" class="dev-row">
              <span class="light" :class="data.devices[key].connected ? 'ok' : 'bad'"></span>
              <span class="name">{{ name }}</span>
              <span class="detail">{{ data.devices[key].connected ? (data.devices[key].type || '已连接') : '未连接' }}</span>
            </div>
          </div>
          <h3 style="margin-top:14px">💻 软件环境</h3>
          <table>
            <tr><td>ROS 发行版</td><td>{{ data.software.ros_distro }}</td></tr>
            <tr><td>ROS_DOMAIN_ID</td><td>{{ data.software.ros_domain_id || '-' }}</td></tr>
            <tr><td>操作系统</td><td>{{ data.software.os_description }}</td></tr>
            <tr><td>工作空间包数</td><td>{{ data.software.packages.length }} 个包 · {{ data.software.launch_count }} 个 launch</td></tr>
          </table>
        </div>

        <!-- 传感器 / 底盘状态 -->
        <div class="card">
          <h3>📡 底盘 &amp; 传感器 <span class="muted">（驱动运行后自动更新）</span></h3>
          <template v-if="data.sensors.gyro">
            <div class="sensor-grid" style="margin-bottom:10px">
              <div class="sensor-chip"><span class="k">航向角 yaw</span><br>{{ data.sensors.gyro.yaw }}°</div>
              <div class="sensor-chip"><span class="k">横滚 roll</span><br>{{ data.sensors.gyro.roll }}°</div>
              <div class="sensor-chip"><span class="k">俯仰 pitch</span><br>{{ data.sensors.gyro.pitch }}°</div>
              <div class="sensor-chip"><span class="k">角速度 wz</span><br>{{ data.sensors.gyro.anvz }}</div>
            </div>
            <div class="sensor-grid" style="margin-bottom:10px">
              <div class="sensor-chip"><span class="k">里程 x</span><br>{{ data.sensors.odom.x }}m</div>
              <div class="sensor-chip"><span class="k">里程 y</span><br>{{ data.sensors.odom.y }}m</div>
              <div class="sensor-chip"><span class="k">线速度 vx</span><br>{{ data.sensors.odom.lin_x }}m/s</div>
            </div>
          </template>
          <div v-else class="empty" style="padding:18px">暂无传感器数据（请先在「任务控制」启动底盘/驱动）</div>

          <template v-if="data.sensors.base_sensor">
            <h3 style="margin-top:8px">🛡️ 防撞 &amp; 跌落</h3>
            <div class="sensor-grid">
              <div v-for="(v, k) in data.sensors.base_sensor" :key="k"
                   class="sensor-chip" :class="v ? 'bool-trig' : 'bool-normal'">
                <span class="k">{{ k }}</span>
                <br>{{ v ? '触发' : '正常' }}
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- ROS 图 -->
      <div class="card" style="margin-top:14px">
        <h3>🕸️ ROS2 图 {{ data.ros_graph.nodes.length ? `· ${data.ros_graph.nodes.length} 节点 / ${data.ros_graph.topics.length} 话题` : '' }}</h3>
        <div class="flex" style="flex-wrap:wrap; gap:6px">
          <span v-for="n in data.ros_graph.nodes" :key="'n'+n" class="tag green">{{ n }}</span>
          <span v-if="data.ros_graph.nodes.length" class="spacer"></span>
          <span v-for="t in data.ros_graph.topics" :key="'t'+t" class="tag">{{ t }}</span>
          <span v-if="!data.ros_graph.nodes.length" class="muted">无活动节点（启动任务后显示）</span>
        </div>
      </div>
    </template>
    <div v-else-if="!error" class="empty">加载中…</div>
  </div>
</template>
