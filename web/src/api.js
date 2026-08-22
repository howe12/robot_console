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
  systemLight: () => getJson('/api/system/light'),
  workspace: () => getJson('/api/workspace'),
  adapterConfig: (workspace = '') =>
    getJson(`/api/adapter/config${workspace ? '?workspace=' + encodeURIComponent(workspace) : ''}`),
  workspaceStatus: () => getJson('/api/workspace/status'),
  workspaceDiff: (workspace = '') =>
    getJson(`/api/workspace/diff${workspace ? '?workspace=' + encodeURIComponent(workspace) : ''}`),
  workspaceApply: (workspace, autoBackup = true) =>
    postJson('/api/workspace/apply?workspace=' + encodeURIComponent(workspace) + '&auto_backup=' + (autoBackup ? 'true' : 'false'), {}),
  workspaceReload: () => postJson('/api/workspace/reload', {}),
  graph: () => getJson('/api/graph'),
  topology: () => getJson('/api/topology'),
  systemStats: () => getJson('/api/system/stats'),
  gitInfo: () => getJson('/api/git/info'),
  imageTopics: () => getJson('/api/ros/image_topics'),
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

export const cameraStreamURL = (opts = {}) => {
  const p = new URLSearchParams()
  if (opts.topic) p.set('topic', opts.topic)
  if (opts.width) p.set('width', String(opts.width))
  if (opts.quality) p.set('quality', String(opts.quality))
  if (opts.fps) p.set('fps', String(opts.fps))
  const q = p.toString()
  return q ? `/api/camera/stream?${q}` : '/api/camera/stream'
}
