<script setup>
import { ref, reactive, inject, onMounted, computed } from 'vue'
import { api } from '../api'

const store = inject('logStore')
const tasks = ref([])
const workspace = ref(null)
const running = reactive([])
const msg = ref('')
const selected = ref(null)          // curated task
const selectedWs = ref(null)        // workspace {package, launch, args}
const pn = ref(null)                // 展开的 package 名
const paramVals = reactive({})
const wsParamVals = reactive({})

// ---- launch 源码弹窗 ----
const modal = ref(null)             // {package, launch, path, source} or null
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
  try {
    const t = await api.tasks()
    tasks.value = t.tasks || []
    // 默认选中第一个启用的功能，方便直接查看启动方式
    const first = t.tasks.find(x => x.enabled !== false)
    if (first && !selected.value) pickTask(first)
  } catch (e) { msg.value = '拉取任务失败: ' + e }
  try {
    const w = await api.workspace()
    workspace.value = w
  } catch (e) { /* optional */ }
  refreshRunning()
}
function refreshRunning() {
  api.status().then(s => {
    running.splice(0, running.length, ...(s.running || []))
  }).catch(() => {})
}

onMounted(loadAll)

function defaultVals(task) {
  const o = {}
  for (const [k, m] of Object.entries(task.params || {})) o[k] = (m.default ?? '')
  for (const c of task.choices || []) o[c.key] = c.default
  return o
}
function pickTask(t) {
  selected.value = t
  selectedWs.value = null
  Object.keys(paramVals).forEach(k => delete paramVals[k])
  Object.assign(paramVals, defaultVals(t))
}
function pickWs(pkg, launch) {
  selectedWs.value = { package: pkg, launch, args: launch.args }
  selected.value = null
  Object.keys(wsParamVals).forEach(k => delete wsParamVals[k])
  for (const [k, m] of Object.entries(launch.args || {})) wsParamVals[k] = m.default ?? (m.has_default !== false ? (m.default ?? '') : '')
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
async function doStartWs() {
  const w = selectedWs.value
  if (!w) return
  try {
    const params = {}
    for (const [k, v] of Object.entries(wsParamVals)) {
      if (v !== '' && v !== null && v !== undefined) {
        const meta = w.args[k] || {}
        params[k] = meta.type === 'bool' ? String(v) : meta.type === 'int' ? Number(v) : String(v)
      }
    }
    const r = await api.startCustom(w.package, w.launch.name, params)
    msg.value = r.ok ? `已启动 ${w.package}/${w.launch.name}` : r.error || '启动失败'
    refreshRunning()
  } catch (e) { msg.value = '启动异常: ' + e }
}
async function doStop(id) {
  await api.stopTask(id)
  msg.value = '已停止 ' + id
  setTimeout(() => msg.value = '', 3000)
  refreshRunning()
}

// ---- 启动命令（实时按参数生成，与后端 build_command 对应）----
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
  if (selected.value) {
    return selected.value.launch_cmd || ''
  }
  if (selectedWs.value) {
    const w = selectedWs.value
    const params = {}
    for (const [k, v] of Object.entries(wsParamVals)) { if (v !== '') params[k] = v }
    return launchCmd({ pkg: w.package, file: w.launch.name }, params)
  }
  return ''
}
// 复制命令到剪贴板
async function copyCmd(cmd) {
  try {
    await navigator.clipboard.writeText(cmd)
    msg.value = '命令已复制 ✓'
    setTimeout(() => msg.value = '', 2000)
  } catch (e) {
    msg.value = '复制失败（浏览器权限）'
  }
}

