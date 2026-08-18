<script setup>
import { ref, inject, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { api } from '../api'
import TopologyView from './TopologyView.vue'

const store = inject('logStore')
const taskFilter = ref('')
const nodeFilter = ref('')
const levelFilter = ref('')
const tailN = ref(500)
const nodes = ref([])
const tasks = ref([])
const scrollBox = ref(null)
const autoScroll = ref(true)
const showTopo = ref(true)
const initialTask = new URLSearchParams(location.hash.split('?')[1] || '').get('task') || ''

// ---- 新任务分割线 ----
const taskStartMarkers = ref(new Set())  // seq 集合，标记哪些 seq 是新任务启动时的第一条
let prevRunningIds = new Set()

watch(() => store.running, (newRunning) => {
  const newIds = new Set((newRunning || []).filter(r => r.running).map(r => r.id))
  for (const id of newIds) {
    if (!prevRunningIds.has(id)) {
      // 新任务启动：在当前最新日志条目上标记分割线
      const entries = store.perTask[id] || []
      if (entries.length) {
        taskStartMarkers.value.add(entries[0].seq)
      }
    }
  }
  prevRunningIds = newIds
}, { deep: true })

function isTaskStart(seq) {
  return taskStartMarkers.value.has(seq)
}

// ---- 清除日志 ----
function clearLogs() {
  if (taskFilter.value) {
    store.perTask[taskFilter.value] = []
  } else {
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

// 历史日志（首次加载或切换过滤时）
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
  } catch (e) {
    hist.value = []
  }
  loadingHist.value = false
  scrollDown()
}

// 实时：从 store.perTask 取该任务日志并在前端过滤
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
watch(() => [taskFilter.value, nodeFilter.value, levelFilter.value], () => {
  loadHist()
})

function scrollDown() {
  nextTick(() => {
    if (autoScroll.value && scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight
  })
}
watch(visible, scrollDown, { deep: true })

function stopTask(id) {
  api.stopTask(id).then(() => {})
}

onMounted(() => {
  if (initialTask) taskFilter.value = initialTask
  loadMeta()
  loadHist()
})
onUnmounted(() => {})
</script>

<template>
  <div>
    <div class="page-title">
      <h2>📜 实时监控</h2>
      <small>ROS2 拓扑（节点/话题通信）+ 终端日志（按 节点/等级 过滤）</small>
      <div class="spacer"></div>
      <button class="btn ghost" @click="showTopo = !showTopo">{{ showTopo ? '🙈 隐藏拓扑' : '🧭 显示拓扑' }}</button>
    </div>

    <!-- ROS2 拓扑图 -->
    <div v-if="showTopo" style="margin-bottom:12px">
      <TopologyView />
    </div>

    <div class="card log-filter-bar" style="margin-bottom:12px">
      <div class="filter-row">
        <select v-model="taskFilter" class="filter-select">
          <option value="">— 全部任务 —</option>
          <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name || t.id }}</option>
          <option v-for="tid in Object.keys(store.perTask)" v-if="!tasks.find(t=>t.id===tid)" :key="'rt'+tid" :value="tid">
            运行中: {{ tid }}
          </option>
        </select>
        <select v-model="nodeFilter" class="filter-select">
          <option value="">— 全部节点 —</option>
          <option v-for="n in uniqueNodes()" :key="n" :value="n">{{ n }}</option>
        </select>
        <select v-model="levelFilter" class="filter-select">
          <option value="">— 全部等级 —</option>
          <option value="debug">debug</option>
          <option value="info">info</option>
          <option value="warn">warn</option>
          <option value="error">error</option>
          <option value="fatal">fatal</option>
        </select>
        <span class="spacer"></span>
        <label class="filter-check">
          <input type="checkbox" v-model="autoScroll"> 自动滚动
        </label>
        <button class="btn sm" @click="clearLogs">🗑️ 清除</button>
        <button class="btn sm" @click="loadHist">⟳ 重载</button>
      </div>
    </div>

    <div class="grid">
      <!-- 运行状态（侧栏） -->
      <div v-if="taskFilter" style="margin-bottom:10px" class="card">
        <h3>⏱️ 运行任务</h3>
        <div v-for="r in (store.running || []).filter(x => !taskFilter || x.id === taskFilter)" :key="r.id" class="run-row">
          <span class="pulse" v-if="r.running"></span>
          <span class="light" v-else :class="r.exit_code === 0 ? 'ok' : 'bad'" style="width:9px;height:9px;border-radius:50%"></span>
          <span>{{ r.id }}</span>
          <span class="muted" style="font-size:12px">pid {{ r.pid }} · {{ r.running ? '运行中' : 'exit ' + r.exit_code }}</span>
          <div class="spacer"></div>
          <button v-if="r.running" class="btn sm danger" @click="stopTask(r.id)">■ 停止</button>
        </div>
      </div>

      <div class="card">
        <div class="flex" style="margin-bottom:8px">
          <h3 style="margin:0">🖥️ 终端日志 <span v-if="loadingHist" class="muted">加载中…</span></h3>
          <span class="spacer"></span>
          <span class="muted" style="font-size:12px">{{ visible.length }} 条</span>
        </div>
        <div ref="scrollBox" class="terminal" style="height:calc(100vh - 260px)">
          <div v-if="!visible.length" style="color:var(--muted)">暂无日志（启动任务后实时输出）</div>
          <template v-for="e in visible" :key="e.seq">
            <div v-if="isTaskStart(e.seq)" class="log-divider">
              <span>━━━ 新任务启动：{{ e.task_id }} ━━━</span>
            </div>
            <div class="log-line">
              <span class="lv" :class="'lv-' + e.level">{{ e.level.toUpperCase().padEnd(5, ' ') }}
              </span>
              <span class="nd" :title="e.node">{{ e.node ? '[' + e.node + ']' : '' }}</span>
              <span>{{ e.line }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
