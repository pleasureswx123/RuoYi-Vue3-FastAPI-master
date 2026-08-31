import { defineStore } from 'pinia'

import { getProjectSchedule } from '@/api/shot-grid/schedules'
import { assertPositiveId } from '@/api/shot-grid/projects'

const DEFAULT_FILTERS = Object.freeze({
  assigneeUserIds: [],
  taskKinds: [],
  taskStatuses: [],
  priorities: [],
  keyword: '',
  episodeIds: [],
  sceneIds: [],
  assetTypes: [],
  onlyConflicts: false,
  onlyDelayed: false
})

function freshFilters() {
  return Object.fromEntries(
    Object.entries(DEFAULT_FILTERS).map(([key, value]) => [key, Array.isArray(value) ? [] : value])
  )
}

function parseBusinessTime(value, fieldName) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    throw new Error(`${fieldName}不是有效时间`)
  }
  return date
}

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatBusinessTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function bufferedScheduleWindow(windowStart, windowEnd) {
  const start = parseBusinessTime(windowStart, '窗口开始时间')
  const end = parseBusinessTime(windowEnd, '窗口结束时间')
  const duration = end.getTime() - start.getTime()
  if (duration <= 0) {
    throw new Error('窗口结束时间必须晚于开始时间')
  }
  return {
    windowStart: formatBusinessTime(new Date(start.getTime() - duration)),
    windowEnd: formatBusinessTime(new Date(end.getTime() + duration))
  }
}

function safeError(error) {
  return {
    httpStatus: error?.httpStatus ?? error?.status ?? null,
    code: error?.code ?? null,
    errorKey: error?.errorKey || '',
    message: error?.message || '排期加载失败',
    details: error?.details && typeof error.details === 'object' ? error.details : null
  }
}

function isAbortError(error) {
  return error?.name === 'AbortError' || error?.code === 'ERR_CANCELED'
}

export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    projectId: null,
    mode: 'swimlane',
    scale: 'week',
    groupBy: 'assignee',
    targetKind: 'all',
    filters: freshFilters(),
    pageNum: 1,
    pageSize: 500,
    tasks: [],
    groups: [],
    total: 0,
    unscheduledCount: 0,
    serverTime: null,
    visibleWindow: null,
    loadedWindow: null,
    loading: false,
    error: null,
    selectedTaskId: null,
    editingTaskId: null,
    editMode: false,
    conflictSnapshot: [],
    generation: 0,
    requestController: null,
    pendingRequestKey: '',
    pendingPromise: null,
    loadedRequestKey: ''
  }),
  actions: {
    setProject(projectId) {
      const normalized = assertPositiveId(projectId, '项目')
      if (this.projectId === normalized) return
      this.cancelRequest()
      this.projectId = normalized
      this.resetResults()
    },
    setFilters(patch) {
      this.filters = { ...this.filters, ...patch }
      this.pageNum = 1
      this.invalidateQuery()
    },
    setGrouping(groupBy) {
      if (this.groupBy === groupBy) return
      this.groupBy = groupBy
      this.invalidateQuery()
    },
    setTargetKind(targetKind) {
      if (this.targetKind === targetKind) return
      this.targetKind = targetKind
      this.invalidateQuery()
    },
    setMode(mode) {
      this.mode = mode
      this.editingTaskId = null
      this.conflictSnapshot = []
    },
    setEditMode(enabled) {
      this.editMode = Boolean(enabled)
      if (!this.editMode) {
        this.editingTaskId = null
        this.conflictSnapshot = []
      }
    },
    setScale(scale) {
      this.scale = scale
    },
    invalidateQuery() {
      this.cancelRequest()
      this.loadedRequestKey = ''
      this.loadedWindow = null
    },
    resetResults() {
      this.tasks = []
      this.groups = []
      this.total = 0
      this.unscheduledCount = 0
      this.serverTime = null
      this.visibleWindow = null
      this.loadedWindow = null
      this.error = null
      this.selectedTaskId = null
      this.editingTaskId = null
      this.editMode = false
      this.conflictSnapshot = []
      this.loadedRequestKey = ''
    },
    cancelRequest() {
      this.requestController?.abort()
      this.requestController = null
      this.pendingRequestKey = ''
      this.pendingPromise = null
      this.generation += 1
      this.loading = false
    },
    loadSchedule(windowStart, windowEnd) {
      if (!this.projectId) {
        return Promise.reject(new Error('请先选择项目'))
      }
      const effectiveWindow = bufferedScheduleWindow(windowStart, windowEnd)
      const params = {
        ...effectiveWindow,
        targetKind: this.targetKind,
        groupBy: this.groupBy,
        ...this.filters,
        pageNum: this.pageNum,
        pageSize: this.pageSize
      }
      const requestKey = JSON.stringify([this.projectId, params])
      this.visibleWindow = { windowStart, windowEnd }
      if (requestKey === this.loadedRequestKey) {
        return Promise.resolve(this.tasks)
      }
      if (requestKey === this.pendingRequestKey && this.pendingPromise) {
        return this.pendingPromise
      }

      this.cancelRequest()
      const generation = this.generation
      const projectId = this.projectId
      const controller = new AbortController()
      this.requestController = controller
      this.pendingRequestKey = requestKey
      this.loading = true
      this.error = null
      const requestPromise = (async () => {
        const allRows = []
        const groupsByKey = new Map()
        let result = {}
        let pageNum = 1
        do {
          const response = await getProjectSchedule(
            projectId,
            { ...params, pageNum },
            { signal: controller.signal }
          )
          result = response?.data ?? response ?? {}
          if (generation !== this.generation || projectId !== this.projectId) return this.tasks
          if (Array.isArray(result.rows)) allRows.push(...result.rows)
          for (const group of Array.isArray(result.groups) ? result.groups : []) {
            const existing = groupsByKey.get(group.groupKey)
            groupsByKey.set(group.groupKey, existing
              ? { ...existing, taskCount: Number(existing.taskCount || 0) + Number(group.taskCount || 0) }
              : { ...group })
          }
          pageNum += 1
        } while (result.hasNext === true)
        return {
          result,
          allRows,
          groups: [...groupsByKey.values()].sort((left, right) => left.sortOrder - right.sortOrder)
        }
      })()
        .then(payload => {
          if (Array.isArray(payload)) return payload
          if (generation !== this.generation || projectId !== this.projectId) return this.tasks
          const { result, allRows, groups } = payload
          this.tasks = allRows
          this.groups = groups
          this.total = Number(result.total || 0)
          this.unscheduledCount = Number(result.unscheduledCount || 0)
          this.serverTime = result.serverTime || null
          this.loadedWindow = effectiveWindow
          this.loadedRequestKey = requestKey
          return this.tasks
        })
        .catch(error => {
          if (generation !== this.generation || projectId !== this.projectId || isAbortError(error)) {
            return this.tasks
          }
          this.error = safeError(error)
          throw error
        })
        .finally(() => {
          if (generation !== this.generation || projectId !== this.projectId) return
          this.loading = false
          this.requestController = null
          this.pendingRequestKey = ''
          this.pendingPromise = null
        })
      this.pendingPromise = requestPromise
      return requestPromise
    },
    dispose() {
      this.cancelRequest()
      this.resetResults()
      this.filters = freshFilters()
      this.projectId = null
    }
  }
})
