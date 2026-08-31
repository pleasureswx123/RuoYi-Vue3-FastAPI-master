import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectSchedule } from '@/api/shot-grid/schedules'
import { useScheduleStore } from '@/store/modules/schedule'

vi.mock('@/api/shot-grid/schedules', () => ({
  getProjectSchedule: vi.fn()
}))

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('项目排期状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getProjectSchedule.mockReset()
  })

  it('切换项目时清空任务、错误、选中项和冲突快照', () => {
    const store = useScheduleStore()
    store.setProject(11)
    store.tasks = [{ taskId: 31 }]
    store.error = { message: '旧错误' }
    store.selectedTaskId = 31
    store.editingTaskId = 31
    store.conflictSnapshot = [99]

    store.setProject(12)

    expect(store.projectId).toBe(12)
    expect(store.tasks).toEqual([])
    expect(store.error).toBeNull()
    expect(store.selectedTaskId).toBeNull()
    expect(store.editingTaskId).toBeNull()
    expect(store.conflictSnapshot).toEqual([])
  })

  it('按可视窗口左右各扩展一个 viewport 并对相同有效请求去重', async () => {
    getProjectSchedule.mockResolvedValue({
      data: { rows: [{ taskId: 31 }], groups: [], total: 1, unscheduledCount: 2, serverTime: '2026-09-10T09:00:00' }
    })
    const store = useScheduleStore()
    store.setProject(11)

    await store.loadSchedule('2026-09-10T00:00:00', '2026-09-20T00:00:00')
    await store.loadSchedule('2026-09-10T00:00:00', '2026-09-20T00:00:00')

    expect(getProjectSchedule).toHaveBeenCalledTimes(1)
    expect(getProjectSchedule.mock.calls[0][1]).toMatchObject({
      windowStart: '2026-08-31T00:00:00',
      windowEnd: '2026-09-30T00:00:00',
      targetKind: 'all',
      groupBy: 'assignee',
      pageNum: 1,
      pageSize: 500
    })
    expect(store.tasks).toEqual([{ taskId: 31 }])
    expect(store.unscheduledCount).toBe(2)
  })

  it('切换筛选会取消旧请求，并丢弃同项目 ABA 迟到响应', async () => {
    const first = deferred()
    const second = deferred()
    getProjectSchedule.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const store = useScheduleStore()
    store.setProject(11)

    const oldRequest = store.loadSchedule('2026-09-01T00:00:00', '2026-09-08T00:00:00')
    const oldSignal = getProjectSchedule.mock.calls[0][2].signal
    store.setFilters({ priorities: ['urgent'] })
    const newRequest = store.loadSchedule('2026-09-01T00:00:00', '2026-09-08T00:00:00')

    expect(oldSignal.aborted).toBe(true)
    second.resolve({ data: { rows: [{ taskId: 2 }], groups: [], total: 1, unscheduledCount: 0 } })
    await newRequest
    first.resolve({ data: { rows: [{ taskId: 1 }], groups: [], total: 1, unscheduledCount: 0 } })
    await oldRequest

    expect(store.tasks).toEqual([{ taskId: 2 }])
    expect(store.loading).toBe(false)
  })

  it('项目切换会中止请求并阻止旧项目数据回填', async () => {
    const response = deferred()
    getProjectSchedule.mockReturnValue(response.promise)
    const store = useScheduleStore()
    store.setProject(11)
    const request = store.loadSchedule('2026-09-01T00:00:00', '2026-09-08T00:00:00')
    const signal = getProjectSchedule.mock.calls[0][2].signal

    store.setProject(12)
    response.resolve({ data: { rows: [{ taskId: 31 }], groups: [], total: 1, unscheduledCount: 0 } })
    await request

    expect(signal.aborted).toBe(true)
    expect(store.tasks).toEqual([])
  })
})
