import { describe, expect, it } from 'vitest'

import {
  baselineVariance,
  scheduleErrorState,
  scheduleReminder,
  scheduleTaskLabel
} from '@/views/schedule/schedulePresentation'

describe('排期展示派生', () => {
  it('按后端原始时间派生基线偏差，不构造进度百分比', () => {
    const variance = baselineVariance({
      currentStart: '2026-09-03T09:00:00',
      currentEnd: '2026-09-07T18:00:00',
      baselineStart: '2026-09-01T09:00:00',
      baselineEnd: '2026-09-05T18:00:00'
    })

    expect(variance).toEqual({ startDays: 2, endDays: 2, delayed: true })
    expect(variance.progress).toBeUndefined()
  })

  it('以 serverTime 判断正常、临期、逾期，完成状态不再预警', () => {
    const task = { taskStatus: 'in_progress', currentEnd: '2026-09-03T18:00:00' }
    expect(scheduleReminder(task, '2026-09-01T18:00:00').state).toBe('normal')
    expect(scheduleReminder(task, '2026-09-03T00:00:00').state).toBe('warning')
    expect(scheduleReminder(task, '2026-09-03T18:00:00').state).toBe('overdue')
    expect(scheduleReminder({ ...task, taskStatus: 'completed' }, '2026-09-04T00:00:00').state).toBe('completed')
  })

  it('任务标签优先业务编码和名称，错误提示给出可行动下一步', () => {
    expect(scheduleTaskLabel({ target: { code: 'EP001-001-0010', name: '镜头 10' } })).toBe('EP001-001-0010 · 镜头 10')
    expect(scheduleTaskLabel({ target: { name: '角色 A - 三视图' } })).toBe('角色 A - 三视图')
    expect(scheduleErrorState({ errorKey: 'SG_TASK_SCHEDULE_OVERLAP', details: { conflictTaskIds: [9] } })).toMatchObject({
      title: '人员排期发生重叠',
      action: '查看冲突后再次确认'
    })
    expect(scheduleErrorState({ errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT' })).toMatchObject({ action: '刷新任务后重试' })
    expect(scheduleErrorState({ httpStatus: 403 })).toMatchObject({ retryable: false })
  })
})
