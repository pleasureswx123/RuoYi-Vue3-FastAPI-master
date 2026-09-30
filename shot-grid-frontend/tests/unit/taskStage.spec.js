import { describe, expect, it } from 'vitest'
import { taskStage } from '@/views/task/taskStage'
import { taskStatusMeta } from '@/views/task/taskPresentation'
import { shotStatusMeta } from '@/views/shot/shotPresentation'
import { currentProductionHandoff, productionHistoryStage, productionHistoryActiveStep } from '@/components/production-history/productionHistoryPresentation'

describe('待排期与待开工统一派生阶段', () => {
  const dates = { expectedStartTime: '2026-09-30T09:00:00', expectedEndTime: '2026-10-07T18:00:00' }
  it.each([{}, { expectedStartTime: dates.expectedStartTime }, { expectedEndTime: dates.expectedEndTime }])('任一时间缺失均待排期，且不改写原任务', range => {
    const task = { taskStatus: 'not_started', ...range }
    expect(taskStage(task)).toBe('pending_schedule')
    expect(taskStatusMeta(task).label).toBe('待排期')
    expect(shotStatusMeta({ status: 'not_started', task }).label).toBe('待排期')
    expect(task.taskStatus).toBe('not_started')
  })
  it('完整排期显示待开工，覆盖镜头、任务和甘特数据', () => {
    expect(taskStage({ taskStatus: 'not_started', ...dates })).toBe('not_started')
    expect(shotStatusMeta({ status: 'not_started', task: dates }).label).toBe('待开工')
    expect(taskStage({ taskStatus: 'not_started', start: dates.expectedStartTime, end: dates.expectedEndTime })).toBe('not_started')
    expect(taskStage({ taskStatus: 'in_progress' })).toBe('in_progress')
    expect(taskStage({ status: 'unassigned' })).toBe('unassigned')
  })
  it('制作履历阶段条及当前待办跟随排期变化', () => {
    const lane = { currentStage: 'assigned', task: { taskStatus: 'not_started' } }
    expect(productionHistoryStage(lane)).toBe('pending_schedule')
    expect(currentProductionHandoff(lane).stage).toBe('待排期')
    expect(productionHistoryActiveStep(productionHistoryStage(lane))).toBe(2)
    Object.assign(lane.task, dates)
    expect(productionHistoryStage(lane)).toBe('not_started')
    expect(currentProductionHandoff(lane).stage).toBe('待开工')
    expect(productionHistoryActiveStep(productionHistoryStage(lane))).toBe(3)
  })
})
