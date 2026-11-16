import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import ElementPlus, { ElButton, ElForm, ElTable, ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import ScheduleBatchDialog from '@/views/schedule/components/ScheduleBatchDialog.vue'
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'

vi.mock('@/api/shot-grid/schedules', () => ({ updateTaskSchedule: vi.fn() }))
const range = ['2030-09-01T09:00:00', '2030-09-05T18:00:00']
const tasks = [1, 2, 3].map(taskId => ({ taskId, projectId: 11, lockVersion: 4,
  taskStatus: 'in_progress', allowedActions: ['schedule'],
  target: { targetKind: taskId === 2 ? 'asset' : 'shot', name: `任务${taskId}`, code: `任务${taskId}` },
  assignee: { userName: '制作人' }, currentStart: null, currentEnd: null
}))
let wrapper
const button = text => wrapper.findAllComponents(ElButton).find(item => item.text() === text)
function open(rows = tasks, validateContext = () => true) {
  wrapper = mount(ScheduleBatchDialog, { props: { context: { tasks: rows, projectId: 11, validateContext } },
    global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: '<section><slot /><slot name="footer" /></section>' } } }
  })
}
async function select(indices) {
  await flushPromises()
  const table = wrapper.getComponent(ElTable)
  indices.forEach(index => table.vm.$.exposed.toggleRowSelection(table.props('data')[index], true, false))
  await flushPromises()
}
async function common() {
  wrapper.findAllComponents(ScheduleDateRangePicker)[0].vm.$emit('update:modelValue', range)
  await flushPromises()
  await button('应用到勾选项').trigger('click')
  await flushPromises()
}
const saved = (id, command) => ({ data: { taskId: id, projectId: 11, lockVersion: 5, currentStart: command.expectedStartTime, currentEnd: command.expectedEndTime } })

describe('排期批量修改', () => {
  beforeEach(() => { vi.clearAllMocks(); updateTaskSchedule.mockReset(); updateTaskSchedule.mockImplementation(async (id, command) => saved(id, command)) })
  afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })

  it('只保存勾选的镜头和资产分项，沿用锁号及独立幂等键', async () => {
    open(); await select([0, 1]); await common()
    await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule.mock.calls.map(call => call[0])).toEqual([1, 2])
    expect(updateTaskSchedule.mock.calls[0][1]).toEqual({ lockVersion: 4, expectedStartTime: range[0], expectedEndTime: range[1], changeReason: '', operationSource: 'dialog' })
    expect(updateTaskSchedule.mock.calls[0][2]).toBeTruthy()
    expect(updateTaskSchedule.mock.calls[0][2]).not.toEqual(updateTaskSchedule.mock.calls[1][2])
    expect(wrapper.emitted('close')[0][0]).toEqual({ attempted: true, savedCount: 2 })
  })

  it('逐项编辑不要求统一周期，未填写的勾选项校验失败时不请求', async () => {
    open(); await select([0, 1])
    wrapper.findAllComponents(ScheduleDateRangePicker)[1].vm.$emit('update:modelValue', range)
    await flushPromises(); await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(wrapper.text()).toContain('请选择完整周期'))
    wrapper.findAllComponents(ScheduleDateRangePicker)[2].vm.$emit('update:modelValue', range)
    await flushPromises(); await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule).toHaveBeenCalledTimes(2)
  })

  it('保留先前成功结果，失败后不提交后续任务且不重复重试', async () => {
    updateTaskSchedule.mockImplementationOnce(async (id, command) => saved(id, command)).mockRejectedValueOnce(new Error('版本已变化'))
    open(); await select([0, 1, 2]); await common()
    await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已保存 1 项')
    expect(wrapper.text()).toContain('未执行')
    expect(button('保存勾选项').props('disabled')).toBe(true)
    await button('关闭并刷新').trigger('click'); await flushPromises()
    expect(wrapper.emitted('close')[0][0]).toEqual({ attempted: true, savedCount: 1 })
  })

  it('保存中禁止重复提交，身份或范围改变后停止剩余项', async () => {
    let resolve
    const scope = reactive({ valid: true })
    updateTaskSchedule.mockImplementationOnce((id, command) => new Promise(done => { resolve = () => done(saved(id, command)) }))
    open(tasks, () => scope.valid); await select([0, 1]); await common()
    await button('保存勾选项').trigger('click'); await flushPromises()
    expect(wrapper.getComponent(ElForm).props('disabled')).toBe(true)
    await button('保存勾选项').trigger('click')
    scope.valid = false; resolve(); await flushPromises()
    expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已停止后续保存')
  })

  it('无权限、已通过和其他项目行不可选择；清空选择使用表格选择状态', async () => {
    open([tasks[0], { ...tasks[1], allowedActions: [] }, { ...tasks[2], taskStatus: 'completed' }, { ...tasks[0], taskId: 4, projectId: 12 }])
    await select([0, 1, 2, 3])
    expect(wrapper.text()).toContain('已选 1 项')
    await button('清空选择').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已选 0 项')
  })

  it('返回任务身份不符时停止，不计为保存成功', async () => {
    updateTaskSchedule.mockResolvedValue({ data: { ...tasks[0], projectId: 12, lockVersion: 5, currentStart: range[0], currentEnd: range[1] } })
    open(); await select([0, 1]); await common()
    await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已保存 0 项')
    expect(wrapper.text()).toContain('返回结果不完整')
  })

  it('勾选但周期未变的任务跳过，放弃修改取消时留在编辑页', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    open([{ ...tasks[0], currentStart: range[0], currentEnd: range[1] }, tasks[1]])
    await select([0, 1]); await common()
    await button('取消').trigger('click'); await flushPromises()
    expect(wrapper.emitted('close')).toBeUndefined()
    await button('保存勾选项').trigger('click'); await flushPromises()
    expect(updateTaskSchedule.mock.calls.map(call => call[0])).toEqual([2])
  })
})
