<script setup>
import { ref, reactive, inject, onMounted, computed, defineProps, defineEmits } from 'vue'
import { api } from '../api'
import Icon from '../components/Icon.vue'

const props = defineProps({
  sidebarCollapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-sidebar'])

const store = inject('logStore')
const tasks = ref([])
const running = reactive([])
const msg = ref('')
const loading = ref(true)
const selected = ref(null)
const view = ref('curated')
const paramVals = reactive({})

// launch 源码弹窗
const modal = ref(null)
const modalLoading = ref(false)
const modalErr = ref('')
async function openLaunchSource(packageName, launchName) {
  if (!packageName || !launchName) { modalErr.value = '无 launch 文件'; return }
  modalLoading.value = true
  modalErr.value = ''
  modal.value = { package: packageName, launch: launchName, path: '', source: '' }
  try {
    const r = await api.launchSource(packageName, launchName)
    if (!r.ok) { modalErr.value = r.error || '获取失败'; return }
    modal.value = { package: r.package, launch: r.launch, path: r.path, source: r.source }
  } catch (e) { modalErr.value = String(e) }
  finally { modalLoading.value = false }
}
function closeModal() { modal.value = null; modalErr.value = '' }

async function loadAll() {
  loading.value = true
  try {
    const t = await api.tasks()
    tasks.value = t.tasks || []
    const first = t.tasks.find(x => x.enabled !== false)
    if (first && !selected.value) pickTask(first)
  } catch (e) { msg.value = '拉取任务失败: ' + e }
  refreshRunning()
  loading.value = false
}

// ====== Task templates（算法选择 + 参数配置）======
const taskTemplates = ref({})
const showParamDialog = ref(false)
const dialogTask = ref(null)
const dialogTemplateId = ref(null)
const dialogAlgoId = ref(null)
const paramValues = ref({})

async function loadTaskTemplates() {
  try {
    const r = await api.taskTemplates()
    taskTemplates.value = r.templates || {}
  } catch (e) {
    taskTemplates.value = {}
  }
}

function matchTemplateId(taskName) {
  if (!taskName) return null
  const lower = taskName.toLowerCase()
  if (/slam|gmapping|cartographer|建图/.test(lower)) return 'slam_2d'
  if (/navigat|amcl|nav2|导航/.test(lower)) return 'navigation_2d'
  if (/detect|yolo|ssd|检测|识别/.test(lower)) return 'detection'
  if (/follow|跟随/.test(lower)) return 'following'
  return null
}

async function pickTaskWithParams(t) {
  const tId = matchTemplateId(t.name)
  if (!tId || !taskTemplates.value[tId]) {
    return launchDiscovered(t)
  }
  dialogTask.value = t
  dialogTemplateId.value = tId
  const tpl = taskTemplates.value[tId]
  const firstAlgo = tpl.algorithms[0]
  dialogAlgoId.value = firstAlgo.id
  paramValues.value = {}
  for (const p of (firstAlgo.params_schema || [])) {
    paramValues.value[p.key] = p.default
  }
  showParamDialog.value = true
}

const currentTemplate = computed(() => taskTemplates.value[dialogTemplateId.value] || null)
const currentAlgo = computed(() => {
  const tpl = currentTemplate.value
  if (!tpl) return null
  return tpl.algorithms.find(a => a.id === dialogAlgoId.value) || tpl.algorithms[0]
})

function onAlgoChange(e) {
  dialogAlgoId.value = e.target.value
  if (!currentAlgo.value) return
  paramValues.value = {}
  for (const p of (currentAlgo.value.params_schema || [])) {
    paramValues.value[p.key] = p.default
  }
}

async function confirmTemplateLaunch() {
  if (!dialogTask.value || !dialogTemplateId.value || !dialogAlgoId.value) return
  const typed = {}
  for (const [k, v] of Object.entries(paramValues.value)) {
    const schema = (currentAlgo.value?.params_schema || []).find(p => p.key === k)
    if (schema?.type === 'number' && v !== '' && v !== null && v !== undefined) {
      typed[k] = String(Number(v))
    } else if (schema?.type === 'bool') {
      typed[k] = v ? 'true' : 'false'
    } else {
      typed[k] = String(v ?? '')
    }
  }
  try {
    const r = await api.startTemplate(dialogTemplateId.value, dialogAlgoId.value, typed)
    if (r.ok) {
      showParamDialog.value = false
      store.activeTab = 'tasks'
    } else {
      alert(r.error || '启动失败')
    }
  } catch (e) {
    alert('启动异常: ' + e)
  }
}

function launchDiscovered(t) {
  // 调用现有 /api/tasks/custom 启动
  api.startCustom(t.package, t.launch, t.params || {}).then(r => {
    if (r.ok) store.activeTab = 'tasks'
  })
}
function refreshRunning() {
  api.status().then(s => {
    running.splice(0, running.length, ...(s.running || []))
  }).catch(() => {})
}

onMounted(async () => {
  await loadAll()
  loadTaskTemplates()
})

function defaultVals(task) {
  const o = {}
  for (const [k, m] of Object.entries(task.params || {})) o[k] = (m.default ?? '')
  for (const c of task.choices || []) o[c.key] = c.default
  return o
}
// 智能提取禁用原因：优先 desc 中的「已禁用」「未启用」等关键短语
function disabledReason(t) {
  if (t.enabled !== false) return ''
  const desc = t.desc || ''
  // 1. 优先从 desc 中提取「（xxx 已禁用）」或「（xxx 未启用）」结构
  const m = desc.match(/[（(]([^）)]*?(已禁用|未启用|不存在|缺失|不可用)[^）)]*)[）)]/)
  if (m) return m[1].trim()
  // 2. 降级到「根据描述：xxx」
  return `根据描述：${desc.slice(0, 60)}`
}
function onPickCurated(t) {
  // 命中 task template(建图/导航/检测/跟随) → 弹算法选择 + 参数对话框；否则进常规详情
  const tId = matchTemplateId(t.name)
  if (tId && taskTemplates.value[tId]) return pickTaskWithParams(t)
  return pickTask(t)
}
function pickTask(t) {
  selected.value = t
  Object.keys(paramVals).forEach(k => delete paramVals[k])
  Object.assign(paramVals, defaultVals(t))
}

