import { defineStore } from 'pinia'
import { getInfo, logout } from '@/api/shot-grid/auth'
import { getToken, removeToken } from '@/utils/auth'

export const useUserStore = defineStore('user', {
  state: () => ({ user: null, restored: false }),
  getters: { authenticated: (state) => Boolean(state.user) },
  actions: {
    async restore() {
      if (this.restored || !getToken()) return this.authenticated
      try {
        const response = await getInfo()
        this.user = response.user || response.data?.user || response.data
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
        this.$reset()
        this.restored = true
      }
    }
  }
})
