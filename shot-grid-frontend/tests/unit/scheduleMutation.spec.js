import { flushPromises, mount } from '@vue/test-utils'
import { ElButton, ElDatePicker, ElForm, ElFormItem, ElInput } from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'
import { useScheduleMutation } from '@/views/schedule/useScheduleMutation'

vi.mock('@/api/shot-grid/productionHistory', () => ({ getProductionHistory: vi.fn().mockResolvedValue({ data: { lanes: [], events: [] } }) }))

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
  it('使用 ElForm 显式校验，原因选填仍可提交，保存中禁用操作', async () => {
    const wrapper = mount(ScheduleEditDialog, {
      props: {
        visible: true,
        task,
        draft: {
          expectedStartTime: '2026-09-02T09:00:00',
          expectedEndTime: '2026-09-06T18:00:00',
          operationSource: 'gantt'
        },
        saving: false
      },
      global: {
        components: { ElButton, ElDatePicker, ElForm, ElFormItem, ElInput },
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
    expect(form.props('model')).toMatchObject({ changeReason: '' })
    expect(form.props('rules')).toMatchObject({ expectedRange: expect.any(Array), changeReason: expect.any(Array) })

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('save-request').at(-1)[0].changeReason).toBe('')

    expect(wrapper.text()).toContain('原排期')
    expect(wrapper.text()).toContain('拟调整为')
    await wrapper.findAllComponents(ElInput).find(input => input.props('type') === 'textarea').setValue('   ')
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(wrapper.emitted('save-request').at(-1)[0].changeReason).toBe('')

    await wrapper.findAllComponents(ElInput).find(input => input.props('type') === 'textarea').setValue('调整动画制作窗口')
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('save-request').at(-1)[0]).toEqual({
      expectedStartTime: '2026-09-02T09:00:00',
      expectedEndTime: '2026-09-06T18:00:00',
      operationSource: 'gantt',
      changeReason: '调整动画制作窗口'
    })

    await wrapper.setProps({ draft: { expectedStartTime: task.currentStart, expectedEndTime: task.currentEnd } })
    expect(wrapper.findAllComponents(ElButton).find(button => button.text() === '保存排期').props('disabled')).toBe(true)
    expect(wrapper.text()).toContain('排期未变更')

    await wrapper.setProps({ saving: true })
    expect(
      wrapper.findAllComponents(ElButton)
        .filter(button => ['取消', '保存排期'].includes(button.text()))
        .every(button => button.props('disabled'))
    ).toBe(true)
  })
})

describe('排期写入', () => {
  it('重叠任务一次保存，不发送隐式确认，使用服务端结果更新 Store', async () => {
    updateTaskSchedule.mockReset()
    const store = { tasks: [{ ...task }], setEditMode: vi.fn() }
    const mutation = useScheduleMutation(store)
    mutation.open(task)
    const saved = { ...task, lockVersion: 9, conflicts: [{ taskId: 32 }] }
    updateTaskSchedule.mockResolvedValueOnce({ data: saved })
    await mutation.save({ changeReason: '调整窗口' })
    expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
    expect(updateTaskSchedule.mock.calls[0][1]).not.toHaveProperty('overlapAcknowledged')
    expect(updateTaskSchedule.mock.calls[0][1]).not.toHaveProperty('expectedConflictTaskIds')
    expect(store.tasks[0]).toEqual(saved)
    expect(mutation.visible.value).toBe(false)
  })

  it('版本冲突刷新后仍需重新保存，只读错误退出编辑模式', async () => {
    updateTaskSchedule.mockReset()
    const store = { tasks: [{ ...task }], setEditMode: vi.fn() }
    const onRefresh = vi.fn()
    const mutation = useScheduleMutation(store, { onRefresh })
    mutation.open(task)
    updateTaskSchedule.mockRejectedValueOnce({ httpStatus: 409, errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT' })
    await mutation.save({ changeReason: '再次调整' })
    expect(onRefresh).toHaveBeenCalledOnce()
    expect(mutation.visible.value).toBe(true)
    expect(store.tasks[0].lockVersion).toBe(8)
    updateTaskSchedule.mockRejectedValueOnce({ httpStatus: 409, errorKey: 'SG_TASK_SCHEDULE_READ_ONLY' })
    await mutation.save({ changeReason: '再次调整' })
    expect(store.setEditMode).toHaveBeenCalledWith(false)
    expect(mutation.visible.value).toBe(false)
  })
})
