import { defineStore } from 'pinia'

const THEME_STORAGE_KEY = 'shot-grid.theme-mode'
const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)'

let mediaQueryList = null

function storedMode() {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function systemMode() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'light'
  return window.matchMedia(DARK_MEDIA_QUERY).matches ? 'dark' : 'light'
}

function applyMode(mode) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const isDark = mode === 'dark'
  root.classList.toggle('dark', isDark)
  root.dataset.theme = mode
  root.style.colorScheme = mode
  const themeColor = document.querySelector('meta[name="theme-color"]')
  if (themeColor) themeColor.content = isDark ? '#090b0f' : '#f4f6f8'
}

function persistMode(mode) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // 浏览器禁用本地存储时仍保持当前会话内的主题切换。
  }
}

export const useThemeStore = defineStore('theme', {
  state: () => {
    const preference = storedMode()
    return {
      mode: preference || systemMode(),
      source: preference ? 'user' : 'system',
      initialized: false
    }
  },
  getters: {
    isDark: state => state.mode === 'dark'
  },
  actions: {
    initialize() {
      const preference = storedMode()
      this.mode = preference || systemMode()
      this.source = preference ? 'user' : 'system'
      applyMode(this.mode)

      if (this.initialized || typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        this.initialized = true
        return
      }

      mediaQueryList = window.matchMedia(DARK_MEDIA_QUERY)
      const handleSystemChange = event => {
        if (storedMode()) return
        this.mode = event.matches ? 'dark' : 'light'
        this.source = 'system'
        applyMode(this.mode)
      }
      if (typeof mediaQueryList.addEventListener === 'function') {
        mediaQueryList.addEventListener('change', handleSystemChange)
      } else if (typeof mediaQueryList.addListener === 'function') {
        mediaQueryList.addListener(handleSystemChange)
      }
      this.initialized = true
    },
    setDark(enabled) {
      this.mode = enabled ? 'dark' : 'light'
      this.source = 'user'
      persistMode(this.mode)
      applyMode(this.mode)
    }
  }
})
