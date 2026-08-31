import { describe, expect, it } from 'vitest'

import {
  baselineOverlayStyle,
  ganttScaleFor,
  rangeChangeRequest,
  toGanttTasks,
  toSwimlaneRows
} from '@/views/schedule/adapters/svarGanttAdapter'

describe('甘特自然时间刻度适配', () => {
  it('将日周月缩放映射为连续自然时间刻度', () => {
    expect(ganttScaleFor('day')).toEqual({
      cellWidth: 72,
      lengthUnit: 'day',
      scales: [
        { unit: 'month', step: 1, format: expect.any(Function) },
        { unit: 'day', step: 1, format: expect.any(Function) }
      ]
    })
    expect(ganttScaleFor('week')).toEqual({
      cellWidth: 112,
      lengthUnit: 'week',
      scales: [
        { unit: 'month', step: 1, format: expect.any(Function) },
        { unit: 'week', step: 1, format: expect.any(Function) }
      ]
    })
    expect(ganttScaleFor('month')).toEqual({
      cellWidth: 128,
      lengthUnit: 'month',
      scales: [
        { unit: 'year', step: 1, format: expect.any(Function) },
        { unit: 'month', step: 1, format: expect.any(Function) }
      ]
    })

    expect(ganttScaleFor('day').scales[1].format(new Date(2026, 8, 3))).toBe('3日')
    expect(ganttScaleFor('week').scales[1].format(new Date(2026, 8, 3))).toBe('第36周')
    expect(ganttScaleFor('month').scales[0].format(new Date(2026, 8, 3))).toBe('2026年')
  })
})

describe('排期领域行到甘特任务适配', () => {
  it('保留当前排期、首次基线、负责人和冲突状态', () => {
    const [task] = toGanttTasks([
      {
        taskId: 31,
        taskName: 'S010 动画',
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        priority: 'high',
        lockVersion: 8,
        target: { targetKind: 'shot', targetId: 101, name: 'EP01-S010' },
        assignee: { userId: 7, userName: '杨景锋' },
        currentStart: '2026-09-01T09:00:00',
        currentEnd: '2026-09-05T18:00:00',
        baselineStart: '2026-08-31T09:00:00',
        baselineEnd: '2026-09-04T18:00:00',
        conflicts: [{ taskId: 32, targetName: 'EP01-S020', startTime: '2026-09-03T09:00:00', endTime: '2026-09-06T18:00:00' }],
        allowedActions: ['task.schedule']
      }
    ], { editable: true })

    expect(task).toEqual({
      id: 'task:31',
      taskId: 31,
      text: 'S010 动画',
      start: new Date('2026-09-01T09:00:00'),
      end: new Date('2026-09-05T18:00:00'),
      assigneeUserId: 7,
      assigneeName: '杨景锋',
      targetName: 'EP01-S010',
      taskKind: 'shot_video',
      taskStatus: 'in_progress',
      priority: 'high',
      lockVersion: 8,
      baseline: {
        start: new Date('2026-08-31T09:00:00'),
        end: new Date('2026-09-04T18:00:00')
      },
      conflictTaskIds: [32],
      className: 'is-conflicted',
      readonly: false
    })
  })
})

describe('甘特范围修改请求', () => {
  const task = {
    taskId: 31,
    lockVersion: 8,
    assigneeUserId: 7,
    readonly: false
  }

  it('把水平移动结果转换为秒精度业务本地时间请求', () => {
    expect(rangeChangeRequest({
      task,
      nextStart: new Date(2026, 8, 2, 9, 0, 0),
      nextEnd: new Date(2026, 8, 6, 18, 0, 0),
      nextAssigneeUserId: 7,
      operationSource: 'gantt'
    })).toEqual({
      accepted: true,
      payload: {
        taskId: 31,
        lockVersion: 8,
        expectedStartTime: '2026-09-02T09:00:00',
        expectedEndTime: '2026-09-06T18:00:00',
        operationSource: 'gantt'
      }
    })
  })

  it('只读任务不产生排期写请求', () => {
    expect(rangeChangeRequest({
      task: { ...task, readonly: true },
      nextStart: new Date(2026, 8, 2, 9, 0, 0),
      nextEnd: new Date(2026, 8, 6, 18, 0, 0),
      nextAssigneeUserId: 7,
      operationSource: 'gantt'
    })).toEqual({ accepted: false, reason: 'readonly' })
  })

  it('跨泳道移动不改变负责人并拒绝排期请求', () => {
    expect(rangeChangeRequest({
      task,
      nextStart: new Date(2026, 8, 2, 9, 0, 0),
      nextEnd: new Date(2026, 8, 6, 18, 0, 0),
      nextAssigneeUserId: 9,
      operationSource: 'swimlane'
    })).toEqual({ accepted: false, reason: 'assignee-change' })
    expect(task.assigneeUserId).toBe(7)
  })
})

describe('人员泳道重叠堆叠', () => {
  it('同负责人重叠任务分层且首尾相接可复用同层', () => {
    const rows = toSwimlaneRows([
      { id: 'task:1', taskId: 1, assigneeUserId: 7, assigneeName: '杨景锋', start: new Date('2026-09-01T09:00:00'), end: new Date('2026-09-05T18:00:00') },
      { id: 'task:2', taskId: 2, assigneeUserId: 7, assigneeName: '杨景锋', start: new Date('2026-09-03T09:00:00'), end: new Date('2026-09-06T09:00:00') },
      { id: 'task:3', taskId: 3, assigneeUserId: 7, assigneeName: '杨景锋', start: new Date('2026-09-06T09:00:00'), end: new Date('2026-09-07T09:00:00') },
      { id: 'task:4', taskId: 4, assigneeUserId: 9, assigneeName: '李梅', start: new Date('2026-09-03T09:00:00'), end: new Date('2026-09-04T09:00:00') }
    ])

    expect(rows.map(row => ({ id: row.id, trackCount: row.trackCount, taskTracks: row.tasks.map(task => [task.taskId, task.track]) }))).toEqual([
      { id: 'assignee:7', trackCount: 2, taskTracks: [[1, 0], [2, 1], [3, 0]] },
      { id: 'assignee:9', trackCount: 1, taskTracks: [[4, 0]] }
    ])
  })
})

describe('自有基线影子', () => {
  it('相对当前任务条计算基线位置而不调用商业版字段', () => {
    expect(baselineOverlayStyle({
      start: new Date('2026-09-02T00:00:00'),
      end: new Date('2026-09-06T00:00:00'),
      baseline: {
        start: new Date('2026-09-01T00:00:00'),
        end: new Date('2026-09-04T00:00:00')
      }
    })).toEqual({ left: '-25%', width: '75%' })
  })
})
