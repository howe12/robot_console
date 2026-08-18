<script setup>
import { ref, onMounted, onUnmounted, computed, defineProps, defineEmits } from 'vue'
import { api } from '../api'
import Icon from '../components/Icon.vue'

const props = defineProps({
  sidebarCollapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-sidebar'])

const data = ref(null)
const error = ref('')
const lastFmt = ref('')
let timer = null
const loading = ref(true)

async function load() {
  try {
    const d = await api.systemStatus()
    // 检测数值变化，触发闪烁
    const old = data.value
    if (old) {
      for (const k of ['cpu', 'mem', 'disk']) {
        if (old.system?.[k]?.percent !== d.system?.[k]?.percent) flashKey.value++
      }
    }
    data.value = d
    lastFmt.value = new Date(d.ts * 1000).toLocaleTimeString()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
  loading.value = false
}
const flashKey = ref(0)

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

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))

// 派生数据
const cpu = computed(() => data.value?.system?.cpu_percent ?? null)
const mem = computed(() => data.value?.system?.mem ?? null)
const disk = computed(() => data.value?.system?.disk ?? null)
const uptime = computed(() => data.value?.system?.uptime ?? null)
const hostname = computed(() => data.value?.system?.hostname ?? '')
const devices = computed(() => data.value?.devices ?? {})
const sensors = computed(() => data.value?.sensors ?? {})
const rosGraph = computed(() => data.value?.ros_graph ?? { nodes: [], topics: [] })
const software = computed(() => data.value?.software ?? {})
</script>

<template>
  <div class="layout-with-sidebar" :class="{ collapsed: sidebarCollapsed }">
    <!-- 粘性侧边栏：上下文信息 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <Icon name="dashboard" size="md" />
        <span>上下文</span>
        <button class="sidebar-toggle" @click="emit('toggle-sidebar')">
          {{ sidebarCollapsed ? '›' : '‹' }}
        </button>
      </div>
      <div class="sidebar-content">
        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">ROS 发行版</div>
        <div style="font-size:14px;font-weight:600;margin-bottom:14px">{{ software.ros_distro || '-' }}</div>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">ROS_DOMAIN_ID</div>
        <div style="font-family:var(--font-mono);font-size:13px;margin-bottom:14px">{{ software.ros_domain_id || '-' }}</div>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">运行时长</div>
        <div style="font-size:13px;margin-bottom:14px">{{ fmtUptime(uptime) }}</div>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">包 / launch</div>
        <div style="font-family:var(--font-mono);font-size:13px;margin-bottom:14px">
          {{ software.packages?.length || 0 }} · {{ software.launch_count || 0 }}
        </div>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">ROS 图</div>
        <div style="font-family:var(--font-mono);font-size:13px">
          {{ rosGraph.nodes.length }} 节点<br>
          {{ rosGraph.topics.length }} 话题
        </div>
      </div>
    </aside>

    <!-- 主内容 -->
    <div>
      <!-- Hero 区 -->
      <div class="hero">
        <div class="hero-grid">
          <div class="hero-title">
            <h2><Icon name="dashboard" size="xl" class="hero-icon" /> Dashboard</h2>
            <span class="hero-sub">系统状态总览 · 资源、传感器、ROS 图实时监控 · 每 5 秒自动刷新</span>
          </div>
          <div class="hero-actions">
            <span class="hero-status">
              <span class="dot" :class="error ? 'bad' : (data ? 'ok' : 'idle')"></span>
              {{ error ? '连接失败' : (data ? `更新于 ${lastFmt}` : '加载中…') }}
            </span>
            <button class="btn" @click="load">↻  刷新</button>
          </div>
        </div>
      </div>

      <!-- 加载中：骨架屏 -->
      <template v-if="loading && !data">
        <div class="metric-grid">
          <div class="card" v-for="i in 4" :key="i">
            <div class="skeleton text" style="width: 60%; margin-bottom: 14px"></div>
            <div class="skeleton text-lg" style="width: 70%"></div>
            <div class="skeleton bar"></div>
          </div>
        </div>
        <div class="card" style="margin-top:24px">
          <div class="skeleton text" style="width: 30%; margin-bottom: 16px"></div>
          <div class="sensor-strip">
            <div v-for="i in 6" :key="i" class="sensor-cell">
              <div class="skeleton text" style="width:50%"></div>
              <div class="skeleton text-lg" style="width:80%; margin-top:8px"></div>
            </div>
          </div>
        </div>
      </template>

      <!-- 已加载 -->
      <template v-else-if="data">
        <!-- 指标卡（视差） -->
        <div class="metric-grid">
          <div class="card metric parallax">
            <div class="label"><Icon name="chip" size="sm" class="label-icon" /> CPU</div>
            <div class="val" :class="{ flash: cpu !== null }">
              {{ cpu !== null ? cpu.toFixed(1) : '-' }}<span class="unit">%</span>
            </div>
            <div class="bar"><i :style="{ width: (cpu || 0) + '%' }"></i></div>
          </div>
          <div class="card metric parallax">
            <div class="label"><Icon name="memory" size="sm" class="label-icon" /> 内存</div>
            <div class="val">
              {{ mem.percent !== undefined ? mem.percent.toFixed(0) : '-' }}<span class="unit">%</span>
            </div>
            <div class="muted sub" style="margin-top:8px">{{ fmtBytes(mem.used) }} / {{ fmtBytes(mem.total) }}</div>
            <div class="bar"><i :style="{ width: (mem.percent || 0) + '%' }"></i></div>
          </div>
          <div class="card metric parallax">
            <div class="label"><Icon name="database" size="sm" class="label-icon" /> 磁盘</div>
            <div class="val">
              {{ disk.percent !== undefined ? disk.percent.toFixed(0) : '-' }}<span class="unit">%</span>
            </div>
            <div class="muted sub" style="margin-top:8px">{{ fmtBytes(disk.free) }} 可用</div>
            <div class="bar"><i :style="{ width: (disk.percent || 0) + '%' }"></i></div>
          </div>
          <div class="card metric parallax">
            <div class="label"><Icon name="bolt" size="sm" class="label-icon" /> 运行时长</div>
            <div class="val" style="font-size:22px">{{ fmtUptime(uptime) }}</div>
            <div class="muted sub" style="margin-top:8px">{{ hostname }}</div>
          </div>
        </div>

        <!-- 实时传感器条 -->
        <div class="card glow" style="margin-top:24px">
          <h3><Icon name="signal" size="md" class="card-h3-icon" /> 实时传感器 · 底盘 & 驱动</h3>
          <template v-if="sensors.gyro">
            <div class="sensor-strip" style="margin-bottom:12px">
              <div class="sensor-cell">
                <div class="k">航向 yaw</div>
                <div class="v">{{ sensors.gyro.yaw }}<span class="u">°</span></div>
              </div>
              <div class="sensor-cell">
                <div class="k">横滚 roll</div>
                <div class="v">{{ sensors.gyro.roll }}<span class="u">°</span></div>
              </div>
              <div class="sensor-cell">
                <div class="k">俯仰 pitch</div>
                <div class="v">{{ sensors.gyro.pitch }}<span class="u">°</span></div>
              </div>
              <div class="sensor-cell">
                <div class="k">角速度 wz</div>
                <div class="v">{{ sensors.gyro.anvz }}</div>
              </div>
              <div class="sensor-cell">
                <div class="k">里程 x</div>
                <div class="v">{{ sensors.odom.x }}<span class="u">m</span></div>
              </div>
              <div class="sensor-cell">
                <div class="k">线速度 vx</div>
                <div class="v">{{ sensors.odom.lin_x }}<span class="u">m/s</span></div>
              </div>
            </div>
          </template>
          <div v-else class="empty" style="padding:24px">暂无传感器数据（请先在「Tasks」启动底盘/驱动任务）</div>

          <template v-if="sensors.base_sensor">
            <h3 style="margin-top:8px"><Icon name="warning" size="md" class="card-h3-icon" /> 防撞 &amp; 跌落</h3>
            <div class="sensor-strip">
              <div v-for="(v, k) in sensors.base_sensor" :key="k"
                   class="sensor-cell" :class="{ alert: v }">
                <div class="k">{{ k }}</div>
                <div class="v" :style="{ color: v ? 'var(--red)' : 'var(--green)' }">
                  {{ v ? '触发' : '正常' }}
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 外接设备 + ROS 图 -->
        <div class="grid grid-2" style="margin-top:24px">
          <div class="card">
            <h3><Icon name="cubeBox" size="md" class="card-h3-icon" /> 外接设备</h3>
            <div class="device-list">
              <div class="device-row">
                <span class="device-light" :class="devices.camera?.connected ? 'ok' : 'bad'"></span>
                <span class="device-name">相机</span>
                <span class="device-type">{{ devices.camera?.type || '-' }}</span>
                <span class="device-status" :class="{ bad: !devices.camera?.connected }">
                  {{ devices.camera?.connected ? '已连接' : '未连接' }}
                </span>
              </div>
              <div class="device-row">
                <span class="device-light" :class="devices.base?.connected ? 'ok' : 'bad'"></span>
                <span class="device-name">底盘</span>
                <span class="device-type">{{ devices.base?.type || '-' }}</span>
                <span class="device-status" :class="{ bad: !devices.base?.connected }">
                  {{ devices.base?.connected ? '已连接' : '未连接' }}
                </span>
              </div>
              <div class="device-row">
                <span class="device-light" :class="devices.lidar?.connected ? 'ok' : 'bad'"></span>
                <span class="device-name">雷达</span>
                <span class="device-type">{{ devices.lidar?.type || '-' }}</span>
                <span class="device-status" :class="{ bad: !devices.lidar?.connected }">
                  {{ devices.lidar?.connected ? '已连接' : '未连接' }}
                </span>
              </div>
              <div class="device-row">
                <span class="device-light" :class="devices.arm?.connected ? 'ok' : 'bad'"></span>
                <span class="device-name">机械臂</span>
                <span class="device-type">{{ devices.arm?.type || '-' }}</span>
                <span class="device-status" :class="{ bad: !devices.arm?.connected }">
                  {{ devices.arm?.connected ? '已连接' : '未连接' }}
                </span>
              </div>
            </div>
          </div>

          <div class="card">
            <h3><Icon name="graph" size="md" class="card-h3-icon" /> ROS2 图 · 节点 / 话题</h3>
            <div class="ros-chip-cloud">
              <span v-for="n in rosGraph.nodes.slice(0, 12)" :key="'n'+n" class="ros-chip node">{{ n }}</span>
              <span v-for="t in rosGraph.topics.slice(0, 12)" :key="'t'+t" class="ros-chip topic">{{ t }}</span>
              <span v-if="rosGraph.nodes.length > 12" class="muted" style="font-size:11px">
                +{{ rosGraph.nodes.length - 12 }} 节点 / +{{ Math.max(0, rosGraph.topics.length - 12) }} 话题
              </span>
              <span v-if="!rosGraph.nodes.length && !rosGraph.topics.length" class="muted" style="font-size:13px">
                启动任务后此处显示节点与话题
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>