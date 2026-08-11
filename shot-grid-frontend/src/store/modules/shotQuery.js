import { defineStore } from 'pinia'
import { listShots } from '@/api/shot-grid/shots'

export const defaultShotQuery = () => ({ projectId: '', episodeId: '', sceneId: '', assigneeUserId: '', status: '', keyword: '', orderBy: 'sortOrder', orderDirection: 'asc', pageNum: 1, pageSize: 20 })

export const useShotQueryStore = defineStore('shotQuery', {
  state: () => ({ query: defaultShotQuery(), rows: [], total: 0, loading: false, error: '', forbidden: false, requestId: 0, controller: null }),
  getters: { result: (state) => ({ rows: state.rows, total: state.total }) },
  actions: {
    setProject(projectId) {
      if (String(projectId || '') === String(this.query.projectId || '')) return
      this.cancel(); this.$reset(); this.query.projectId = String(projectId || '')
    },
    patchQuery(patch) { Object.assign(this.query, patch, { pageNum: Object.hasOwn(patch, 'pageNum') ? patch.pageNum : 1 }) },
    cancel() { this.controller?.abort(); this.controller = null },
    async fetch() {
      if (!this.query.projectId) return
      this.cancel(); const id = ++this.requestId; this.controller = new AbortController(); this.loading = true; this.error = ''; this.forbidden = false
      const { projectId, ...params } = this.query
      try {
        const result = await listShots(projectId, params, { signal: this.controller.signal })
        if (id !== this.requestId) return
        this.rows = result?.rows || []; this.total = Number(result?.total || 0)
      } catch (error) {
        if (error?.code === 'ERR_CANCELED' || id !== this.requestId) return
        this.forbidden = Number(error?.response?.status || error?.code) === 403
        this.error = this.forbidden ? '您没有查看该项目镜头的权限。' : '镜头加载失败，请重试。'
      } finally { if (id === this.requestId) this.loading = false }
    },
    clear() { this.cancel(); this.$reset() }
  }
})
