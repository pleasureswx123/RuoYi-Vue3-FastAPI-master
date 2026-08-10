import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPrefix = env.VITE_APP_BASE_API || '/dev-api'

  return {
    base: env.VITE_APP_BASE_PATH || '/shot-grid/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '~': path.resolve(import.meta.dirname, '.')
      }
    },
    server: {
      host: true,
      port: 5174,
      proxy: {
        [apiPrefix]: {
          target: env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:9099',
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(new RegExp(`^${apiPrefix}`), '')
        }
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: false
    }
  }
})