const runningActive = computed(() => running.filter(r => r.running))
const runningFinished = computed(() => running.filter(r => !r.running))
// 互斥：有其他任务运行时禁止启动新功能
const hasOtherRunning = computed(() => {
  const active = runningActive.value
  if (!active.length) return false
  // 如果当前选中的就是正在运行的那个，允许（重启自身）
  if (selected.value && active.some(r => r.id === selected.value.id)) return false
  if (selectedWs.value && active.some(r => r.id.includes(selectedWs.value.package))) return false
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
  <div>
    <div class="page-title">
      <h2>🚀 机器人功能</h2>
      <span class="muted">选择功能 → 调整参数 → 启动；可查看对应 launch 文件</span>
      <div class="spacer"></div>
      <button class="btn ghost" @click="loadAll">↻ 刷新</button>
      <span v-if="msg" style="color:var(--green)">{{ msg }}</span>
    </div>

    <div class="grid grid-2">
      <!-- 左侧：机器人功能列表 -->
      <div>
        <div class="card" style="margin-bottom:12px">
          <h3>🤖 机器人功能</h3>
          <div style="max-height:400px;overflow-y:auto;display:flex;flex-direction:column;gap:4px">
            <div v-for="t in tasks" :key="t.id"
              class="fn-item" :class="{ active: selected?.id === t.id && !selectedWs }"
              @click="pickTask(t)">
              <span v-if="t.enabled === false" class="tag red">禁用</span>
              <span class="fn-name" :style="{flex:1}">{{ t.name }}</span>
              <span class="tag">{{ t.menu ?? '—' }}</span>
              <button class="btn sm ghost" title="查看对应 launch 文件"
                @click.stop="openLaunchSource(t.launch_pkg || t.package, t.launch_file)"
                v-if="t.launch_file">📄</button>
            </div>
          </div>
        </div>

        <!-- 正在执行的功能 -->
        <div class="card running-panel" style="margin-bottom:12px">
          <h3>⏱️ 正在执行的功能</h3>
          <div v-if="(store.running || []).filter(r => r.running).length">
            <div v-for="r in (store.running || []).filter(r => r.running)" :key="r.id" class="run-row">
              <span class="pulse"></span>
              <span style="font-weight:600">{{ r.id }}</span>
              <span class="muted" style="font-size:12px">pid {{ r.pid }}</span>
              <div class="spacer"></div>
              <a class="btn sm" :href="'#/logs?task=' + r.id" style="color:var(--accent)">日志</a>
              <button class="btn sm danger" @click="doStop(r.id)">■ 停止</button>
            </div>
          </div>
          <div v-else class="empty" style="padding:16px;font-size:13px">暂无正在执行的功能</div>
        </div>

        <div class="card">
          <h3>🧩 工作空间自动分析（可自定义启动）</h3>
          <div style="max-height:300px;overflow-y:auto;display:flex;flex-direction:column;gap:4px">
            <div v-for="p in workspace?.launches || []" :key="p.package" style="margin-bottom:4px">
              <div class="flex" style="cursor:pointer" @click="pn = (pn === p.package ? null : p.package)">
                <span class="tag green">{{ p.package }}</span>
                <span class="muted" style="font-size:12px">{{ p.launch.length }} launch</span>
              </div>
              <div v-if="pn === p.package" style="padding-left:18px;display:flex;flex-direction:column;gap:3px">
                <div v-for="l in p.launch" :key="l.name" class="ws-item"
                  :class="{ active: selectedWs?.launch.name === l.name && selectedWs?.package === p.package }">
                  <button class="btn sm" style="flex:1;text-align:left" @click="pickWs(p.package, l)">• {{ l.name }}</button>
                  <button class="btn sm ghost" title="查看 launch 文件" @click="openLaunchSource(p.package, l.name)">📄</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：参数 + 启动方式 + 操作 + 运行列表 -->
      <div>
        <!-- 机器人功能参数 -->
        <div v-if="selected" class="card" style="margin-bottom:12px">
          <div class="flex">
            <h3 style="margin:0">▶ 启动：{{ selected.name }}</h3>
            <div class="spacer"></div>
            <button class="btn sm primary" :disabled="hasOtherRunning" @click="doStart(selected)">🚀 启动</button>
          </div>
          <p v-if="hasOtherRunning" class="warn" style="font-size:12px;margin-top:4px">⚠️ 「{{ otherRunningId }}」正在运行，请先停止后再启动新功能</p>
          <p class="desc muted" style="margin-top:4px">{{ selected.desc }}</p>

          <!-- 启动方式 -->
          <div class="launch-way" v-if="selected.launch_cmd">
            <div class="flex" style="margin-bottom:4px">
              <span class="muted" style="font-size:12px">🔧 启动方式</span>
              <div class="spacer"></div>
              <button class="btn sm ghost" @click="copyCmd(selected.launch_cmd)">📋 复制命令</button>
            </div>
            <code class="cmd">{{ selected.launch_cmd }}</code>
            <div class="flex" style="margin-top:6px;flex-wrap:wrap;gap:6px">
              <button class="btn sm" @click="openLaunchSource(selected.launch_pkg || selected.package, selected.launch_file)"
                v-if="selected.launch_file">📄 查看 launch 源码</button>
              <span class="muted" style="font-size:12px" v-if="selected.launch_path">{{ selected.launch_path }}</span>
            </div>
          </div>

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
        </div>

        <!-- 工作空间 launch 参数 -->
        <div v-if="selectedWs" class="card" style="margin-bottom:12px">
          <div class="flex">
            <h3 style="margin:0">▶ 启动：{{ selectedWs.package }} / {{ selectedWs.launch.name }}</h3>
            <div class="spacer"></div>
            <button class="btn sm primary" :disabled="hasOtherRunning" @click="doStartWs">🚀 启动</button>
          </div>
          <p v-if="hasOtherRunning" class="warn" style="font-size:12px;margin-top:4px">⚠️ 「{{ otherRunningId }}」正在运行，请先停止后再启动新功能</p>

          <!-- 启动方式 -->
          <div class="launch-way" style="margin-top:8px">
            <div class="flex" style="margin-bottom:4px">
              <span class="muted" style="font-size:12px">🔧 启动方式</span>
              <div class="spacer"></div>
              <button class="btn sm ghost" @click="copyCmd(currentLaunchCmd())">📋 复制命令</button>
            </div>
            <code class="cmd">{{ currentLaunchCmd() }}</code>
            <div style="margin-top:6px">
              <button class="btn sm" @click="openLaunchSource(selectedWs.package, selectedWs.launch.name)">📄 查看 launch 源码</button>
            </div>
          </div>

          <div v-if="Object.keys(selectedWs.args).length" v-for="(meta, k) in selectedWs.args" :key="k" class="param-row">
            <label :title="meta.desc">{{ k }}</label>
            <input type="text" v-model="wsParamVals[k]" placeholder="默认: {{ meta.default }}">
          </div>
          <div v-else class="muted" style="margin-bottom:8px">（未检测到可调参数，直接启动）</div>
        </div>

        <!-- 运行列表 -->
        <div class="card" style="margin-bottom:12px">
          <h3>⏱️ 运行状态</h3>
          <div v-if="runningActive.length">
            <div v-for="r in runningActive" :key="r.id" class="run-row">
              <span class="pulse"></span>
              <span style="font-weight:600">{{ r.id }}</span>
              <span class="muted" style="font-size:12px">pid {{ r.pid }}</span>
              <div class="spacer"></div>
              <a class="btn sm" :href="'#/logs?task=' + r.id" style="color:var(--accent)">日志</a>
              <button class="btn sm danger" @click="doStop(r.id)">■ 停止</button>
            </div>
          </div>
          <div v-else class="muted">暂无运行中的任务</div>
          <div v-if="runningFinished.length" style="margin-top:8px">
            <div class="muted" style="font-size:12px;margin-bottom:4px">最近结束：</div>
            <div v-for="r in runningFinished" :key="r.id" class="run-row stopped">
              <span class="light" :class="r.exit_code === 0 ? 'ok' : 'bad'" style="width:9px;height:9px;border-radius:50%"></span>
              <span>{{ r.id }}</span>
              <span class="muted" style="font-size:12px">exit {{ r.exit_code }}</span>
              <div class="spacer"></div>
              <a v-if="r.exit_code !== 0" href="#/logs" class="btn sm">查看日志</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- launch 源码弹窗 -->
    <div v-if="modal" class="modal-mask" @click.self="closeModal">
      <div class="modal">
        <div class="flex" style="margin-bottom:8px">
          <h3 style="margin:0">📄 {{ modal.package }} / {{ modal.launch }}</h3>
          <div class="spacer"></div>
          <button class="btn sm ghost" @click="closeModal">✕ 关闭</button>
        </div>
        <div class="muted" style="font-size:12px;margin-bottom:8px;word-break:break-all">路径：{{ modal.path || '…' }}</div>
        <div v-if="modalLoading" class="empty">加载中…</div>
        <div v-else-if="modalErr" class="warn">{{ modalErr }}</div>
        <pre v-else class="src-box">{{ modal.source }}</pre>
        <div class="flex" style="margin-top:8px">
          <button class="btn sm" @click="copyCmd(modal.path)">📋 复制路径</button>
        </div>
      </div>
    </div>
  </div>
</template>