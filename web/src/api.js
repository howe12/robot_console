// 轻量 API 客户端
const BASE = ''

async function getJson(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`${path} -> ${r.status}`)
  return r.json()
}

async function postJson(path, body = {}) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!r.ok) throw new Error(`${path} -> ${r.status}`)
  return r.json()
}

export const api = {
  tasks: () => getJson('/api/tasks'),
  status: () => getJson('/api/status'),
  devices: () => getJson('/api/devices'),
  systemStatus: () => getJson('/api/system/status'),
  workspace: () => getJson('/api/workspace'),
  graph: () => getJson('/api/graph'),
  topology: () => getJson('/api/topology'),
  systemStats: () => getJson('/api/system/stats'),
  taskLogs: (id, tail = 300, node, level) => {
    const q = new URLSearchParams({ tail: String(tail) })
    if (node) q.set('node', node)
    if (level) q.set('level', level)
    return getJson(`/api/tasks/${id}/logs?${q}`)
  },
  logFilters: () => getJson('/api/logs/filters'),
  startTask: (id, params = {}) => postJson(`/api/tasks/${id}/start`, { params }),
  stopTask: (id) => postJson(`/api/tasks/${id}/stop`),
  stopAll: () => postJson('/api/stop-all'),
  startCustom: (packageName, launch, params = {}) =>
    postJson('/api/tasks/custom', { package: packageName, launch, params }),
  launchSource: (packageName, launch) =>
    getJson(`/api/launch/source?package=${encodeURIComponent(packageName)}&launch=${encodeURIComponent(launch)}`),
  cmdVel: (linear, angular) => postJson('/api/cmd_vel', { linear, angular })
}

export const cameraStreamURL = (topic = 'camera/color/image_raw') =>
  `/api/camera/stream`
