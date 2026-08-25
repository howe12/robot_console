<script setup>
import { reactive, onMounted, onUnmounted, provide, ref, computed, watch } from 'vue'
import { api } from './api'
import Dashboard from './views/Dashboard.vue'
import Tasks from './views/Tasks.vue'
import Logs from './views/Logs.vue'
import Visual from './views/Visual.vue'
import Icon from './components/Icon.vue'

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
    // VNC 模式：log 上限更小（减少内存 + VNC 帧编码量）
    const logLimit = document.body.getAttribute('data-remote') === 'true' ? 200 : 500
    if (store.perTask[e.task_id].length > logLimit) store.perTask[e.task_id].shift()
    store.entries.push({ ...e })
    if (store.entries.length > (logLimit * 1.6)) store.entries.shift()
  }
}
onMounted(() => {
  onHash()
  window.addEventListener('hashchange', onHash)
  // 远程会话检测：标记 <body data-remote> 关闭持续动画（VNC/Terminal Server）
  if (isRemoteSession()) {
    document.body.setAttribute('data-remote', 'true')
    console.info('[remote] VNC / reduced-motion 会话检测：持续动画已关闭')
  }
  connectLogs()
  loadStatus()
  // 轮询频率：默认 5s，VNC/远程环境自动 15s（连续动画和重绘会拖慢远程会话）
  const pollMs = isRemoteSession() ? 15000 : 5000
  statusTimer = setInterval(loadStatus, pollMs)
})
onUnmounted(() => {
  window.removeEventListener('hashchange', onHash)
  if (ws) ws.close()
  if (statusTimer) clearInterval(statusTimer)
})

// 检测远程/VNC 会话：VNC/Terminal Services/Citrix 等场景下禁用持续动画
function isRemoteSession() {
  if (typeof navigator === 'undefined') return false
  // 1. 系统级偏好（用户或 OS 主动设置的）
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true
  // 2. 显式 query 参数：?low=1 强制低性能模式
  if (location.search.includes('low=1') || location.hash.includes('low=1')) return true
  // 3. User-Agent 嗅探（VNC / Citrix / RDP）
  const ua = navigator.userAgent || ''
  if (/vnc|remmina|tigervnc|tightvnc|realvnc|xtigervnc|citrix|terminalserver/i.test(ua)) return true
  // 4. 屏幕像素比异常低（VNC 通常 1.0）+ 设备内存 < 4GB 也算
  if (window.devicePixelRatio && window.devicePixelRatio < 1) return true
  if (navigator.deviceMemory && navigator.deviceMemory < 4) return true
  return false
}

// 视差已禁用：mousemove 监听会触发整页重绘，VNC 上完全没必要
// 原始 onMouseMove 函数已删除

// 当前视图元数据
const views = [
  { key: 'dashboard', label: 'Dashboard', icon: 'dashboard', desc: '系统状态总览' },
  { key: 'tasks',     label: 'Tasks',     icon: 'tasks',     desc: '机器人功能控制' },
  { key: 'logs',      label: 'Logs',      icon: 'logs',      desc: '实时监控 + 拓扑' },
  { key: 'visual',    label: 'Visual',    icon: 'visual',    desc: '可视化与遥控' }
]
const currentView = computed(() => views.find(v => v.key === view.value) || views[0])

// 路由切换过渡 key（强制重渲染）
const viewKey = ref(0)
watch(view, () => viewKey.value++)
</script>

<template>
  <div class="shell">
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
        <Icon name="robot" size="xl" class="logo-icon" />
        <div class="brand-text">
          <div class="brand-title">SPARK</div>
          <div class="brand-sub">Robot Console</div>
        </div>
        <span class="version-pill">v1.0</span>
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
          <Icon name="stop" size="sm" class="stop-icon" />
          {{ stopping ? '停止中…' : '紧急停止' }}
        </button>
      </div>
    </header>

    <!-- Nav Bar（顶栏 2：标签页 + 视图工具） -->
    <nav class="nav-bar">
      <div class="nav-tabs">
        <a v-for="v in views" :key="v.key" :href="'#/' + v.key"
          class="nav-tab" :class="{ active: view === v.key }">
          <Icon :name="v.icon" size="md" class="nav-icon" />
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