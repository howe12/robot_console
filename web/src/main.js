import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

// 全局错误兜底：任何未捕获错误（render/Watcher/异步）都上报后端并打 console，
// 避免出现"页面静默变空"（Vue render 出错会把该组件渲染成 <!---->）后无从排查。
function reportClientError(err, info) {
  try {
    const detail = String((err && (err.message || err.stack)) || err) || info || 'unknown'
    console.error('[client-error]', detail, err)
    fetch('/api/client-error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: detail.slice(0, 2000),
        url: location.href,
        at: new Date().toISOString(),
        ua: navigator.userAgent
      })
    }).catch(() => {})
  } catch (e) { /* 上报本身失败则忽略 */ }
}

window.addEventListener('error', e => reportClientError(e.error || e.message))
window.addEventListener('unhandledrejection', e => reportClientError(e.reason))

const app = createApp(App)
app.config.errorHandler = (err, _instance, info) => reportClientError(err, info)
app.mount('#app')