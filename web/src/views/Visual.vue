<script setup>
import { ref, onMounted, onUnmounted, inject } from 'vue'
import { api, cameraStreamURL } from '../api'

const store = inject('logStore')
const camHref = ref('')
const camState = ref('未连接')
const velState = ref('v=0.0  w=0.0')
const foxgloveOn = ref(false)
const foxgloveTip = ref('')

// ---- 遥控 ----
const keys = { w: false, a: false, s: false, d: false }
let velTimer = null
function sendVel() {
  let fwd = (keys.w ? 1 : 0) - (keys.s ? 1 : 0)
  let turn = (keys.d ? 1 : 0) - (keys.a ? 1 : 0)
  // 速度上限
  const lin = fwd * 0.25
  const ang = turn * 0.6
  api.cmdVel(lin, ang).catch(() => {})
}
function drive(dir) {
  if (dir === ' ') { keys.w = keys.a = keys.s = keys.d = false }
  else if (['w', 'a', 's', 'd'].includes(dir)) { keys[dir] = true }
  sendVel()
  updateVelText()
}
function release(dir) {
  if (['w', 'a', 's', 'd'].includes(dir)) { keys[dir] = false }
  sendVel()
  updateVelText()
}
function stopAll() {
  keys.w = keys.a = keys.s = keys.d = false
  api.cmdVel(0, 0).catch(() => {})
  updateVelText()
}
function updateVelText() {
  const lin = ((keys.w ? 1 : 0) - (keys.s ? 1 : 0)) * 0.25
  const ang = ((keys.d ? 1 : 0) - (keys.a ? 1 : 0)) * 0.6
  velState.value = `v=${lin.toFixed(2)}  w=${ang.toFixed(2)}`
}

function onKeyDown(e) {
  const k = e.key.toLowerCase()
  if (['w', 'a', 's', 'd', ' '].includes(k)) { e.preventDefault(); drive(k) }
}
function onKeyUp(e) {
  const k = e.key.toLowerCase()
  if (['w', 'a', 's', 'd'].includes(k)) { release(k) }
}

function startCam() {
  camHref.value = cameraStreamURL()
  camState.value = '连接中…'
  const img = new Image()
  img.onerror = () => { camState.value = '无画面（请启动相机任务）' }
  img.onload = () => { camState.value = '在线' }
}
function checkFoxglove() {
  foxgloveOn.value = (store.running || []).some(r => r.running && (r.cmd || '').includes('foxglove'))
  foxgloveTip.value = foxgloveOn.value ? '' : '提示：Foxglove 桥接未运行，先在「任务控制」启动 「3D可视化服务（Foxglove）」'
}
function startFoxglove() {
  api.startTask('foxglove', {}).then(() => { checkFoxglove() })
}
function stopFoxglove() {
  api.stopTask('foxglove').then(() => { checkFoxglove() })
}
async function startBringup() {
  // 便捷：一键启动底盘驱动（spark_bringup）
  try {
    const r = await api.startCustom('spark_bringup', 'driver_bringup.launch.py', {
      start_base: 'true', start_camera: 'true', start_lidar: 'true', start_bringup_rviz: 'false'
    })
    alert(r.ok ? '底盘驱动已启动' : r.error)
    setTimeout(() => startCam(), 2500)
  } catch (e) { alert('启动失败: ' + e) }
}

let statusTimer = null
onMounted(() => {
  startCam()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  checkFoxglove()
  statusTimer = setInterval(checkFoxglove, 4000)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<template>
  <div>
    <div class="page-title">
      <h2>🖥️ 可视化 &amp; 控制</h2>
      <small>相机 / 遥控 / 3D 视图（Foxglove）</small>
    </div>

    <div class="grid" style="grid-template-columns:1.4fr 1fr">
      <!-- 相机 -->
      <div class="card">
        <div class="flex" style="margin-bottom:8px;flex-wrap:wrap">
          <h3 style="margin:0">📷 相机画面</h3>
          <span class="spacer"></span>
          <span class="muted" style="font-size:12px" :class="camState === '在线' ? '' : 'warn'">{{ camState }}</span>
          <button class="btn sm" @click="startCam">↻ 重连</button>
        </div>
        <div style="border-radius:8px;overflow:hidden;background:#000;text-align:center;min-height:260px">
          <img v-if="camHref" :src="camHref" alt="相机画面" style="max-width:100%;max-height:60vh">
          <div v-else class="empty" style="padding:60px">相机未连接</div>
        </div>
      </div>

      <!-- 遥控 -->
      <div class="card">
        <h3>🎮 遥控面板 <span class="muted" style="font-weight:400">{{ velState }}</span></h3>
        <div style="text-align:center">
          <div class="flex" style="justify-content:center;margin:14px 0">
            <button class="btn primary" @click="startBringup">⚡ 一键启动底盘驱动</button>
          </div>
          <div class="pad-row">
            <button class="pad" @mousedown="drive('w')" @mouseup="release('w')" @mouseleave.stop="release('w')">▲<br>W</button>
          </div>
          <div class="pad-row">
            <button class="pad" @mousedown="drive('a')" @mouseup="release('a')" @mouseleave="release('a')">◀<br>A</button>
            <button class="pad pad-stop" @mousedown="stopAll()">■</button>
            <button class="pad" @mousedown="drive('d')" @mouseup="release('d')" @mouseleave="release('d')">▶<br>D</button>
          </div>
          <div class="pad-row">
            <button class="pad" @mousedown="drive('s')" @mouseup="release('s')" @mouseleave="release('s')">▼<br>S</button>
          </div>
          <p class="muted" style="font-size:12px">按住 WASD 移动，松开回零；空格急停。也可用键盘。</p>
        </div>

        <h3 style="margin-top:14px">🧊 3D 视图（Foxglove · 端口 8765）</h3>
        <div v-if="!foxgloveOn" class="warn" style="font-size:12px;margin-bottom:8px">{{ foxgloveTip }}</div>
        <div class="flex" style="margin-bottom:8px">
          <button class="btn sm primary" @click="startFoxglove" v-if="!foxgloveOn" style="color:#07111f">▶ 启动 Foxglove 桥接</button>
          <button class="btn sm danger" @click="stopFoxglove" v-else>■ 停止</button>
          <a class="btn sm ghost" href="https://app.foxglove.dev/" target="_blank" rel="noopener">Foxglove 网页 ↗</a>
        </div>
      </div>
    </div>

    <!-- Foxglove 内嵌 -->
    <div class="foxglove-box" style="margin-top:14px">
      <iframe
        :src="foxgloveOn
          ? 'https://app.foxglove.dev/view?ds=ws&ds.url=ws://' + location.hostname + ':8765'
          : 'about:blank'"
        title="Foxglove 3D 可视化"></iframe>
      <div v-if="!foxgloveOn" class="empty" style="position:absolute;inset:0;background:var(--bg2);display:flex;flex-direction:column;gap:8px;align-items:center;justify-content:center">
        <span style="font-size:40px">🧊</span>
        <span style="color:var(--muted)">启动 Foxglove 桥接后在此嵌入 3D / 雷达 / TF / 地图视图</span>
      </div>
    </div>
  </div>
</template>
