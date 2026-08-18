<script setup>
// 分层有向图拓扑：dagre 布局 + d3-zoom 缩放平移 + 点击高亮 + 按包分组着色
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import dagre from 'dagre'
import { select } from 'd3-selection'
import { zoom, zoomIdentity } from 'd3-zoom'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  topics: { type: Array, default: () => [] }
})
const emit = defineEmits(['select'])

const NODE_W = 150, NODE_H = 26
const TOPIC_R = 8
const svgRef = ref(null)
const focusName = ref(null)   // 高亮的节点/话题名

// ---- dagre 布局 ----
// 图模型：节点 ↔ 话题，topic 作为中间节点
// 边：publisher → topic（pub），topic → subscriber（sub）
const layout = computed(() => {
  const g = new dagre.graphlib.Graph({ multigraph: true })
  g.setGraph({ rankdir: 'LR', nodesep: 18, edgesep: 14, ranksep: 70, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))

  const nodeMap = {}
  for (const n of props.nodes) {
    nodeMap[n.name] = n
    g.setNode(n.name, { kind: 'node', width: NODE_W, height: NODE_H, label: n.name, group: n.group })
  }
  // 话题作为节点
  for (const t of props.topics) {
    g.setNode(t.name, { kind: 'topic', width: TOPIC_R * 2, height: TOPIC_R * 2, label: t.name, type: t.type })
  }
  // 边
  const edges = []
  for (const t of props.topics) {
    for (const p of t.publishers || []) {
      if (nodeMap[p]) { g.setEdge(p, t.name, { kind: 'pub' }, `pub_${p}_${t.name}`); edges.push({ from: p, to: t.name, kind: 'pub', topic: t.name, ttype: t.type, node: p }) }
    }
    for (const s of t.subscribers || []) {
      if (nodeMap[s]) { g.setEdge(t.name, s, { kind: 'sub' }, `sub_${t.name}_${s}`); edges.push({ from: t.name, to: s, kind: 'sub', topic: t.name, ttype: t.type, node: s }) }
    }
  }
  dagre.layout(g)

  const positions = {}
  let maxX = 0, maxY = 0
  g.nodes().forEach(id => {
    const nd = g.node(id)
    positions[id] = { x: nd.x, y: nd.y, kind: nd.kind, group: nd.group, type: nd.type, w: nd.width, h: nd.height }
    if (nd.x > maxX) maxX = nd.x
    if (nd.y > maxY) maxY = nd.y
  })
  const edgePaths = []
  g.edges().forEach(e => {
    const ed = g.edge(e)
    if (ed && ed.points) edgePaths.push({ points: ed.points, name: e.name, kind: ed.kind })
  })
  return { positions, edges: edgePaths, width: maxX + NODE_W, height: maxY + NODE_H + 20, rawEdges: edges }
})

