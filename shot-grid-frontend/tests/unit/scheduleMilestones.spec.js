import { describe, expect, it } from 'vitest'
import { taskMilestones, scheduleDateWarnings } from '@/views/schedule/scheduleMilestones'
describe('排期实际节点', () => {
  it('只聚合当前任务的提交和审核，不借用其他分项或计划日期', () => {
    const result = taskMilestones({ lanes: [{ laneId: 2, task: { taskId: 31, createTime: '2026-09-01' } }], events: [
      { laneIds: [3], versionCycle: { submittedTime: '2026-08-01' } },
      { laneIds: [2], versionCycle: { submittedTime: '2026-09-03', reviewActions: [{ actionType: 'approve', createTime: '2026-09-04' }] } }
    ] }, 31)
    expect(result.firstSubmitted).toBe('2026-09-03')
    expect(result.approved).toBe('2026-09-04')
    expect(result).not.toHaveProperty('started')
  })
  it('历史日期仅提示，未完成到期、创建和提交边界分别判断', () => {
    const task = { taskStatus: 'not_started' }
    expect(scheduleDateWarnings(task, ['2026-09-02', '2026-09-03'], { created: '2026-09-04', firstSubmitted: '2026-09-01' }, new Date('2026-09-05').getTime())).toHaveLength(4)
    expect(scheduleDateWarnings(task, ['2026-09-03', '2026-09-02'], null)).toEqual([])
  })
})
