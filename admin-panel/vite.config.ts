import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/admin-panel/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5000',
      '/admin/analytics': 'http://localhost:5000',
      '/admin/chat-history': 'http://localhost:5000',
      '/files': 'http://localhost:5000',
      '/sessions': 'http://localhost:5000',
      '/load': 'http://localhost:5000',
    },
    // Note: /api/admin/dynamic-sources and /api/admin/files/* are already
    // covered by the '/api' proxy entry above.
  },
})
