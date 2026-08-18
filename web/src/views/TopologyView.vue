<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import TopoCanvas from './TopoCanvas.vue'

const data = ref(null)
const loading = ref(true)
const error = ref('')
const selected = ref(null)
const lastFmt = ref('')
const showSrv = ref(false)
const showParams = ref(true)   // 是否过滤 /rosout, /parameter_events 噪声

async function load() {
  try {
    const d = await api.topology()
    data.value = d
    lastFmt.value = new Date().toLocaleTimeString()
    error.value = ''
  } catch (e) { error.value = String(e) }
  loading.value = false
}

// 过滤噪声话题（除非勾选显示）
const filtered = computed(() => {
  if (!data.value) return { nodes: [], topics: [], services: [], actions: [] }
  const topics = (data.value.topics || []).filter(t =>
    !showParams.value || (t.name !== '/rosout' && !t.name.startsWith('/parameter_events'))
  )
  return { nodes: data.value.nodes || [], topics,
           services: data.value.services || [], actions: data.value.actions || [] }
})

function onSelect(o) { selected.value = o }

onMounted(load)
</script>

<template>
  <div class="card topo-card">
    <div class="flex" style="margin-bottom:8px;flex-wrap:wrap">
      <h3 style="margin:0">🧭 ROS2 拓扑图 <span class="muted" style="font-weight:400;font-size:12px">节点 ↔ 话题通信（rqt_graph 风格）</span></h3>
      <div class="spacer"></div>
      <label style="font-size:12px;color:var(--muted);display:flex;gap:4px;align-items:center">
        <input type="checkbox" v-model="showParams"> 隐去 rosout/参数
      </label>
      <span class="muted" style="font-size:12px">{{ lastFmt }}</span>
      <button class="btn sm" @click="load">↻ 刷新</button>
    </div>

    <div v-if="loading" class="empty" style="padding:30px">正在读取 ROS2 图…</div>
    <div v-else-if="error" class="warn">拓扑加载失败：{{ error }}</div>
    <div v-else-if="!filtered.nodes.length" class="empty" style="padding:30px">
      🕸 当前无活动节点（启动任意机器人功能后此处会显示节点与话题通信拓扑）
    </div>

    <template v-else>
      <TopoCanvas :nodes="filtered.nodes" :topics="filtered.topics" @select="onSelect" />
      <div class="legend">
        <span><i class="lg pub"></i> 发布</span>
        <span><i class="lg sub"></i> 订阅</span>
        <span><i class="lg node"></i> 节点（按分组着色）</span>
        <span><i class="lg topic"></i> 话题</span>
        <span class="muted" style="font-size:11px">滚轮缩放 · 拖拽平移 · 点击聚焦</span>
      </div>

      <div v-if="selected" class="sel-detail">
        <b>{{ selected.kind === 'node' ? '📦 节点' : '🔔 话题' }}：{{ selected.name }}</b>
        <span v-if="selected.type" class="muted">（{{ selected.type }}）</span>
        <div class="muted" style="font-size:12px;margin-top:4px">
          <template v-if="selected.kind === 'node'">
            <span v-if="selected.publishers?.length">发布：{{ selected.publishers.map(t=>t.name).join(', ') }}</span>
            <template v-if="selected.subscribers?.length">
              <br>订阅：{{ selected.subscribers.map(t=>t.name).join(', ') }}
            </template>
          </template>
          <template v-else>
            <span v-if="selected.publishers?.length">发布者：{{ selected.publishers.join(', ') }}</span>
            <template v-if="selected.subscribers?.length">
              <br>订阅者：{{ selected.subscribers.join(', ') }}
            </template>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
