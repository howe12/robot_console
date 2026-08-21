<script setup>
import { ref, onMounted, onUnmounted, computed, watch, defineProps, defineEmits, inject } from 'vue'
import { api } from '../api'
import Icon from '../components/Icon.vue'

const props = defineProps({
  sidebarCollapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-sidebar'])
// 注入全局日志 store（从 App.vue provide('logStore')）
const store = inject('logStore', { entries: [], perTask: {}, running: [] })

const data = ref(null)
const error = ref('')
const lastFmt = ref('')
let timer = null
const loading = ref(true)
const systemStats = ref(null)
const rosGraphLoaded = ref(false)  // 首次拉过 full status 后为 true
const wsBytes = ref(0)          // 累计 WebSocket 接收字节
const wsLastTick = ref(0)       // 上次记录时间
const browserInfo = ref(null)   // 浏览器端实时数据
let statsTimer = null
let gitTimer = null
const gitInfo = ref(null)
let browserTimer = null

;
const flashKey = ref(0)

function fmtBytes(b) {
  if (b == null) return '-'
  const g = b / 1073741824
  if (g >= 1) return g.toFixed(2) + ' GB'
  return (b / 1048576).toFixed(0) + ' MB'
};
function fmtUptime(s) {
  if (s == null) return '-'
  const d = Math.floor(s / 86400)
  const h = Math.floor(s % 86400 / 3600)
  const m = Math.floor(s % 3600 / 60)
  return d > 0 ? `${d}天 ${h}时 ${m}分` : `${h}时 ${m}分`;
// Git date 字符串 ("Wed Aug 19 14:35:27 2026 +0800") -> 相对时间
}
function formatRelative(gitDate) {
  if (!gitDate) return ''
  // git 格式 "Wed Aug 19 14:35:27 2026 +0800"
  const d = new Date(gitDate)
  if (isNaN(d)) return gitDate
  const sec = (Date.now() - d.getTime()) / 1000
  if (sec < 60) return '刚刚'
  if (sec < 3600) return `${Math.floor(sec/60)} 分钟前`
  if (sec < 86400) return `${Math.floor(sec/3600)} 小时前`
  if (sec < 86400*7) return `${Math.floor(sec/86400)} 天前`
  if (sec < 86400*30) return `${Math.floor(sec/(86400*7))} 周前`
  if (sec < 86400*365) return `${Math.floor(sec/(86400*30))} 月前`
  return `${Math.floor(sec/(86400*365))} 年前`
};


// 底盘传感器键名 → 中文（SparkBaseSensor.msg 字段）
const SENSOR_LABEL = {
  // 红外防撞（7 个）
  ir_bumper_left: '红外防撞·左',
  ir_bumper_right: '红外防撞·右',
  ir_bumper_front: '红外防撞·前',
  ir_bumper_front_left: '红外防撞·前左',
  ir_bumper_front_right: '红外防撞·前右',
  ir_bumper_back_left: '红外防撞·后左',
  ir_bumper_back_right: '红外防撞·后右',
  // 跌落（6 个）
  cliff_left: '悬崖·左',
  cliff_right: '悬崖·右',
  cliff_front_left: '悬崖·前左',
  cliff_front_right: '悬崖·前右',
  cliff_back_left: '悬崖·后左',
  cliff_back_right: '悬崖·后右',
  // 轮组
  wheel_drop_left: '轮抬起·左',
  wheel_drop_right: '轮抬起·右',
  wheel_over_current_left: '轮过流·左',
  wheel_over_current_right: '轮过流·右',
};
function sensorLabel(k) { return SENSOR_LABEL[k] || k }

const load = async () => {
  try {
    // 用轻量端点：30ms 替代 system/status 1.5s（ROS 图冷启动 1000ms+）
    // ROS 图节点/话题改在 TopologyView（只在用户进入 Logs 视图时拉）
    const d = await api.systemLight()
    // 检测数值变化，触发闪烁
    const old = data.value
    if (old) {
      for (const k of ['cpu', 'mem', 'disk']) {
        if (old.system?.[k]?.percent !== d.system?.[k]?.percent) flashKey.value++
      }
    }
    // 第一次拉取：附加拉一次 full status 获取 ros_graph（chip cloud 用）
    if (!rosGraphLoaded.value) {
      try {
        const full = await api.systemStatus()
        d.ros_graph = full.ros_graph
        rosGraphLoaded.value = true
      } catch (e) { /* 忽略 */ }
    }
    data.value = d
    lastFmt.value = new Date(d.ts * 1000).toLocaleTimeString()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
  loading.value = false
}
onMounted(() => {
  // 主数据轮询用轻量端点（/api/system/light，<30ms，无 ROS 图）
  // ROS 图节点/话题改在 TopologyView（仅 Logs 视图需要时拉取）
  load()
  const isRemote = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const mainPollMs = isRemote ? 12000 : 6000
  timer = setInterval(load, mainPollMs)
  // 网络分析：后端 stats（极轻 1.5ms）+ 浏览器实时（无请求）
  // 直接 inline fetch 调用，避免 Vue compiler scope merging bug
  ;(async () => { try { systemStats.value = await api.systemStats() } catch {} })()
  ;(() => {
    const mem = performance.memory ? {
      used: (performance.memory.usedJSHeapSize / 1048576).toFixed(1),
      total: (performance.memory.totalJSHeapSize / 1048576).toFixed(1)
    } : null
    browserInfo.value = {
      jsHeapMb: mem,
      dom: document.querySelectorAll('*').length,
      svg: document.querySelectorAll('svg').length,
      wsEntries: store.entries.length,
      wsBytes: wsBytes.value
    }
  })()
  ;(async () => { try { gitInfo.value = await api.gitInfo() } catch {} })()  // 初始拉一次
  statsTimer = setInterval(async () => { try { systemStats.value = await api.systemStats() } catch {} }, isRemote ? 5000 : 2000)
  browserTimer = setInterval(() => {
    const mem = performance.memory ? {
      used: (performance.memory.usedJSHeapSize / 1048576).toFixed(1),
      total: (performance.memory.totalJSHeapSize / 1048576).toFixed(1)
    } : null
    browserInfo.value = {
      jsHeapMb: mem,
      dom: document.querySelectorAll('*').length,
      svg: document.querySelectorAll('svg').length,
      wsEntries: store.entries.length,
      wsBytes: wsBytes.value
    }
  }, isRemote ? 5000 : 2000)
  // 仓库同步信息轮询较慢（30s）
  gitTimer = setInterval(async () => { try { gitInfo.value = await api.gitInfo() } catch {} }, 30000)
  // 监听 store 的 log entries 累加 WebSocket 字节
  watch(() => store.entries.length, (newLen, oldLen) => {
    if (newLen > oldLen) {
      for (let i = oldLen; i < newLen; i++) {
        // 估算每条 entry 序列化大小
        const e = store.entries[i]
        if (e) wsBytes.value += (e.line?.length || 0) + (e.node?.length || 0) + 30
      }
    }
  })
})
onUnmounted(() => {
  clearInterval(timer)
  clearInterval(statsTimer); clearInterval(gitTimer)
  clearInterval(browserTimer)
})

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
const workspaceBaseName = computed(() => {
  const ws = software.value?.workspace || ''
  if (!ws) return '—'
  return ws.split('/').filter(Boolean).pop() || ws
})

// 网络分析：后端 stats + 浏览器 stats
;
;

// CPU 数字颜色：低/中/高三色
function cpuColor(p) {
  if (p === null || p === undefined) return ''
  if (p < 30) return 'color: var(--green)'
  if (p < 70) return 'color: var(--yellow)'
  return 'color: var(--red)'
};
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
        <!-- 机器人 + 工作空间（最高优先级 — 一眼看出当前连的是哪台机器 / 哪个工作空间） -->
        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">机器人</div>
        <div style="font-size:14px;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:6px">
          <span style="width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green)"></span>
          {{ software.hostname || '—' }}
        </div>
        <div style="font-size:11px;color:var(--muted);font-family:var(--font-mono);margin-bottom:14px">{{ software.os_description }}</div>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px">
          ROS 工作空间
          <span v-if="software.workspace" class="muted" style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10px;margin-left:6px">点击展开</span>
        </div>
        <details class="ws-path">
          <summary style="font-size:13px;font-family:var(--font-mono);cursor:pointer;list-style:none">
            📁 {{ workspaceBaseName }}
          </summary>
          <div style="font-size:10px;font-family:var(--font-mono);color:var(--muted);margin-top:6px;padding:6px;background:var(--bg2);border-radius:6px;word-break:break-all;line-height:1.5">
            {{ software.workspace || '—' }}
          </div>
        </details>

        <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px;margin-top:14px">ROS 发行版</div>
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
          <div class="card metric">
            <div class="label"><Icon name="chip" size="sm" class="label-icon" /> CPU</div>
            <div class="val" :class="{ flash: cpu !== null }">
              {{ cpu !== null ? cpu.toFixed(1) : '-' }}<span class="unit">%</span>
            </div>
            <div class="bar"><i :style="{ width: (cpu || 0) + '%' }"></i></div>
          </div>
          <div class="card metric">
            <div class="label"><Icon name="memory" size="sm" class="label-icon" /> 内存</div>
            <div class="val">
              {{ mem.percent !== undefined ? mem.percent.toFixed(0) : '-' }}<span class="unit">%</span>
            </div>
            <div class="muted sub" style="margin-top:8px">{{ fmtBytes(mem.used) }} / {{ fmtBytes(mem.total) }}</div>
            <div class="bar"><i :style="{ width: (mem.percent || 0) + '%' }"></i></div>
          </div>
          <div class="card metric">
            <div class="label"><Icon name="database" size="sm" class="label-icon" /> 磁盘</div>
            <div class="val">
              {{ disk.percent !== undefined ? disk.percent.toFixed(0) : '-' }}<span class="unit">%</span>
            </div>
            <div class="muted sub" style="margin-top:8px">{{ fmtBytes(disk.free) }} 可用</div>
            <div class="bar"><i :style="{ width: (disk.percent || 0) + '%' }"></i></div>
          </div>
          <div class="card metric">
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
                <div class="k" :title="k">{{ sensorLabel(k) }}</div>
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

        <!-- 网络 / 资源分析 -->
        <div class="card glow" style="margin-top:24px">
          <div class="flex" style="margin-bottom:14px">
            <h3 style="margin:0"><Icon name="bolt" size="md" class="card-h3-icon" /> 网络 / 资源分析
              <span v-if="systemStats" class="muted" style="font-weight:400;margin-left:10px;font-size:12px;font-family:var(--font-mono)">
                PID {{ systemStats.pid }} · uptime {{ fmtUptime(systemStats.uptime) }} · 线程 {{ systemStats.threads }}
              </span>
            </h3>
            <div class="spacer"></div>
            <span class="muted" style="font-size:11px;font-family:var(--font-mono)">每 2s 刷新</span>
          </div>
          <div class="grid grid-4" style="gap:12px">
            <div class="metric">
              <div class="label">后端 CPU</div>
              <div class="val" :style="cpuColor(systemStats?.cpu_percent)">
                {{ systemStats?.cpu_percent !== null && systemStats?.cpu_percent !== undefined ? systemStats.cpu_percent.toFixed(1) : '—' }}<span class="unit">%</span>
              </div>
              <div class="bar"><i :style="{ width: (systemStats?.cpu_percent || 0) + '%' }"></i></div>
            </div>
            <div class="metric">
              <div class="label">后端内存 (RSS)</div>
              <div class="val">
                {{ systemStats?.rss_mb !== null && systemStats?.rss_mb !== undefined ? systemStats.rss_mb.toFixed(0) : '—' }}<span class="unit">MB</span>
              </div>
              <div class="muted sub" style="margin-top:6px;font-size:12px">虚拟 {{ systemStats?.vms_mb?.toFixed(0) || '—' }} MB</div>
            </div>
            <div class="metric">
              <div class="label">WebSocket 客户端</div>
              <div class="val" style="font-size:32px">{{ systemStats?.ws_clients ?? '—' }}</div>
              <div class="muted sub" style="margin-top:6px;font-size:12px">
                运行中任务: {{ systemStats?.running_tasks ?? '—' }}
              </div>
            </div>
            <div class="metric">
              <div class="label">浏览器 JS 堆</div>
              <div class="val">
                {{ browserInfo?.jsHeapMb?.used || '—' }}<span class="unit">MB</span>
              </div>
              <div class="muted sub" style="margin-top:6px;font-size:12px">
                DOM {{ browserInfo?.dom || '—' }} · SVG {{ browserInfo?.svg || '—' }}
              </div>
            </div>
          </div>
          <div class="grid grid-3" style="gap:12px;margin-top:12px">
            <div class="metric">
              <div class="label">WebSocket 日志条目</div>
              <div class="val" style="font-size:24px">{{ browserInfo?.wsEntries || 0 }}</div>
              <div class="muted sub" style="margin-top:4px;font-size:11px">最近 1000 条累计</div>
            </div>
            <div class="metric">
              <div class="label">WebSocket 累计流量</div>
              <div class="val" style="font-size:24px">
                {{ browserInfo ? (browserInfo.wsBytes / 1024).toFixed(1) : '0' }}<span class="unit">KB</span>
              </div>
              <div class="muted sub" style="margin-top:4px;font-size:11px">实时累加</div>
            </div>
            <div class="metric">
              <div class="label">JS 堆总容量</div>
              <div class="val" style="font-size:24px">
                {{ browserInfo?.jsHeapMb?.total || '—' }}<span class="unit">MB</span>
              </div>
              <div class="muted sub" style="margin-top:4px;font-size:11px">v8 分配</div>
            </div>
          </div>
          <div v-if="systemStats?.psutil_missing" class="warn" style="margin-top:12px;font-size:12px">
            ⚠ psutil 未安装，部分指标不可用。运行: pip install psutil
          </div>
        </div>

        <!-- 仓库同步信息（git 状态） -->
        <div class="card glow" style="margin-top:24px">
          <div class="flex" style="margin-bottom:14px">
            <h3 style="margin:0">
              <Icon name="cubeBox" size="md" class="card-h3-icon" />
              仓库同步
              <span v-if="gitInfo?.in_sync === true" class="tag green" style="margin-left:10px">✓ 同步</span>
              <span v-else-if="gitInfo" class="tag" style="margin-left:10px;background:rgba(255,206,84,.15);color:var(--yellow)">⚠ 偏离</span>
              <span v-else class="muted" style="font-weight:400;margin-left:10px;font-size:12px">加载中…</span>
            </h3>
            <div class="spacer"></div>
            <span class="muted" style="font-size:11px;font-family:var(--font-mono)">每 30s 刷新</span>
          </div>

          <div v-if="gitInfo?.latest?.hash" class="metric-grid" style="gap:12px">
            <div class="metric">
              <div class="label">最新 commit</div>
              <div class="val" style="font-size:18px;font-family:var(--font-mono);letter-spacing:0">
                {{ gitInfo.latest.short }}
              </div>
              <div class="muted sub" style="margin-top:4px;font-size:11px;line-height:1.4;word-break:break-all">
                {{ gitInfo.latest.subject }}
              </div>
            </div>
            <div class="metric">
              <div class="label">作者</div>
              <div class="val" style="font-size:16px">{{ gitInfo.latest.author }}</div>
              <div class="muted sub" style="margin-top:4px;font-size:11px">{{ gitInfo.latest.date }}</div>
            </div>
            <div class="metric">
              <div class="label">分支 / 远程</div>
              <div class="val" style="font-size:18px;font-family:var(--font-mono)">{{ gitInfo.branch }}</div>
              <div class="muted sub" style="margin-top:4px;font-size:11px;line-height:1.4;word-break:break-all">
                {{ gitInfo.remote }}
              </div>
            </div>
            <div class="metric">
              <div class="label">与 origin/main 关系</div>
              <div class="val" style="font-size:18px">
                <span v-if="gitInfo.in_sync" style="color:var(--green)">一致</span>
                <span v-else style="color:var(--yellow)">
                  <span v-if="gitInfo.behind > 0">落后 {{ gitInfo.behind }} 提交</span>
                  <span v-else-if="gitInfo.ahead > 0">领先 {{ gitInfo.ahead }} 提交</span>
                  <span v-else>分叉</span>
                </span>
              </div>
              <div class="muted sub" style="margin-top:4px;font-size:11px">
                未提交 {{ gitInfo.uncommitted }} 文件
              </div>
            </div>
          </div>
          <!-- 近期提交列表（最多 5 个） -->
          <div v-if="gitInfo?.recent_commits?.length" style="margin-top:18px">
            <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:8px">近 5 次提交</div>
            <ul class="commit-list">
              <li v-for="c in gitInfo.recent_commits" :key="c.hash" class="commit-row">
                <div style="display:flex;align-items:center;gap:10px">
                  <span style="font-family:var(--font-mono);font-size:11px;color:var(--accent);flex-shrink:0">{{ c.short }}</span>
                  <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="c.subject">{{ c.subject }}</span>
                  <span style="font-size:11px;color:var(--muted);flex-shrink:0;font-family:var(--font-mono)">{{ formatRelative(c.date) }}</span>
                </div>
              </li>
            </ul>
          </div>

          <div v-else class="muted" style="font-size:12px;padding:8px 0">
            {{ gitInfo ? '仓库信息加载失败' : '正在读取…' }}
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
