<script setup>
/**
 * SVG Icon 组件（SF Symbols 风格）
 * 设计原则：
 *   - 24×24 网格，圆角端点，stroke 1.5px
 *   - 单一图标以 path/symbol id 引用，全局 <defs> 在 index.html 或 App.vue 中提供
 *   - 调用：<Icon name="dashboard" /> 或 <Icon name="stop" size="lg" />
 */
const props = defineProps({
  name: { type: String, required: true },
  size: { type: String, default: '' },  // sm | md | lg | xl | '' (1em)
  solid: { type: Boolean, default: false },
})

// 所有图标定义：name -> svg path "d" 属性
// 每个图标都符合 SF Symbols 风格：圆角 stroke 1.5，统一 24px 网格
const icons = {
  // ── 导航 ──
  dashboard: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z',
  tasks: 'M9 2h6a2 2 0 0 1 2 2v1h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h3V4a2 2 0 0 1 2-2zm0 3v0h6V4H9v1zm-5 4v10h16V9H4z',
  logs: 'M4 4h16v2H4V4zm0 5h16v2H4V9zm0 5h10v2H4v-2zm0 5h7v2H4v-2zM18 14l4 4-4 4v-3h-4v-2h4v-3z',
  visual: 'M2 4h20v12H2V4zm0 14h7v2H2v-2zm9 0h11v2H11v-2z',

  // ── 系统 ──
  chip: 'M9 2v2H7v2H5v2H3v6h2v2h2v2h2v2h6v-2h2v-2h2v-2h2V8h-2V6h-2V4h-2V2H9zm0 2h6v2h2v2h2v8h-2v2h-2v2H9v-2H7v-2H5V8h2V6h2V4z',
  cpu: 'M4 4h16v16H4V4zm2 4v8h12V8H6z M2 9h2v2H2V9zm0 4h2v2H2v-2zm18-4h2v2h-2V9zm0 4h2v2h-2v-2zM9 2v2H7V2h2zm4 0v2h-2V2h2zm-4 18v2H7v-2h2zm4 0v2h-2v-2h2z',
  memory: 'M3 5h18v14H3V5zm2 2v10h14V7H5zm2 2h2v2H7V9zm4 0h2v2h-2V9zm4 0h2v2h-2V9zM7 13h2v2H7v-2zm4 0h2v2h-2v-2zm4 0h2v2h-2v-2z',

  // ── 状态 / 数据 ──
  rocket: 'M12 2l3 6-3 2-3-2 3-6zm-2 9l2 2 2-2v6l-2 2-2-2v-6zm-5 1l2 4-3 3 1-5zm14 0l1 5-3-3 2-4z',
  speed: 'M12 3a9 9 0 0 0-9 9 9 9 0 0 0 9 9 9 9 0 0 0 9-9 9 9 0 0 0-9-9zm0 2a7 7 0 0 1 7 7h-2.5l1.5 4-4-1.5L15.5 12H18a7 7 0 0 1-7 7v-2.5L9 18l-2.5-1.5L8 12H5a7 7 0 0 1 7-7z',
  signal: 'M4 4h4v16H4V4zm6 4h4v12h-4V8zm6-6h4v18h-4V2z',
  bolt: 'M13 2L4 14h6l-1 8 9-12h-6l1-8z',
  battery: 'M2 8h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H2V8zm18 3v2h2v-2h-2z M5 10v6h13v-6H5z',

  // ── 控制 ──
  play: 'M5 3l14 9-14 9V3z',
  stop: 'M5 5h14v14H5V5z',
  pause: 'M6 4h4v16H6V4zm8 0h4v16h-4V4z',
  refresh: 'M4 12a8 8 0 0 1 14-5.3L21 4v7h-7l2.3-2.3A6 6 0 0 0 6 12H4zm16 0a8 8 0 0 1-14 5.3L3 20v-7h7l-2.3 2.3A6 6 0 0 0 18 12h2z',
  power: 'M12 2v10h-2V2h2zm-7.1 4.1l1.4 1.4a8 8 0 0 0 11.4 0l1.4-1.4 1.4 1.4a10 10 0 0 1-14.2 0l-1.4-1.4zM12 13a9 9 0 0 0 9-9h-2a7 7 0 0 1-14 0H4a9 9 0 0 0 8 8.9V22h-1v2h4v-2h-1v-10.1z',
  send: 'M3 12L21 3l-7 18-3-8-8-1z',

  // ── UI ──
  check: 'M5 12l5 5L20 7l-1.4-1.4L10 14.2 6.4 10.6 5 12z',
  close: 'M6 6l12 12M18 6L6 18',
  chevronRight: 'M9 6l6 6-6 6',
  chevronDown: 'M6 9l6 6 6-6',
  chevronLeft: 'M15 6l-6 6 6 6',
  arrowUp: 'M12 4l-8 8h5v8h6v-8h5l-8-8z',
  arrowDown: 'M12 20l8-8h-5V4H9v8H4l8 8z',
  arrowLeft: 'M4 12l8-8v5h8v6h-8v5l-8-8z',
  arrowRight: 'M20 12l-8 8v-5H4v-6h8V4l8 8z',
  plus: 'M12 4v16M4 12h16',
  minus: 'M4 12h16',
  copy: 'M8 4h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2v12h10V6H8zM4 8v12a2 2 0 0 0 2 2h10v-2H6V8H4z',
  trash: 'M9 2h6l1 2h4v2H4V4h4l1-2zm-3 5h12l-1 14H7L6 7zm3 3v9h2v-9H9zm4 0v9h2v-9h-2z',

  // ── 通讯 / 网络 ──
  wifi: 'M2 8.5a14 14 0 0 1 20 0l-2 2a11 11 0 0 0-16 0l-2-2zm4 4a8 8 0 0 1 12 0l-2 2a5 5 0 0 0-8 0l-2-2zm4 4a4 4 0 0 1 4 4h-4v-4z',
  network: 'M12 2a3 3 0 0 1 3 3 3 3 0 0 1-3 3 3 3 0 0 1-3-3 3 3 0 0 1 3-3zm-7 8h14v2H5v-2zm1 4h12v8H6v-8zm3 2v4h6v-4H9z',
  graph: 'M3 3h2v18H3V3zm16 0h2v18h-2V3zM7 12l3-4 4 3 5-7v6h-2v-2l-3 4-4-3-2 3H7z',

  // ── 硬件 ──
  cube: 'M12 2l9 5v10l-9 5-9-5V7l9-5zm0 2.2L5 8v8l7 3.8V4.2zM19 8l-5 2.6v9l5-2.6V8z',
  cubeBox: 'M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3zm0 2L6 8.25v7.5l6 3.25 6-3.25v-7.5L12 5z',
  layers: 'M12 2l10 6-10 6L2 8l10-6zm0 9l10 6-10 6-10-6 10-6z',
  eye: 'M12 4.5C7 4.5 2.7 8 1 12c1.7 4 6 7.5 11 7.5s9.3-3.5 11-7.5c-1.7-4-6-7.5-11-7.5zm0 12a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9zm0-2a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  eyeOff: 'M3 3l18 18-1.4 1.4L16.5 19.4A12 12 0 0 1 12 19.5C7 19.5 2.7 16 1 12c.7-1.5 1.7-3 3-4.3L1.6 4.4 3 3zm9 5a4 4 0 0 1 4 4l-4-4z',

  // ── 数据 ──
  database: 'M12 3c-4.4 0-8 1.3-8 3v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0-1.7-3.6-3-8-3zm0 2c3.8 0 6 1 6 1.5S15.8 8 12 8s-6-1-6-1.5S8.2 5 12 5zm0 5c3.8 0 6 1 6 1.5s-2.2 1.5-6 1.5-6-1-6-1.5S8.2 10 12 10zm0 5c3.8 0 6 1 6 1.5s-2.2 1.5-6 1.5-6-1-6-1.5S8.2 15 12 15z',
  terminal: 'M3 3h18v18H3V3zm2 2v14h14V5H5zm2 3l4 4-4 4 1.4 1.4L13 13.4 17 17.4 18.4 16 14.4 12l4-4L17 6.6 13 10.6 9.4 7 7 8.4zM14 16h4v2h-4v-2z',
  file: 'M6 2h8l4 4v14H6V2zm7 1.5V7h3.5L13 3.5zM8 11h8v1H8v-1zm0 3h8v1H8v-1zm0 3h5v1H8v-1z',

  // ── 通用 ──
  settings: 'M12 2l2 4 4 .5L20 9l-1 4 1 4-2 2.5-4 .5-2 4-2-4-4-.5L4 15l1-4-1-4 2-2.5 4-.5 2-4zm0 6a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  star: 'M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7l3-7z',
  sparkles: 'M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2zm7 12l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3zM5 14l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2z',
  filter: 'M3 4h18v2l-7 8v6l-4-2v-4L3 6V4z',

  // ── 业务 ──
  map: 'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3V6zm6 0v15m6-15v15',
  route: 'M5 4h14v3H5V4zm0 5h10v3H5V9zm0 5h14v3H5v-3zm0 5h7v3H5v-3z',
  warning: 'M12 2l11 19H1L12 2zm0 5v6h2V7h-2zm0 8v2h2v-2h-2z',
  info: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm-1 5h2v6h-2v-6z',

  // ── 控制面板 ──
  arrowUpCircle: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 5l-5 6h3v6h4v-6h3l-5-6z',
  arrowDownCircle: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-5 11l5 6 5-6h-3V6h-4v7H7z',
  arrowLeftCircle: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-9 9h10V8l6 5-6 5v-3H3v-4z',
  arrowRightCircle: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-2 5l6 5-6 5v-3H6v-4h4V7z',

  // ── 品牌 ──
  robot: 'M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm2 3v6h10V8H7zm5 1a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM4 10v3H2v-3h2zm18 0v3h-2v-3h2zM9 2v3h2V2H9zm4 0v3h2V2h-2z',
}
</script>

<template>
  <svg
    :class="['icon', size, { solid }]"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <path :d="icons[name]" />
  </svg>
</template>