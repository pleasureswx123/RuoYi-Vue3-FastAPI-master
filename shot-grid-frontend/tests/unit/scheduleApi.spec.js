import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  getProjectSchedule,
  getTaskScheduleChanges,
  getUnscheduledScheduleTasks,
  updateTaskSchedule
} from '@/api/shot-grid/schedules'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('任务排期 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('项目排期和未排期池保留窗口筛选与取消信号', () => {
    const signal = new AbortController().signal
    const params = {
      windowStart: '2026-09-01T00:00:00',
      windowEnd: '2026-10-01T00:00:00',
      targetKind: 'all',
      groupBy: 'assignee',
      pageNum: 1,
      pageSize: 200
    }

    getProjectSchedule(11, params, { signal })
    getUnscheduledScheduleTasks(11, params, { signal })

    expect(request.mock.calls).toEqual([
      [{ url: '/shot-grid/projects/11/schedule', method: 'get', params, signal, silentError: true }],
      [
        {
          url: '/shot-grid/projects/11/schedule/unscheduled',
          method: 'get',
          params,
          signal,
          silentError: true
        }
      ]
    ])
  })

  it('历史查询与排期写入固定真实路径、幂等头和重复提交策略', () => {
    const data = {
      lockVersion: 3,
      expectedStartTime: '2026-09-03T09:00:00',
      expectedEndTime: '2026-09-05T18:00:00',
      operationSource: 'gantt',
      changeReason: '调整制作窗口',
      overlapAcknowledged: false,
      expectedConflictTaskIds: []
    }

    getTaskScheduleChanges(31, { pageNum: 1, pageSize: 20 })
    updateTaskSchedule(31, data, 'schedule-31-command-1')

    expect(request.mock.calls).toEqual([
      [
        {
          url: '/shot-grid/tasks/31/schedule-changes',
          method: 'get',
          params: { pageNum: 1, pageSize: 20 },
          signal: undefined,
          silentError: true
        }
      ],
      [
        {
          url: '/shot-grid/tasks/31/schedule',
          method: 'put',
          data,
          headers: { 'X-Idempotency-Key': 'schedule-31-command-1' },
          repeatSubmit: false,
          silentError: true
        }
      ]
    ])
  })

  it('拒绝非法 ID 和空幂等键', () => {
    expect(() => getProjectSchedule('../11', {})).toThrow('项目 ID 必须为正整数')
    expect(() => getTaskScheduleChanges(0, {})).toThrow('任务 ID 必须为正整数')
    expect(() => updateTaskSchedule(31, {}, '   ')).toThrow('幂等键不能为空')
  })
})
