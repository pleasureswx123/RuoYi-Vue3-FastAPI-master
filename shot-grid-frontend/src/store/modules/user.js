import { defineStore } from 'pinia'
import { getInfo, login, logout } from '@/api/auth'
import { getToken, removeToken, setToken } from '@/utils/auth'
import { clearClientSession } from '@/utils/sessionCleanup'
import { useNavigationStore } from './navigation'

function normalizeIdentity(payload = {}) {
  return {
    user: payload.user || null,
    roles: Array.isArray(payload.roles) ? payload.roles : [],
    permissions: Array.isArray(payload.permissions) ? payload.permissions : []
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({ user: null, roles: [], permissions: [], restored: false }),
  getters: {
    authenticated: (state) => Boolean(state.user && getToken()),
    hasPermission: (state) => (permission) => state.permissions.includes('*:*:*') || state.permissions.includes(permission)
  },
  actions: {
    applyIdentity(payload) {
      Object.assign(this, normalizeIdentity(payload))
      this.restored = true
    },
    async signIn(credentials) {
      useNavigationStore().clear()
      const result = await login(credentials)
      const token = result?.token || result?.access_token
      if (!token) throw new Error('登录响应缺少 Token')
      setToken(token)
      try {
        this.applyIdentity(await getInfo())
      } catch (error) {
        removeToken()
        throw error
      }
      return this.user
    },
    async restore() {
      if (this.restored || !getToken()) return this.authenticated
      try {
        this.applyIdentity(await getInfo())
        return true
      } finally {
        this.restored = true
      }
    },
    async signOut() {
      try {
        if (getToken()) await logout()
      } finally {
        removeToken()
        clearClientSession()
        useNavigationStore().clear()
        this.$reset()
        this.restored = true
      }
    }
  }
})
