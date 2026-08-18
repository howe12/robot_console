<script setup>
import { reactive, onMounted, onUnmounted, provide, ref, computed, watch } from 'vue'
import { api } from './api'
import Dashboard from './views/Dashboard.vue'
import Tasks from './views/Tasks.vue'
import Logs from './views/Logs.vue'
import Visual from './views/Visual.vue'

// ---- 全局共享状态 ----
const store = reactive({
  entries: [],
  perTask: {},
  running: [],
  wsState: 'connecting',
  logPaused: false
})
provide('logStore', store)

// 视图路由
const view = ref('')
function hashView() {
  const h = location.hash.replace(/^#\/?/, '') || 'dashboard'
  return h.split('?')[0]
}
function onHash() { view.value = hashView() }

// 紧急停止
const stopping = ref(false)
const stopMsg = ref('')
const activeCount = computed(() => (store.running || []).filter(r => r.running).length)
async function emergencyStop() {
  if (stopping.value) return
  stopping.value = true
  stopMsg.value = ''
  try {
    const r = await api.stopAll()
    stopMsg.value = r.ok ? `已紧急停止 ${r.stopped.length} 个任务 + ROS 节点` : '停止失败'
    setTimeout(() => stopMsg.value = '', 4000)
    loadStatus()
  } catch (e) {
    stopMsg.value = '紧急停止异常: ' + e
  } finally {
    stopping.value = false
  }
}

// 侧边栏折叠
const sidebarCollapsed = ref(false)
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value }

let ws = null
let wsRetry = 0
let statusTimer = null
async function loadStatus() {
  try {
    const s = await api.status()
    store.running = s.running || []
  } catch (e) {}
}
function connectLogs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/logs`)
  ws.onopen = () => { store.wsState = 'open'; wsRetry = 0 }
  ws.onclose = () => {
    store.wsState = 'closed'
    wsRetry += 1
    setTimeout(connectLogs, Math.min(1000 * wsRetry, 5000))
  }
  ws.onerror = () => { ws.close() }
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (!msg.entry) return
    const e = msg.entry
    if (!store.perTask[e.task_id]) store.perTask[e.task_id] = []
    store.perTask[e.task_id].push(e)
    if (store.perTask[e.task_id].length > 500) store.perTask[e.task_id].shift()
    store.entries.push({ ...e })
    if (store.entries.length > 800) store.entries.shift()
  }
}
onMounted(() => {
  onHash()
  window.addEventListener('hashchange', onHash)
  connectLogs()
  loadStatus()
  statusTimer = setInterval(loadStatus, 5000)
})
onUnmounted(() => {
  window.removeEventListener('hashchange', onHash)
  if (ws) ws.close()
  if (statusTimer) clearInterval(statusTimer)
})

// 视差：鼠标移动时更新 CSS 变量
function onMouseMove(e) {
  const x = (e.clientX / window.innerWidth - 0.5) * 2  // -1..1
  const y = (e.clientY / window.innerHeight - 0.5) * 2
  document.documentElement.style.setProperty('--mx', x.toFixed(3))
  document.documentElement.style.setProperty('--my', y.toFixed(3))
}

// 当前视图元数据
const views = [
  { key: 'dashboard', label: 'Dashboard', icon: '◐', desc: '系统状态总览' },
  { key: 'tasks',     label: 'Tasks',     icon: '◈', desc: '机器人功能控制' },
  { key: 'logs',      label: 'Logs',      icon: '◉', desc: '实时监控 + 拓扑' },
  { key: 'visual',    label: 'Visual',    icon: '◇', desc: '可视化与遥控' }
]
const currentView = computed(() => views.find(v => v.key === view.value) || views[0])

// 路由切换过渡 key（强制重渲染）
const viewKey = ref(0)
watch(view, () => viewKey.value++)
</script>

<template>
  <div class="shell" @mousemove="onMouseMove">
    <!-- 极光背景层 -->
    <div class="aurora" aria-hidden="true">
      <div class="aurora-blob blob-1"></div>
      <div class="aurora-blob blob-2"></div>
      <div class="aurora-blob blob-3"></div>
      <div class="aurora-grid"></div>
    </div>

    <!-- Command Bar（顶栏 1：品牌 + 状态 + 紧急停止） -->
    <header class="cmd-bar">
      <div class="brand">
        <span class="logo">🤖</span>
        <div class="brand-text">
          <div class="brand-title">SPARK</div>
          <div class="brand-sub">Robot Console</div>
        </div>
        <span class="version-pill">v0.6</span>
      </div>
      <div class="cmd-center">
        <span class="status-chip">
          <span class="dot" :class="wsState === 'open' ? 'ok' : 'bad'"></span>
          <span class="muted">日志 {{ wsState === 'open' ? '在线' : '离线' }}</span>
        </span>
        <span class="status-chip" :class="activeCount ? 'live' : ''">
          <span class="dot" :class="activeCount ? 'ok live' : 'idle'"></span>
          <span class="muted">{{ activeCount }} 运行中</span>
        </span>
      </div>
      <div class="cmd-right">
        <button class="btn emergency-stop" :disabled="stopping || !activeCount"
          @click="emergencyStop" title="紧急停止所有任务 + ROS 节点">
          <span class="stop-icon">⏹</span>
          {{ stopping ? '停止中…' : '紧急停止' }}
        </button>
      </div>
    </header>

    <!-- Nav Bar（顶栏 2：标签页 + 视图工具） -->
    <nav class="nav-bar">
      <div class="nav-tabs">
        <a v-for="v in views" :key="v.key" :href="'#/' + v.key"
          class="nav-tab" :class="{ active: view === v.key }">
          <span class="nav-icon">{{ v.icon }}</span>
          <span class="nav-label">{{ v.label }}</span>
        </a>
      </div>
      <div class="nav-tools">
        <span class="view-desc">{{ currentView.desc }}</span>
      </div>
    </nav>

    <!-- stop banner -->
    <div v-if="stopMsg" class="stop-banner" :class="stopMsg.includes('异常')||stopMsg.includes('失败') ? 'warn' : ''">
      {{ stopMsg }}
    </div>

    <!-- 主内容区（含粘性侧边栏） -->
    <main class="content-wrap">
      <div :key="viewKey" class="view-transition">
        <Dashboard v-if="view === 'dashboard'" :sidebar-collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
        <Tasks v-else-if="view === 'tasks'" :sidebar-collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
        <Logs v-else-if="view === 'logs'" :sidebar-collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
        <Visual v-else-if="view === 'visual'" :sidebar-collapsed="sidebarCollapsed" @toggle-sidebar="toggleSidebar" />
        <div v-else class="empty">未知视图</div>
      </div>
    </main>

    <!-- 折叠侧边栏的浮动按钮（仅当侧边栏折叠时显示） -->
    <button v-if="sidebarCollapsed" class="sidebar-toggle-floating" @click="toggleSidebar" title="展开侧边栏">›</button>
  </div>
</template>

<style>
/* App.vue 局部样式：只放布局相关，具体设计 token 走 style.css */
</style>