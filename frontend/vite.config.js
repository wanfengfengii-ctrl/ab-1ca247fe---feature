import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发环境把 API 与健康检查代理到本机后端；容器内由 nginx 反代。
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
