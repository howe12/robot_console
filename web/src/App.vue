<script setup>
import { reactive, onMounted, onUnmounted, provide, ref, computed } from 'vue'
import { api } from './api'
import Dashboard from './views/Dashboard.vue'
import Tasks from './views/Tasks.vue'
import Logs from './views/Logs.vue'
import Visual from './views/Visual.vue'

// ---- 全局共享日志状态 ----
const store = reactive({
  entries: [],
  perTask: {},
  running: [],
  wsState: 'connecting',
  logPaused: false
})
provide('logStore', store)

const view = ref('')
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

function hashView() {
  const h = location.hash.replace(/^#\/?/, '') || 'dashboard'
  return h.split('?')[0]
}
function onHash() { view.value = hashView() }
onMounted(() => { onHash(); window.addEventListener('hashchange', onHash) })
onUnmounted(() => window.removeEventListener('hashchange', onHash))

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
  connectLogs()
  loadStatus()
  statusTimer = setInterval(loadStatus, 5000)
})
onUnmounted(() => {
  if (ws) ws.close()
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo">🤖</span>
        <h1>SPARK 机器人管理系统</h1>
        <span class="version">v0.6</span>
      </div>
      <nav class="tabs">
        <a href="#/" class="tab" :class="{ active: view === 'dashboard' }">📊 系统状态</a>
        <a href="#/tasks" class="tab" :class="{ active: view === 'tasks' }">🚀 任务控制</a>
        <a href="#/logs" class="tab" :class="{ active: view === 'logs' }">📜 实时日志</a>
        <a href="#/visual" class="tab" :class="{ active: view === 'visual' }">🖥️ 可视化控制</a>
      </nav>
      <div class="top-status">
        <span class="dot" :class="wsState === 'open' ? 'ok' : 'bad'" :title="'日志连接: ' + wsState">
          日志 {{ wsState === 'open' ? '在线' : '离线' }}
        </span>
        <span class="badge badge-run">运行 {{ activeCount }}</span>
        <button class="btn emergency-stop" :disabled="stopping || !activeCount"
          @click="emergencyStop" title="紧急停止所有任务 + ROS 节点">
          🛑 {{ stopping ? '停止中…' : '紧急停止' }}
        </button>
      </div>
    </header>
    <div v-if="stopMsg" class="stop-banner" :class="stopMsg.includes('异常')||stopMsg.includes('失败') ? 'warn' : ''">{{ stopMsg }}</div>

    <main class="content">
      <Dashboard v-if="view === 'dashboard'" />
      <Tasks v-else-if="view === 'tasks'" />
      <Logs v-else-if="view === 'logs'" />
      <Visual v-else-if="view === 'visual'" />
      <div v-else class="empty">未知视图</div>
    </main>
  </div>
</template>
