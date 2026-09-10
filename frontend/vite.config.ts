import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Адрес API задаётся переменной VITE_API_URL (см. .env.example).
// В разработке удобно оставить её пустой и ходить через прокси: тогда
// запросы идут на тот же источник и CORS не мешает.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
