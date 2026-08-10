import { defineStore } from 'pinia'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { resolveNavigation } from '@/router/navigation'

export const useNavigationStore = defineStore('navigation', {
  state: () => ({ entries: [], loaded: false, rejectedRouteKeys: [] }),
  getters: {
    hasRoute: (state) => (routeKey) => state.entries.some((entry) => entry.routeKey === routeKey)
  },
  actions: {
    async load() {
      if (this.loaded) return this.entries
      const { entries, rejected } = resolveNavigation(await getShotGridNavigation())
      this.entries = entries
      this.rejectedRouteKeys = rejected
      this.loaded = true
      return entries
    },
    clear() {
      this.$reset()
    }
  }
})
