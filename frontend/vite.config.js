import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import monacoEditorPlugin from 'vite-plugin-monaco-editor'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    monacoEditorPlugin.default({
          languageWorkers: ['editorWorkerService', 'typescript', 'css', 'html', 'json'],
    }),
  ],
  optimizeDeps: {
      include: ['monaco-editor', 'monaco-emmet'],
    },
  worker: {
      format: 'es',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: "http://localhost:8000",
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      }
    }
  }
})
