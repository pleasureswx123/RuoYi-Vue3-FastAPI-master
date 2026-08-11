import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  getMineTaskPage,
  getProjectTaskPage,
  getTaskDetail,
  startTask,
  updateTask
} from '@/api/shot-grid/tasks'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('任务 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('我的任务与项目任务保留 camelCase 分页筛选和取消信号', () => {
    const signal = new AbortController().signal
    const params = {
      keyword: '动力舱',
      taskKind: 'asset_image',
      taskStatus: 'revision',
      dueDateFrom: '2026-08-01',
      dueDateTo: '2026-08-31',
      priority: 'urgent',
      pageNum: 2,
      pageSize: 20,
      orderByColumn: 'dueDate',
      isAsc: 'ascending'
    }

    getMineTaskPage(params, { signal })
    getProjectTaskPage(8, { ...params, scope: 'project', assigneeUserId: 7 }, { signal })

    expect(request.mock.calls[0][0]).toEqual({
      url: '/shot-grid/tasks/mine',
      method: 'get',
      params,
      signal,
      silentError: true
    })
    expect(request.mock.calls[1][0]).toMatchObject({
      url: '/shot-grid/projects/8/tasks',
      method: 'get',
      params: expect.objectContaining({ scope: 'project', assigneeUserId: 7 }),
      signal
    })
  })

  it('详情、更新与开始任务使用后端真实路径和锁版本', () => {
    const signal = new AbortController().signal
    const update = { requirements: '冷蓝色调', priority: 'high', dueDate: null, lockVersion: 3 }
    getTaskDetail(31, { signal })
    updateTask(31, update)
    startTask(31, { lockVersion: 4 })

    expect(request.mock.calls).toEqual([
      [{ url: '/shot-grid/tasks/31', method: 'get', signal, silentError: true }],
      [{ url: '/shot-grid/tasks/31', method: 'put', data: update, silentError: true }],
      [{ url: '/shot-grid/tasks/31/start', method: 'post', data: { lockVersion: 4 }, silentError: true }]
    ])
  })

  it('拒绝非正整数路由 ID，不将不可信字符串拼入 URL', () => {
    expect(() => getProjectTaskPage('../8', {})).toThrow('项目 ID 必须为正整数')
    expect(() => getTaskDetail('31/../../users')).toThrow('任务 ID 必须为正整数')
    expect(() => startTask(0, { lockVersion: 0 })).toThrow('任务 ID 必须为正整数')
  })
})
