import { describe, expect, it } from 'vitest'

import {
  taskAssigneeLabel,
  taskDueState,
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta,
  taskVersionStatusMeta
} from '@/views/task/taskPresentation'

describe('任务展示契约', () => {
  it('集中映射稳定英文状态码，未知值不影响渲染', () => {
    expect(taskStatusMeta('revision')).toMatchObject({ label: '待修订', tone: 'danger' })
    expect(taskKindMeta('shot_video')).toMatchObject({ label: '镜头视频', shortLabel: '镜头' })
    expect(taskPriorityMeta('urgent')).toMatchObject({ label: '紧急', tone: 'danger' })
    expect(taskVersionStatusMeta('final')).toMatchObject({ label: '最终版本', tone: 'success' })
    expect(taskStatusMeta('future_state')).toEqual({ label: '未知', tone: 'neutral' })
  })

  it('截止日期与制作人摘要不依赖中文状态进行流转判断', () => {
    expect(taskDueState('2026-08-10', new Date('2026-08-11T12:00:00')).overdue).toBe(true)
    expect(taskDueState('2026-08-12', new Date('2026-08-11T12:00:00')).overdue).toBe(false)
    expect(taskAssigneeLabel({ userId: 7, nickName: '杨景锋', producerCode: 'YJF' })).toBe('杨景锋（YJF）')
  })

  it('区分 403、404、409 和 5xx，不把服务失败伪装为空数据', () => {
    expect(taskErrorState({ httpStatus: 403, message: '不是项目成员' })).toMatchObject({ title: '没有任务访问权限', retryable: false })
    expect(taskErrorState({ httpStatus: 404, message: '任务已删除' })).toMatchObject({ title: '任务不存在', retryable: false })
    expect(taskErrorState({ httpStatus: 409, errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT' })).toMatchObject({ title: '任务已发生变更', retryable: true })
    expect(taskErrorState({ httpStatus: 503, message: '维护中' })).toMatchObject({ title: '任务服务暂不可用', retryable: true })
  })
})
