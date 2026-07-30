import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import svgr from 'vite-plugin-svgr'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    svgr({ svgrOptions: { svgo: true, titleProp: true } }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@icons': path.resolve(__dirname, './public/icons'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
