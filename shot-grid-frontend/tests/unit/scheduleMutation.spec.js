import { flushPromises, mount } from '@vue/test-utils'
import { ElButton, ElCheckbox, ElDatePicker, ElForm, ElFormItem, ElInput } from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'
import { useScheduleMutation } from '@/views/schedule/useScheduleMutation'

vi.mock('@/api/shot-grid/schedules', () => ({ updateTaskSchedule: vi.fn() }))

const task = {
  taskId: 31,
  projectId: 11,
  taskKind: 'shot_video',
  taskStatus: 'in_progress',
  priority: 'high',
  lockVersion: 8,
  target: { targetKind: 'shot', targetId: 101, code: 'EP001-001-0010', name: 'EP001-001-0010' },
  assignee: { userId: 7, userName: '杨景锋' },
  currentStart: '2026-09-01T09:00:00',
  currentEnd: '2026-09-05T18:00:00',
  baselineStart: '2026-08-31T09:00:00',
  baselineEnd: '2026-09-04T18:00:00',
  conflicts: [],
  allowedActions: ['schedule']
}

describe('排期编辑表单', () => {
  it('使用 ElForm 显式校验，原因未填不提交，保存中禁用操作', async () => {
    const wrapper = mount(ScheduleEditDialog, {
      props: {
        visible: true,
        task,
        draft: {
          expectedStartTime: '2026-09-02T09:00:00',
          expectedEndTime: '2026-09-06T18:00:00',
          operationSource: 'gantt'
        },
        saving: false,
        conflictTaskIds: []
      },
      global: {
        components: { ElButton, ElCheckbox, ElDatePicker, ElForm, ElFormItem, ElInput },
        stubs: {
          ElDialog: {
            props: ['modelValue'],
            emits: ['update:modelValue', 'closed'],
            template: '<section><slot /><slot name="footer" /></section>'
          }
        }
      }
    })
    const form = wrapper.getComponent(ElForm)
    expect(form.props('model')).toMatchObject({ changeReason: '', overlapAcknowledged: false })
    expect(form.props('rules')).toMatchObject({ expectedRange: expect.any(Array), changeReason: expect.any(Array) })

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').trigger('click')
    expect(wrapper.emitted('save-request')).toBeUndefined()

    await wrapper.findAllComponents(ElInput).find(input => input.props('type') === 'textarea').setValue('调整动画制作窗口')
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('save-request')[0][0]).toEqual({
      expectedStartTime: '2026-09-02T09:00:00',
      expectedEndTime: '2026-09-06T18:00:00',
      operationSource: 'gantt',
      changeReason: '调整动画制作窗口',
      overlapAcknowledged: false
    })

    await wrapper.setProps({ saving: true })
    expect(
      wrapper.findAllComponents(ElButton)
        .filter(button => ['取消', '保存排期'].includes(button.text()))
        .every(button => button.props('disabled'))
    ).toBe(true)
  })
})

describe('排期写入与重叠二次确认', () => {
  it('首次冲突不修改 Store，确认同一冲突快照后用相同幂等键保存服务端结果', async () => {
    const store = { tasks: [{ ...task }], setEditMode: vi.fn() }
    const mutation = useScheduleMutation(store)
    mutation.open(task, {
      expectedStartTime: '2026-09-02T09:00:00',
      expectedEndTime: '2026-09-06T18:00:00',
      operationSource: 'gantt'
    })
    updateTaskSchedule.mockRejectedValueOnce({
      httpStatus: 409,
      errorKey: 'SG_TASK_SCHEDULE_OVERLAP',
      message: '存在重叠',
      details: {
        conflictTaskIds: [32, 35],
        conflicts: [{ taskId: 32, targetName: 'EP001-001-0020', assignee: { userName: '李梅' }, startTime: '2026-09-03T09:00:00', endTime: '2026-09-06T18:00:00' }]
      }
    })

    await mutation.save({ changeReason: '调整窗口', overlapAcknowledged: false })

    expect(store.tasks[0].currentStart).toBe(task.currentStart)
    expect(mutation.conflictTaskIds.value).toEqual([32, 35])
    expect(mutation.conflicts.value[0]).toMatchObject({ targetName: 'EP001-001-0020', assignee: { userName: '李梅' } })
    const idempotencyKey = updateTaskSchedule.mock.calls[0][2]

    const saved = { ...task, lockVersion: 9, currentStart: '2026-09-02T09:00:00', currentEnd: '2026-09-06T18:00:00' }
    updateTaskSchedule.mockResolvedValueOnce({ data: saved })
    await mutation.save({ changeReason: '调整窗口', overlapAcknowledged: true })

    expect(updateTaskSchedule.mock.calls[1][1]).toMatchObject({
      overlapAcknowledged: true,
      expectedConflictTaskIds: [32, 35]
    })
    expect(updateTaskSchedule.mock.calls[1][2]).toBe(idempotencyKey)
    expect(store.tasks[0]).toEqual(saved)
    expect(mutation.visible.value).toBe(false)
  })

  it('只读错误退出编辑模式，冲突集合变化要求重新确认', async () => {
    const store = { tasks: [{ ...task }], setEditMode: vi.fn() }
    const mutation = useScheduleMutation(store)
    mutation.open(task)
    mutation.conflictTaskIds.value = [32]
    updateTaskSchedule.mockRejectedValueOnce({
      httpStatus: 409,
      errorKey: 'SG_TASK_SCHEDULE_OVERLAP',
      details: { conflictTaskIds: [32, 36] }
    })
    await mutation.save({ changeReason: '再次调整', overlapAcknowledged: true })
    expect(mutation.conflictTaskIds.value).toEqual([32, 36])
    expect(mutation.overlapAcknowledged.value).toBe(false)

    updateTaskSchedule.mockRejectedValueOnce({ httpStatus: 409, errorKey: 'SG_TASK_SCHEDULE_READ_ONLY' })
    await mutation.save({ changeReason: '再次调整', overlapAcknowledged: false })
    expect(store.setEditMode).toHaveBeenCalledWith(false)
    expect(mutation.visible.value).toBe(false)
  })
})
