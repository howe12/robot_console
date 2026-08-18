import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物输出到 ../static（FastAPI 静态目录）
export default defineConfig({
  plugins: [vue()],
  base: '/static/',
  build: {
    outDir: '../static',
    emptyOutDir: false, // 保留 FastAPI 由 src 引用的 index.html 在内的既有文件策略
    assetsDir: 'assets',
    rollupOptions: {
      input: 'index.html'
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/ws': { target: 'ws://127.0.0.1:8080', ws: true }
    }
  }
})
