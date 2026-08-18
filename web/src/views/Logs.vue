<script setup>
import { ref, inject, onMounted, onUnmounted, computed, watch, nextTick, defineProps, defineEmits } from 'vue'
import { api } from '../api'
import TopologyView from './TopologyView.vue'

const props = defineProps({
  sidebarCollapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-sidebar'])

const store = inject('logStore')
const taskFilter = ref('')
const nodeFilter = ref('')
const levelFilter = ref('')
const tailN = ref(500)
const nodes = ref([])
const tasks = ref([])
const scrollBox = ref(null)
const autoScroll = ref(true)
const showTopo = ref(false)  // 默认折叠
const initialTask = new URLSearchParams(location.hash.split('?')[1] || '').get('task') || ''

// 新任务分割线
const taskStartMarkers = ref(new Set())
let prevRunningIds = new Set()

watch(() => store.running, (newRunning) => {
  const newIds = new Set((newRunning || []).filter(r => r.running).map(r => r.id))
  for (const id of newIds) {
    if (!prevRunningIds.has(id)) {
      const entries = store.perTask[id] || []
      if (entries.length) taskStartMarkers.value.add(entries[0].seq)
    }
  }
  prevRunningIds = newIds
}, { deep: true })

function isTaskStart(seq) { return taskStartMarkers.value.has(seq) }
function clearLogs() {
  if (taskFilter.value) store.perTask[taskFilter.value] = []
  else {
    store.entries.splice(0, store.entries.length)
    for (const k of Object.keys(store.perTask)) store.perTask[k] = []
  }
  taskStartMarkers.value.clear()
}

async function loadMeta() {
  try {
    const f = await api.logFilters()
    nodes.value = f.nodes || []
  } catch (e) {}
  try {
    const s = await api.tasks()
    tasks.value = (s.tasks || []).map(t => ({ id: t.id, name: t.name }))
  } catch (e) {}
}

const hist = ref([])
const loadingHist = ref(false)
async function loadHist() {
  loadingHist.value = true
  try {
    if (taskFilter.value) {
      const r = await api.taskLogs(taskFilter.value, tailN.value, nodeFilter.value || null, levelFilter.value || null)
      hist.value = r.lines || []
    } else {
      hist.value = []
    }
  } catch (e) { hist.value = [] }
  loadingHist.value = false
  scrollDown()
}

const allEntries = computed(() => {
  if (taskFilter.value) return store.perTask[taskFilter.value] || []
  return store.entries
})
const visible = computed(() => {
  const lv = levelFilter.value
  const nd = nodeFilter.value
  return allEntries.value.filter(e => {
    if (lv && e.level !== lv) return false
    if (nd && e.node !== nd) return false
    return true
  }).slice(-tailN.value)
})

function uniqueNodes() {
  const set = new Set(nodes.value)
  for (const e of store.entries) if (e.node) set.add(e.node)
  for (const list of Object.values(store.perTask)) for (const e of list) if (e.node) set.add(e.node)
  return Array.from(set).sort()
}

watch(() => [taskFilter.value, nodeFilter.value, levelFilter.value], () => { loadHist() })

function scrollDown() {
  nextTick(() => {
    if (autoScroll.value && scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight
  })
}
watch(visible, scrollDown, { deep: true })

function stopTask(id) { api.stopTask(id).then(() => {}) }

onMounted(() => {
  if (initialTask) taskFilter.value = initialTask
  loadMeta()
  loadHist()
})
</script>

<template>
  <div class="layout-with-sidebar" :class="{ collapsed: sidebarCollapsed }">
    <!-- 粘性侧边栏：运行中任务 + 上下文 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <span>⏱️ 运行中</span>
        <button class="sidebar-toggle" @click="emit('toggle-sidebar')">{{ sidebarCollapsed ? '›' : '‹' }}</button>
      </div>
      <div class="sidebar-content">
        <div v-if="(store.running || []).filter(r => r.running).length">
          <div v-for="r in (store.running || []).filter(x => x.running)" :key="r.id" class="run-row" style="margin-bottom:6px">
            <span class="pulse"></span>
            <span style="font-weight:500;font-size:13px;flex:1">{{ r.id }}</span>
            <button class="btn sm danger" @click="stopTask(r.id)" style="padding:3px 8px;font-size:11px">■</button>
          </div>
        </div>
        <div v-else class="muted" style="font-size:13px;padding:8px 0">暂无运行中任务</div>

        <div style="margin-top:24px">
          <div class="muted" style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px">节点数</div>
          <div style="font-family:var(--font-mono);font-size:13px">{{ uniqueNodes().length }}</div>
        </div>

        <div style="margin-top:16px">
          <div class="muted" style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px">日志条目</div>
          <div style="font-family:var(--font-mono);font-size:13px">{{ visible.length }}</div>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div>
      <!-- Hero -->
      <div class="hero">
        <div class="hero-grid">
          <div class="hero-title">
            <h2><span class="hero-icon">◉</span> 实时监控</h2>
            <span class="hero-sub">ROS2 拓扑 + 终端日志 · 按任务/节点/等级过滤 · 新任务自动分割线</span>
          </div>
          <div class="hero-actions">
            <span class="hero-status" v-if="taskFilter || nodeFilter || levelFilter">
              <span class="dot ok"></span>
              已过滤
            </span>
            <button class="btn" @click="showTopo = !showTopo">
              {{ showTopo ? '🙈 隐藏拓扑' : '🧭 显示拓扑' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 拓扑图（默认折叠为一条）-->
      <div v-if="!showTopo" class="collapse-bar" @click="showTopo = true">
        <span class="collapse-icon">▶</span>
        <span>🧭 ROS2 拓扑图 · 节点 ↔ 话题通信</span>
        <span class="spacer"></span>
        <span class="muted" style="font-size:11px">点击展开</span>
      </div>
      <div v-else class="collapse-body">
        <div class="collapse-bar expanded" @click="showTopo = false" style="margin-bottom:8px">
          <span class="collapse-icon">▼</span>
          <span>🧭 ROS2 拓扑图</span>
          <span class="spacer"></span>
          <span class="muted" style="font-size:11px">点击折叠</span>
        </div>
        <TopologyView />
      </div>

      <!-- Chips 风格筛选 -->
      <div class="card log-filter-bar">
        <div class="filter-chips">
          <span class="filter-chip" :class="{ active: !!taskFilter }">
            <span>📋 任务:</span>
            <select v-model="taskFilter">
              <option value="">全部</option>
              <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name || t.id }}</option>
              <option v-for="tid in Object.keys(store.perTask)" v-if="!tasks.find(t=>t.id===tid)" :key="'rt'+tid" :value="tid">
                运行中: {{ tid }}
              </option>
            </select>
          </span>
          <span class="filter-chip" :class="{ active: !!nodeFilter }">
            <span>📡 节点:</span>
            <select v-model="nodeFilter">
              <option value="">全部</option>
              <option v-for="n in uniqueNodes()" :key="n" :value="n">{{ n }}</option>
            </select>
          </span>
          <span class="filter-chip" :class="{ active: !!levelFilter }">
            <span>⚡ 等级:</span>
            <select v-model="levelFilter">
              <option value="">全部</option>
              <option value="debug">debug</option>
              <option value="info">info</option>
              <option value="warn">warn</option>
              <option value="error">error</option>
              <option value="fatal">fatal</option>
            </select>
          </span>
          <span class="spacer"></span>
          <label class="filter-chip">
            <input type="checkbox" v-model="autoScroll" style="margin:0"> 自动滚动
          </label>
          <button class="btn sm danger" @click="clearLogs">🗑️ 清除</button>
          <button class="btn sm" @click="loadHist">⟳ 重载</button>
        </div>
      </div>

      <!-- 终端日志 -->
      <div class="card" style="margin-top:16px">
        <div class="flex" style="margin-bottom:12px">
          <h3 style="margin:0"><span class="card-h3-icon">🖥️</span> 终端日志
            <span v-if="loadingHist" class="muted" style="margin-left:8px;font-size:12px">加载中…</span>
          </h3>
          <span class="spacer"></span>
          <span class="muted" style="font-size:12px;font-family:var(--font-mono)">{{ visible.length }} 条</span>
        </div>
        <div ref="scrollBox" class="terminal" style="height:calc(100vh - 360px);min-height:380px">
          <div v-if="!visible.length" style="color:var(--muted);padding:40px 0;text-align:center">
            暂无日志（启动任务后实时输出）
          </div>
          <template v-for="e in visible" :key="e.seq">
            <div v-if="isTaskStart(e.seq)" class="log-divider">
              ━━━ 新任务启动：{{ e.task_id }} ━━━
            </div>
            <div class="log-line">
              <span class="lv" :class="'lv-' + e.level">{{ e.level.toUpperCase().padEnd(5, ' ') }}</span>
              <span class="nd" :title="e.node">{{ e.node ? '[' + e.node + ']' : '' }}</span>
              <span>{{ e.line }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>