async function doStart(curated) {
  const t = curated
  try {
    const r = await api.startTask(t.id, paramVals)
    msg.value = r.ok ? `已启动 ${t.name}` : r.error || '启动失败'
    if (!r.ok) setTimeout(() => msg.value = '', 4000)
    refreshRunning()
  } catch (e) { msg.value = '启动异常: ' + e }
}
async function doStop(id) {
  await api.stopTask(id)
  msg.value = '已停止 ' + id
  setTimeout(() => msg.value = '', 3000)
  refreshRunning()
}

// 启动命令实时生成
function launchCmd(launchFile, paramsObj) {
  const args = []
  for (const [k, v] of Object.entries(paramsObj)) {
    if (v !== '' && v !== null && v !== undefined && v !== false) {
      args.push(`${k}:=${v}`)
    }
  }
  return args.length ? `ros2 launch ${launchFile.pkg} ${launchFile.file} ${args.join(' ')}`
                     : `ros2 launch ${launchFile.pkg} ${launchFile.file}`
}
function currentLaunchCmd() {
  if (selected.value) return selected.value.launch_cmd || ''
  return ''
}
async function copyCmd(cmd) {
  try {
    await navigator.clipboard.writeText(cmd)
    msg.value = '命令已复制 ✓'
    setTimeout(() => msg.value = '', 2000)
  } catch (e) { msg.value = '复制失败（浏览器权限）' }
}

const runningActive = computed(() => running.filter(r => r.running))
const runningFinished = computed(() => running.filter(r => !r.running))
const hasOtherRunning = computed(() => {
  const active = runningActive.value
  if (!active.length) return false
  if (selected.value && active.some(r => r.id === selected.value.id)) return false
  return true
})
const otherRunningId = computed(() => {
  const active = runningActive.value
  if (!active.length) return ''
  if (selected.value && active.some(r => r.id === selected.value.id)) return ''
  return active[0]?.id || ''
})
</script>

