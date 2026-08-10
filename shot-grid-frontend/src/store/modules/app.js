import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({ pendingRequests: 0 }),
  getters: { loading: (state) => state.pendingRequests > 0 },
  actions: {
    beginRequest() {
      this.pendingRequests += 1
    },
    endRequest() {
      this.pendingRequests = Math.max(0, this.pendingRequests - 1)
    }
  }
})
