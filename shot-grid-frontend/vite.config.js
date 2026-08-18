import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  return {
    base: env.VITE_APP_BASE_PATH || '/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      host: true,
      port: 5174,
      open: false,
      proxy: {
        [env.VITE_APP_BASE_API || '/dev-api']: {
          target: env.VITE_APP_PROXY_TARGET || 'http://127.0.0.1:9099',
          changeOrigin: true,
          rewrite: requestPath => requestPath.replace(new RegExp(`^${env.VITE_APP_BASE_API || '/dev-api'}`), '')
        }
      }
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: false,
      rollupOptions: {
        output: {
          chunkFileNames: 'static/js/[name]-[hash].js',
          entryFileNames: 'static/js/[name]-[hash].js',
          assetFileNames: 'static/[ext]/[name]-[hash].[ext]'
        }
      }
    },
    test: {
      environment: 'jsdom',
      server: {
        deps: {
          inline: ['element-plus']
        }
      },
      include: ['tests/**/*.spec.js'],
      setupFiles: ['./tests/setup.js'],
      clearMocks: true,
      restoreMocks: true,
      coverage: {
        reportsDirectory: path.resolve(process.cwd(), 'coverage')
      }
    }
  }
})