const groupColors = {
  '底盘驱动': '#3ddc84', '雷达驱动': '#5ce1a8', '相机驱动': '#4fc3f7',
  '遥控': '#ffb74d', '跟随': '#ffb74d', '建图': '#ba68c8', '导航': '#ba68c8',
  'RTAB': '#9575cd', '机械臂': '#ff8a65', '视觉检测': '#f06292',
  '语音': '#4db6ac', '可视化': '#90a4ae', 'TF': '#a1887f', '系统': '#78909c',
  '仿真/TF': '#a1887f',
}
function grpColor(g) { return groupColors[g] || '#90a4ae' }
function shortName(n) { return n.replace(/^\//, '').split('/').pop() || n }
function typeName(t) { return t ? t.split('/').pop() : '' }

// 辅助：dagre edge 点 → SVG path（贝塞尔）
function edgePath(e) {
  const pts = e.points
  if (!pts || !pts.length) return ''
  if (pts.length === 2) return `M ${pts[0].x} ${pts[0].y} L ${pts[1].x} ${pts[1].y}`
  let d = `M ${pts[0].x} ${pts[0].y}`
  for (let i = 1; i < pts.length - 1; i++) {
    const xc = (pts[i].x + pts[i + 1].x) / 2
    const yc = (pts[i].y + pts[i + 1].y) / 2
    d += ` Q ${pts[i].x} ${pts[i].y}, ${xc} ${yc}`
  }
  d += ` T ${pts[pts.length - 1].x} ${pts[pts.length - 1].y}`
  return d
}
// 选中节点/话题时返回原始对象（含 pub/sub 关系）供详情区
function nodeByName(name) {
  const n = props.nodes.find(x => x.name === name)
  return n ? { kind: 'node', name, group: n.group, publishers: n.publishers, subscribers: n.subscribers, srv: (n.srv_servers||[]).length } : { kind: 'node', name }
}
function topicByName(name) {
  const t = props.topics.find(x => x.name === name)
  return t ? { kind: 'topic', name, type: t.type, publishers: t.publishers, subscribers: t.subscribers } : { kind: 'topic', name }
}

// ---- 高亮：focus 节点/话题相关的所有边和端点 ----
const highlight = computed(() => {
  const f = focusName.value
  if (!f) return null
  const related = new Set([f])
  for (const e of layout.value.rawEdges) {
    if (e.node === f || e.topic === f) { related.add(e.node); related.add(e.topic) }
  }
  return related
})
function isDim(name) {
  const h = highlight.value
  return h && !h.has(name)
}
function edgeDim(e) {
  const h = highlight.value
  if (!h) return false
  return !(h.has(e.from) && h.has(e.to))
}

// ---- 缩放平移 ----
let zoomBeh = null
onMounted(() => {
  const svg = select(svgRef.value)
  zoomBeh = zoom().scaleExtent([0.3, 3]).on('zoom', (ev) => {
    select(svgRef.value).select('.topo-g').attr('transform', ev.transform)
  })
  svg.call(zoomBeh)
})
function resetZoom() {
  const svg = select(svgRef.value)
  svg.transition().duration(300).call(zoomBeh.transform, zoomIdentity)
}
function fitView() {
  const svg = svgRef.value
  if (!svg) return
  const bbox = svg.querySelector('.topo-g').getBBox()
  const pad = 30
  const sx = (svg.clientWidth - pad * 2) / bbox.width
  const sy = (svg.clientHeight - pad * 2) / bbox.height
  const scale = Math.min(sx, sy, 1.2)
  const tx = pad - bbox.x * scale + (svg.clientWidth - bbox.width * scale) / 2
  const ty = pad - bbox.y * scale + (svg.clientHeight - bbox.height * scale) / 2
  select(svg).transition().duration(400).call(zoomBeh.transform, zoomIdentity.translate(tx, ty).scale(scale))
}

// 节点变化后自动 fit
watch(() => [props.nodes.length, props.topics.length], () => {
  nextTick(() => setTimeout(fitView, 80))
}, { immediate: true })

onUnmounted(() => {})
</script>

<template>
  <div class="topo-wrap">
    <div class="topo-toolbar">
      <button class="btn sm" @click="resetZoom" title="重置缩放">⟳ 重置</button>
      <button class="btn sm" @click="fitView" title="适应窗口">⊡ 适应</button>
      <span class="muted" style="font-size:12px">{{ nodes.length }} 节点 · {{ topics.length }} 话题</span>
      <span class="spacer" style="flex:1"></span>
      <span v-if="focusName" class="muted" style="font-size:12px">聚焦：{{ shortName(focusName) }}
        <a href="#" @click.prevent="focusName=null" style="color:var(--accent)">✕</a>
      </span>
    </div>
    <div class="topo-canvas">
      <svg ref="svgRef" class="topo-svg" :style="{ height: Math.max(360, layout.height) + 'px' }">
        <defs>
          <marker id="ap_pub" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <polygon points="0 0,6 3.5,0 7" fill="#ff9d3d"/>
          </marker>
          <marker id="ap_sub" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <polygon points="0 0,6 3.5,0 7" fill="#4da3ff"/>
          </marker>
        </defs>
        <g class="topo-g">
          <!-- 连线 -->
          <g v-for="(e, i) in layout.edges" :key="'e'+i" :opacity="edgeDim(e) ? 0.12 : 0.85">
            <path :d="edgePath(e)" fill="none"
              :stroke="e.kind === 'pub' ? '#ff9d3d' : '#4da3ff'"
              :stroke-width="focusName ? (edgeDim(e) ? 1 : 2.4) : 1.4"
              :stroke-dasharray="e.kind === 'sub' ? '5 4' : ''"
              :marker-end="`url(#ap_${e.kind})`"
              @click="emit('select', {kind:'topic', name:e.topicName, type:e.ttype, publishers:[], subscribers:[]})"/>
          </g>
          <!-- 话题节点 -->
          <g v-for="(p, name) in layout.positions" :key="'t'+name" v-if="false"></g>
          <template v-for="(p, name) in layout.positions" :key="name">
            <g v-if="p.kind === 'topic'"
               :transform="`translate(${p.x - TOPIC_R}, ${p.y - TOPIC_R})`"
               :opacity="isDim(name) ? 0.15 : 1" style="cursor:pointer"
               @click="focusName = (focusName === name ? null : name); emit('select', topicByName(name))">
              <circle :cx="TOPIC_R" :cy="TOPIC_R" :r="TOPIC_R" fill="#1d2740" stroke="#b083ff" stroke-width="1.6"/>
              <text :x="TOPIC_R" :y="-4" text-anchor="middle" class="topo-tname">{{ shortName(name) }}</text>
              <text :x="TOPIC_R" :y="TOPIC_R * 2 + 12" text-anchor="middle" class="topo-ttype">{{ typeName(p.type) }}</text>
            </g>
          </template>
          <!-- 节点 -->
          <template v-for="(p, name) in layout.positions" :key="'n'+name">
            <g v-if="p.kind === 'node'"
               :transform="`translate(${p.x - NODE_W/2}, ${p.y - NODE_H/2})`"
               :opacity="isDim(name) ? 0.2 : 1" style="cursor:pointer"
               @click="focusName = (focusName === name ? null : name); emit('select', nodeByName(name))">
              <rect :width="NODE_W" :height="NODE_H" rx="5"
                :fill="focusName === name ? grpColor(p.group) : '#161d2e'"
                :stroke="grpColor(p.group)" stroke-width="1.4"/>
              <text :x="NODE_W/2" :y="NODE_H/2 + 4" text-anchor="middle" class="topo-nname"
                :fill="focusName === name ? '#07111f' : '#dbe4f3'">{{ shortName(name) }}</text>
              <text :x="NODE_W/2" :y="-4" text-anchor="middle" class="topo-grp">{{ p.group }}</text>
            </g>
          </template>
        </g>
      </svg>
    </div>
  </div>
</template>