<template>
  <div class="layout-with-sidebar" :class="{ collapsed: sidebarCollapsed }">
    <!-- 粘性侧边栏：机器人功能列表 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <Icon name="tasks" size="md" />
        <span>功能列表</span>
        <button class="sidebar-toggle" @click="emit('toggle-sidebar')">
          {{ sidebarCollapsed ? '›' : '‹' }}
        </button>
      </div>
      <div class="sidebar-content">
        <!-- 视图切换 -->
        <div class="filter-chips" style="margin-bottom:14px">
          <button class="filter-chip" :class="{ active: view === 'curated' }" @click="view = 'curated'">精选 · {{ tasks.length }}</button>
        </div>

        <!-- 精选任务列表 -->
        <div v-if="view === 'curated'">
          <div v-for="t in tasks" :key="t.id"
            class="fn-item" :class="{
              active: selected?.id === t.id,
              disabled: t.enabled === false
            }"
            :title="t.enabled === false ? '⚠ 禁用：' + disabledReason(t) : t.desc"
            @click="t.enabled !== false && onPickCurated(t)">
            <span v-if="t.enabled === false" class="tag red" title="已禁用">禁用</span>
            <span class="fn-name" :title="t.name">{{ t.name }}</span>
            <span class="tag">{{ t.menu ?? '—' }}</span>
            <button class="btn sm ghost" title="查看 launch 文件"
              v-if="t.launch_file && t.enabled !== false"
              @click.stop="openLaunchSource(t.launch_pkg || t.package, t.launch_file)"><Icon name="file" size="sm" /></button>
          </div>
        </div>

        <!-- 算法选择 + 参数配置对话框（cover entire sidebar content area） -->
        <div v-if="showParamDialog" class="dialog-overlay" @click.self="showParamDialog = false">
          <div class="dialog">
            <div class="flex" style="margin-bottom:14px;align-items:center">
              <h3 style="margin:0;font-size:16px">⚙️ 配置：{{ dialogTask?.name }}</h3>
              <div class="spacer"></div>
              <button class="btn sm" @click="showParamDialog = false">✕</button>
            </div>
            <p v-if="currentTemplate" class="muted" style="font-size:12px;margin:0 0 14px">{{ currentTemplate.description }}</p>

            <label class="param-label">算法</label>
            <select :value="dialogAlgoId" @change="onAlgoChange" style="width:100%;padding:8px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;margin-bottom:6px">
              <option v-for="a in currentTemplate?.algorithms || []" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
            <p v-if="currentAlgo" class="muted" style="font-size:11px;margin:0 0 14px;line-height:1.5">{{ currentAlgo.description }}</p>

            <div v-for="p in currentAlgo?.params_schema || []" :key="p.key" style="margin-bottom:14px">
              <label class="param-label">{{ p.label }}</label>
              <input v-if="p.type === 'string'" :value="paramValues[p.key] || ''" @input="(e) => paramValues[p.key] = e.target.value" style="width:100%;padding:7px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--font-mono);font-size:12px" />
              <div v-else-if="p.type === 'number'" style="display:flex;align-items:center;gap:10px">
                <input type="range" :min="p.min ?? 0" :max="p.max ?? 100" :step="p.step ?? 1" :value="Number(paramValues[p.key] ?? p.default)" @input="(e) => paramValues[p.key] = Number(e.target.value)" style="flex:1" />
                <input type="number" :min="p.min" :max="p.max" :step="p.step ?? 1" :value="Number(paramValues[p.key] ?? p.default)" @input="(e) => paramValues[p.key] = Number(e.target.value)" style="width:90px;padding:6px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--font-mono);font-size:12px" />
                <span class="muted" style="font-size:11px;min-width:70px">当前: {{ paramValues[p.key] }}</span>
              </div>
              <label v-else-if="p.type === 'bool'" style="display:flex;align-items:center;gap:8px;cursor:pointer">
                <input type="checkbox" :checked="!!paramValues[p.key]" @change="(e) => paramValues[p.key] = e.target.checked" />
                <span>启用</span>
              </label>
              <select v-else-if="p.type === 'select'" :value="paramValues[p.key] || p.default" @change="(e) => paramValues[p.key] = e.target.value" style="width:100%;padding:7px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px">
                <option v-for="opt in p.options || []" :key="opt" :value="opt">{{ opt }}</option>
              </select>
            </div>

            <div style="display:flex;gap:10px;margin-top:20px;padding-top:14px;border-top:1px solid var(--border)">
              <button class="btn primary" @click="confirmTemplateLaunch" style="flex:1">🚀 启动（用当前参数）</button>
              <button class="btn" @click="showParamDialog = false">取消</button>
            </div>
          </div>
        </div>

        </div>
    </aside>

    <!-- 主内容区 -->
    <div>
      <!-- Hero -->
      <div class="hero">
        <div class="hero-grid">
          <div class="hero-title">
            <h2><Icon name="tasks" size="xl" class="hero-icon" /> 机器人功能</h2>
            <span class="hero-sub">选择功能 → 调整参数 → 启动 · 互斥保护：已有任务运行时禁止启动其他</span>
          </div>
          <div class="hero-actions">
            <span class="hero-status" v-if="msg" :style="msg.includes('失败')||msg.includes('异常') ? 'color:var(--yellow)' : ''">
              {{ msg }}
            </span>
            <button class="btn ghost" @click="loadAll"><Icon name="refresh" size="sm" /></button>
          </div>
        </div>
      </div>

      <!-- 加载中：骨架屏 -->
      <template v-if="loading">
        <!-- 侧栏骨架 -->
        <div class="card">
          <div class="skeleton text" style="width: 50%; margin-bottom: 14px"></div>
          <div v-for="i in 8" :key="'s'+i" class="fn-item" style="pointer-events:none">
            <div class="skeleton text" style="flex:1; height:14px"></div>
            <div class="skeleton text" style="width:24px; height:14px"></div>
          </div>
        </div>
        <!-- 详情骨架 -->
        <div class="card glow" style="margin-top:16px">
          <div class="skeleton text" style="width:40%; height:18px; margin-bottom:12px"></div>
          <div class="skeleton text" style="width:60%; margin-bottom:20px"></div>
          <div class="grid grid-2" style="gap:14px">
            <div>
              <div class="skeleton block" style="height:120px"></div>
            </div>
            <div>
              <div class="skeleton text" style="width:35%; margin-bottom:8px"></div>
              <div class="skeleton text" style="width:55%; margin-bottom:8px"></div>
              <div class="skeleton text" style="width:45%"></div>
            </div>
          </div>
        </div>
      </template>

      <!-- 主内容：选中时显示详情，否则显示 Hero + 提示 -->
      <template v-else>
      <div v-if="!selected" class="empty">
        <div style="font-size:48px;opacity:.3"><Icon name="tasks" size="xl" /></div>
        <div style="margin-top:12px">从左侧选择一个功能查看详情</div>
      </div>

      <!-- 精选任务详情 -->
      <div v-if="selected" class="card glow">
        <div class="flex" style="margin-bottom:14px">
          <h3 style="margin:0"><Icon name="play" size="md" class="card-h3-icon" /> {{ selected.name }}</h3>
          <div class="spacer"></div>
          <button class="btn sm primary" :disabled="hasOtherRunning" @click="doStart(selected)"><Icon name="rocket" size="sm" /> 启动</button>
        </div>
        <p class="muted" style="margin:0 0 16px;font-size:13px">{{ selected.desc }}</p>
        <p v-if="hasOtherRunning" class="warn" style="font-size:12px;margin:0 0 12px">
          ⚠️ 「{{ otherRunningId }}」正在运行，请先停止后再启动新功能
        </p>

        <!-- 启动方式 + 参数 并列 -->
        <div class="grid grid-2" style="gap:14px">
          <div class="launch-way">
            <div class="flex" style="margin-bottom:8px">
              <span class="muted" style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase">🔧 启动方式</span>
              <div class="spacer"></div>
              <button class="btn sm ghost" @click="copyCmd(selected.launch_cmd)" v-if="selected.launch_cmd"><Icon name="copy" size="sm" /> 复制命令</button>
            </div>
            <code class="cmd" v-if="selected.launch_cmd">{{ selected.launch_cmd }}</code>
            <div v-else class="muted" style="font-size:12px">（无可用启动命令）</div>
            <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
              <button class="btn sm" @click="openLaunchSource(selected.launch_pkg || selected.package, selected.launch_file)"
                v-if="selected.launch_file">查看 launch 源码</button>
              <span class="muted" style="font-size:11px;font-family:var(--font-mono);word-break:break-all" v-if="selected.launch_path">{{ selected.launch_path }}</span>
            </div>
          </div>

          <div>
            <div v-if="(selected.choices || []).length" class="param-row" v-for="c in selected.choices" :key="c.key">
              <label>{{ c.label }}</label>
              <select v-model="paramVals[c.key]">
                <option v-for="o in c.options" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div v-for="(meta, k) in selected.params || {}" :key="k" class="param-row">
              <label :title="meta.desc">{{ k }}</label>
              <input type="text" v-model="paramVals[k]" :placeholder="meta.default">
            </div>
            <div v-if="!selected.params || !Object.keys(selected.params).length" class="muted" style="font-size:12px">无可调参数</div>
          </div>
        </div>
      </div>

      <!-- 正在执行的功能（实时）-->
      <div class="card running-panel" style="margin-top:20px">
        <h3><Icon name="bolt" size="md" class="card-h3-icon" /> 正在执行的功能</h3>
        <div v-if="runningActive.length">
          <div v-for="r in runningActive" :key="r.id" class="run-row">
            <span class="pulse"></span>
            <span style="font-weight:600">{{ r.id }}</span>
            <span class="muted" style="font-size:12px;font-family:var(--font-mono)">pid {{ r.pid }}</span>
            <div class="spacer"></div>
            <a class="btn sm" :href="'#/logs?task=' + r.id" style="color:var(--accent)">日志</a>
            <button class="btn sm danger" @click="doStop(r.id)"><Icon name="stop" size="sm" /> 停止</button>
          </div>
        </div>
        <div v-else class="empty" style="padding:18px;font-size:13px">暂无正在执行的功能</div>
        <div v-if="runningFinished.length" style="margin-top:12px">
          <div class="muted" style="font-size:11px;letter-spacing:0.06em;margin-bottom:6px;text-transform:uppercase">最近结束</div>
          <div v-for="r in runningFinished" :key="r.id" class="run-row stopped">
            <span class="device-light" :class="r.exit_code === 0 ? 'ok' : 'bad'"></span>
            <span>{{ r.id }}</span>
            <span class="muted" style="font-size:12px;font-family:var(--font-mono)">exit {{ r.exit_code }}</span>
            <div class="spacer"></div>
            <a v-if="r.exit_code !== 0" href="#/logs" class="btn sm">查看日志</a>
          </div>
        </div>
      </div>
      </template>
    </div>

    <!-- launch 源码弹窗 -->
    <div v-if="modal" class="modal-mask" @click.self="closeModal">
      <div class="modal">
        <div class="flex" style="margin-bottom:8px">
          <h3 style="margin:0"><Icon name="file" size="md" /> {{ modal.package }} / {{ modal.launch }}</h3>
          <div class="spacer"></div>
          <button class="btn sm ghost" @click="closeModal"><Icon name="close" size="sm" /> 关闭</button>
        </div>
        <div class="muted" style="font-size:12px;margin-bottom:8px;word-break:break-all;font-family:var(--font-mono)">路径：{{ modal.path || '…' }}</div>
        <div v-if="modalLoading" class="empty">加载中…</div>
        <div v-else-if="modalErr" class="warn">{{ modalErr }}</div>
        <pre v-else class="src-box">{{ modal.source }}</pre>
        <div class="flex" style="margin-top:8px">
          <button class="btn sm" @click="copyCmd(modal.path)"><Icon name="copy" size="sm" /> 复制路径</button>
        </div>
      </div>
    </div>
  </div>
</template>