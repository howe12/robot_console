<script setup>
import { ref, onMounted, onUnmounted, inject, defineProps, defineEmits } from 'vue'
import { api } from '../api'
import Icon from '../components/Icon.vue'

const props = defineProps({
  sidebarCollapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-sidebar'])

const store = inject('logStore')
const camHref = ref('')
const camState = ref('未连接')
const velState = ref('v=0.0  w=0.0')
const foxgloveOn = ref(false)
const foxgloveTip = ref('')
const speedLimit = ref(0.25)
const turnLimit = ref(0.6)

// 速度预设
const presets = [
  { lin: 0.10, ang: 0.30, label: '慢' },
  { lin: 0.25, ang: 0.60, label: '中' },
  { lin: 0.40, ang: 0.90, label: '快' }
]
const presetActive = ref(1)

const keys = { w: false, a: false, s: false, d: false }
function sendVel() {
  let fwd = (keys.w ? 1 : 0) - (keys.s ? 1 : 0)
  let turn = (keys.d ? 1 : 0) - (keys.a ? 1 : 0)
  const lin = fwd * speedLimit.value
  const ang = turn * turnLimit.value
  api.cmdVel(lin, ang).catch(() => {})
}
function drive(dir) {
  if (dir === ' ') { keys.w = keys.a = keys.s = keys.d = false }
  else if (['w','a','s','d'].includes(dir)) { keys[dir] = true }
  sendVel(); updateVelText()
}
function release(dir) {
  if (['w','a','s','d'].includes(dir)) { keys[dir] = false }
  sendVel(); updateVelText()
}
function stopAll() {
  keys.w = keys.a = keys.s = keys.d = false
  api.cmdVel(0, 0).catch(() => {})
  updateVelText()
}
function updateVelText() {
  const lin = ((keys.w ? 1 : 0) - (keys.s ? 1 : 0)) * speedLimit.value
  const ang = ((keys.d ? 1 : 0) - (keys.a ? 1 : 0)) * turnLimit.value
  velState.value = `v=${lin.toFixed(2)}  w=${ang.toFixed(2)}`
}
function setPreset(i) {
  presetActive.value = i
  speedLimit.value = presets[i].lin
  turnLimit.value = presets[i].ang
  sendVel()
  updateVelText()
}

function onKeyDown(e) {
  const k = e.key.toLowerCase()
  if (['w','a','s','d',' '].includes(k)) { e.preventDefault(); drive(k) }
}
function onKeyUp(e) {
  const k = e.key.toLowerCase()
  if (['w','a','s','d'].includes(k)) release(k)
}

function startCam() {
  camHref.value = '/api/camera/stream'
  camState.value = '连接中…'
  const img = new Image()
  img.onerror = () => { camState.value = '无画面（请启动相机任务）' }
  img.onload = () => { camState.value = '在线' }
}
function checkFoxglove() {
  foxgloveOn.value = (store.running || []).some(r => r.running && (r.cmd || '').includes('foxglove'))
  foxgloveTip.value = foxgloveOn.value ? '' : '提示：Foxglove 桥接未运行，先在「Tasks」启动「3D 可视化服务（Foxglove）」'
}
function startFoxglove() { api.startTask('foxglove', {}).then(() => checkFoxglove()) }
function stopFoxglove() { api.stopTask('foxglove').then(() => checkFoxglove()) }

const sysDevices = ref({ camera: null, base: null, lidar: null, arm: null })
async function refreshDevices() {
  try {
    const s = await api.systemStatus()
    sysDevices.value = s.devices || {}
  } catch (e) {}
}

async function startBringup() {
  try {
    const r = await api.startCustom('spark_bringup', 'driver_bringup.launch.py', {
      start_base: 'true', start_camera: 'true', start_lidar: 'true', start_bringup_rviz: 'false'
    })
    if (!r.ok) alert(r.error || '启动失败')
    setTimeout(() => { startCam(); refreshDevices() }, 2500)
  } catch (e) { alert('启动失败: ' + e) }
}

let statusTimer = null
onMounted(() => {
  startCam()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  checkFoxglove()
  refreshDevices()
  statusTimer = setInterval(() => { checkFoxglove(); refreshDevices() }, 4000)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<template>
  <div class="layout-with-sidebar" :class="{ collapsed: sidebarCollapsed }">
    <!-- 粘性侧边栏：设备清单 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <Icon name="cubeBox" size="md" />
        <span>设备清单</span>
        <button class="sidebar-toggle" @click="emit('toggle-sidebar')">{{ sidebarCollapsed ? '›' : '‹' }}</button>
      </div>
      <div class="sidebar-content">
        <div class="device-list">
          <div class="device-row">
            <span class="device-light" :class="sysDevices.camera?.connected ? 'ok' : 'bad'"></span>
            <span class="device-name">相机</span>
            <span class="device-type">{{ sysDevices.camera?.type || '-' }}</span>
          </div>
          <div class="device-row">
            <span class="device-light" :class="sysDevices.base?.connected ? 'ok' : 'bad'"></span>
            <span class="device-name">底盘</span>
            <span class="device-type">{{ sysDevices.base?.type || '-' }}</span>
          </div>
          <div class="device-row">
            <span class="device-light" :class="sysDevices.lidar?.connected ? 'ok' : 'bad'"></span>
            <span class="device-name">雷达</span>
            <span class="device-type">{{ sysDevices.lidar?.type || '-' }}</span>
          </div>
          <div class="device-row">
            <span class="device-light" :class="sysDevices.arm?.connected ? 'ok' : 'bad'"></span>
            <span class="device-name">机械臂</span>
            <span class="device-type">{{ sysDevices.arm?.type || '-' }}</span>
          </div>
        </div>

        <div style="margin-top:20px">
          <button class="btn primary" style="width:100%" @click="startBringup"><Icon name="bolt" size="sm" /> 一键启动底盘</button>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div>
      <!-- Hero -->
      <div class="hero">
        <div class="hero-grid">
          <div class="hero-title">
            <h2><Icon name="visual" size="xl" class="hero-icon" /> 可视化控制</h2>
            <span class="hero-sub">实时相机画面 · WASD 速度遥控 · Foxglove 3D 视图（端口 8765）</span>
          </div>
          <div class="hero-actions">
            <span class="hero-status">
              <span class="dot" :class="camState === '在线' ? 'ok' : (camState === '连接中…' ? 'idle' : 'bad')"></span>
              相机 {{ camState }}
            </span>
            <button class="btn" @click="startCam"><Icon name="refresh" size="sm" /> 重连</button>
          </div>
        </div>
      </div>

      <!-- 相机 Hero + 遥控面板 并列 -->
      <div class="grid grid-2" style="margin-top:8px">
        <div class="card glow">
          <h3><Icon name="camera" size="md" class="card-h3-icon" /> 相机画面 · 16:10</h3>
          <div class="cam-hero">
            <div class="cam-film top">REC · {{ camState }}</div>
            <img v-if="camHref" :src="camHref" alt="相机画面" />
            <div v-else class="empty" style="padding:60px">相机未连接</div>
            <div class="cam-film bottom">FOX-LIVE · D435</div>
          </div>
        </div>

        <div class="card glow">
          <h3><Icon name="speed" size="md" class="card-h3-icon" /> 速度控制
            <span class="muted" style="font-weight:400;margin-left:8px;font-family:var(--font-mono)">{{ velState }}</span>
          </h3>

          <div style="margin-bottom:14px">
            <div class="muted" style="font-size:11px;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">速度预设</div>
            <div class="speed-presets">
              <button v-for="(p, i) in presets" :key="i"
                class="speed-pill" :class="{ active: presetActive === i }"
                @click="setPreset(i)">
                {{ p.label }} · {{ p.lin }}m/s
              </button>
            </div>
          </div>

          <div style="text-align:center;margin:18px 0">
            <div class="pad-row">
              <button class="pad" :class="{ active: keys.w }"
                @mousedown="drive('w')" @mouseup="release('w')" @mouseleave="release('w')">▲<br>W</button>
            </div>
            <div class="pad-row">
              <button class="pad" :class="{ active: keys.a }"
                @mousedown="drive('a')" @mouseup="release('a')" @mouseleave="release('a')">◀<br>A</button>
              <button class="pad pad-stop" @mousedown="stopAll">■</button>
              <button class="pad" :class="{ active: keys.d }"
                @mousedown="drive('d')" @mouseup="release('d')" @mouseleave="release('d')">▶<br>D</button>
            </div>
            <div class="pad-row">
              <button class="pad" :class="{ active: keys.s }"
                @mousedown="drive('s')" @mouseup="release('s')" @mouseleave="release('s')">▼<br>S</button>
            </div>
            <div class="muted" style="font-size:11px;margin-top:10px">按住 WASD 移动 · 空格急停 · 键盘可用</div>
          </div>
        </div>
      </div>

      <!-- Foxglove 3D 视图 -->
      <div class="card glow" style="margin-top:16px">
        <div class="flex" style="margin-bottom:12px">
          <h3 style="margin:0"><Icon name="layers" size="md" class="card-h3-icon" /> 3D 视图（Foxglove · 端口 8765）</h3>
          <div class="spacer"></div>
          <span class="warn" style="font-size:12px" v-if="!foxgloveOn && foxgloveTip">{{ foxgloveTip }}</span>
          <button class="btn sm primary" @click="startFoxglove" v-if="!foxgloveOn" style="margin-left:8px"><Icon name="play" size="sm" /> 启动 Foxglove</button>
          <button class="btn sm danger" @click="stopFoxglove" v-else style="margin-left:8px"><Icon name="stop" size="sm" /> 停止</button>
          <a class="btn sm ghost" href="https://app.foxglove.dev/" target="_blank" rel="noopener" style="margin-left:8px">Foxglove 网页 <Icon name="arrowRightCircle" size="sm" /></a>
        </div>
        <div class="foxglove-box">
          <iframe
            :src="foxgloveOn
              ? 'https://app.foxglove.dev/view?ds=ws&ds.url=ws://' + location.hostname + ':8765'
              : 'about:blank'"
            title="Foxglove 3D 可视化"></iframe>
          <div v-if="!foxgloveOn" style="position:absolute;inset:0;background:var(--bg2);display:flex;flex-direction:column;gap:8px;align-items:center;justify-content:center">
            <Icon name="layers" size="xl" />
            <span style="color:var(--muted)">启动 Foxglove 桥接后此处嵌入 3D / 雷达 / TF / 地图视图</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>