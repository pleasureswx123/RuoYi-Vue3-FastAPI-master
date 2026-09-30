import { ElAlert, ElButton, ElCheckbox, ElDatePicker, ElDialog, ElForm, ElFormItem, ElInput, ElOption, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BatchShotStartDialog from '@/views/shot/components/BatchShotStartDialog.vue'
import { getShotDetail } from '@/api/shot-grid/shots'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { startTask } from '@/api/shot-grid/tasks'
import { buttonLabel } from '../helpers/elementPlus'

vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/schedules', () => ({ updateTaskSchedule: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ startTask: vi.fn() }))
const shots = [1, 2, 3].map(id => ({ shotId: id, taskId: id + 10, shotCode: `000${id}`, taskLockVersion: id, lockVersion: id + 1 }))
const components = { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElInput, ElOption, ElSelect, ElTable, ElTableColumn }
async function open(validateContext = () => true, extra = {}) {
  const wrapper = mount(BatchShotStartDialog, {
    props: { context: { shots, projectId: 8, members: [], validateContext, canSchedule: true, ...extra } },
    global: { components, stubs: { ShotProductionInfo: true } }
  })
  await flushPromises()
  return wrapper
}
const button = (wrapper, label) => wrapper.findAllComponents(ElButton).find(item => label === '确认批量开工' ? buttonLabel(item).startsWith('确认开工（') : buttonLabel(item) === label)
async function fill(wrapper) {
  await wrapper.findComponent(ElForm).findComponent(ElCheckbox).find('input').setValue(true)
  await flushPromises()
}
async function submit(wrapper) {
  await button(wrapper, '确认批量开工').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  updateTaskSchedule.mockReset()
  getShotDetail.mockImplementation((_projectId, shotId) => Promise.resolve({ data: {
    ...shots[shotId - 1], allowedActions: ['task.start'],
    task: { taskId: shotId + 10, lockVersion: shotId,
      expectedStartTime: '2026-01-01T09:00:00', expectedEndTime: '2026-01-02T18:00:00' }
  } }))
  startTask.mockReset().mockResolvedValue({ data: { taskStatus: 'preparing' } })
})

describe('镜头批量开工', () => {
  it('已排期任务聚焦开工核对，不展示排期工具和调整入口', async () => {
    const wrapper = await open()
    try {
      const labels = wrapper.findAllComponents(ElButton).map(buttonLabel)
      expect(labels).not.toContain('调整排期')
      expect(labels).not.toContain('仅选择已排期项')
      expect(labels.some(label => label.startsWith('统一设置未排期'))).toBe(false)
      expect(wrapper.findAllComponents(ElTableColumn).map(column => column.props('label'))).toContain('制作内容')
      expect(button(wrapper, '确认批量开工')).toBeTruthy()
    } finally { wrapper.unmount() }
  })

  it('存在未排期任务时整批禁止开工，不在开工请求中补填日期', async () => {
    getShotDetail.mockResolvedValue({ data: { ...shots[0], allowedActions: ['task.start'], task: { taskId: 11, lockVersion: 1 } } })
    const wrapper = mount(BatchShotStartDialog, { props: { context: { shots: [shots[0]], projectId: 8, members: [], validateContext: () => true } }, global: { components } })
    try {
      await flushPromises()
      expect(button(wrapper, '确认批量开工').props('disabled')).toBe(true)
      expect(wrapper.findComponent(ElDatePicker).exists()).toBe(false)
      await submit(wrapper)
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('确认条件校验后沿用各项排期，不再提交日期字段', async () => {
    const wrapper = await open()
    try {
      await wrapper.findComponent(ElForm).findComponent(ElCheckbox).find('input').setValue(false)
      await submit(wrapper)
      expect(startTask).not.toHaveBeenCalled()
      await fill(wrapper)
      await submit(wrapper)
      expect(startTask).toHaveBeenCalledTimes(3)
      expect(startTask).toHaveBeenNthCalledWith(1, 11, { lockVersion: 1, shotLockVersion: 2, assetsConfirmed: true, priority: 'normal' })
    } finally { wrapper.unmount() }
  })

  it('统一补齐未排期项后保留选择，沿用成功响应的新版本确认开工', async () => {
    getShotDetail.mockImplementation((_projectId, id) => Promise.resolve({ data: { ...shots[id - 1], allowedActions: ['task.start'], task: { taskId: id + 10, lockVersion: id, ...(id === 1 ? { expectedStartTime: '2026-01-01T09:00:00', expectedEndTime: '2026-01-02T18:00:00' } : {}) } } }))
    updateTaskSchedule.mockImplementation((id, data) => Promise.resolve({ data: { taskId: id, lockVersion: data.lockVersion + 1, currentStart: data.expectedStartTime, currentEnd: data.expectedEndTime } }))
    const wrapper = await open()
    try {
      await button(wrapper, '统一设置未排期（2）').trigger('click'); await flushPromises()
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule).not.toHaveBeenCalled()
      wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2026-10-01T09:00:00', '2026-10-05T18:00:00'])
      // 不填原因也可以批量保存排期。
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule.mock.calls.map(call => call[0])).toEqual([12, 13])
      expect(startTask).not.toHaveBeenCalled()
      expect(button(wrapper, '确认批量开工').text()).toContain('3 项')
      await submit(wrapper)
      expect(startTask).toHaveBeenNthCalledWith(2, 12, expect.objectContaining({ lockVersion: 3 }))
    } finally { wrapper.unmount() }
  })
  it('仅选择已排期项必须显式操作；只对选择范围开工', async () => {
    getShotDetail.mockImplementation((_projectId, id) => Promise.resolve({ data: { ...shots[id - 1], allowedActions: ['task.start'], task: { taskId: id + 10, lockVersion: id, ...(id === 1 ? { expectedStartTime: '2026-01-01', expectedEndTime: '2026-01-02' } : {}) } } }))
    const wrapper = await open()
    try {
      await button(wrapper, '仅选择已排期项').trigger('click'); await flushPromises()
      expect(button(wrapper, '确认批量开工').text()).toContain('1 项')
      await submit(wrapper)
      expect(startTask).toHaveBeenCalledTimes(1)
      expect(startTask.mock.calls[0][0]).toBe(11)
    } finally { wrapper.unmount() }
  })
  it('独立排期模式不提供开工动作，部分失败保留逐项结果', async () => {
    updateTaskSchedule.mockResolvedValueOnce({ data: { taskId: 11, lockVersion: 2, currentStart: '2026-10-01', currentEnd: '2026-10-05' } }).mockRejectedValue({ httpStatus: 409, message: '版本冲突' })
    const wrapper = await open(() => true, { mode: 'schedule' })
    try {
      expect(button(wrapper, '确认批量开工')).toBeUndefined()
      wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2026-10-01T09:00:00', '2026-10-05T18:00:00'])
      await button(wrapper, '应用到勾选项').trigger('click'); await flushPromises()
      await wrapper.findAllComponents(ElInput).find(input => input.props('type') === 'textarea').find('textarea').setValue('修改计划')
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(document.body.textContent).toContain('排期已保存，尚未开工')
      expect(document.body.textContent).toContain('版本冲突')
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it('行内排期支持统一应用后逐行微调，只在最终保存时写入', async () => {
    updateTaskSchedule.mockImplementation((id, data) => Promise.resolve({ data: { taskId: id, lockVersion: data.lockVersion + 1, currentStart: data.expectedStartTime, currentEnd: data.expectedEndTime } }))
    const wrapper = await open(() => true, { mode: 'schedule' })
    try {
      expect(wrapper.findAllComponents(ElDatePicker)).toHaveLength(4)
      const dates = wrapper.findAllComponents(ElDatePicker)
      dates[0].vm.$emit('update:modelValue', ['2026-10-01T09:00:00', '2026-10-05T18:00:00'])
      await button(wrapper, '应用到勾选项').trigger('click'); await flushPromises()
      dates[2].vm.$emit('update:modelValue', ['2026-10-02T09:00:00', '2026-10-06T18:00:00'])
      await flushPromises()
      expect(updateTaskSchedule).not.toHaveBeenCalled()
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule).toHaveBeenCalledTimes(3)
      expect(updateTaskSchedule.mock.calls[1][1]).toMatchObject({ expectedStartTime: '2026-10-02T09:00:00', expectedEndTime: '2026-10-06T18:00:00', changeReason: '' })
      expect(startTask).not.toHaveBeenCalled()
      expect(wrapper.emitted('close')[0][0]).toEqual({ attempted: true })
    } finally { wrapper.unmount() }
  })
  it('行内时间缺失阻止保存，取消不提交草稿', async () => {
    const wrapper = await open(() => true, { mode: 'schedule' })
    try {
      wrapper.findAllComponents(ElDatePicker)[1].vm.$emit('update:modelValue', [])
      await flushPromises()
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule).not.toHaveBeenCalled()
      await button(wrapper, '取消').trigger('click')
      expect(wrapper.emitted('close')[0][0]).toEqual({ attempted: false })
    } finally { wrapper.unmount() }
  })

  it.each([true, false])('单项排期入口 single=%s 只展示一个时间组件，直接校验保存', async single => {
    updateTaskSchedule.mockImplementation((id, data) => Promise.resolve({ data: { taskId: id, lockVersion: data.lockVersion + 1, currentStart: data.expectedStartTime, currentEnd: data.expectedEndTime } }))
    const wrapper = await open(() => true, { mode: 'schedule', single, shots: [shots[0]] })
    try {
      expect(wrapper.findAllComponents(ElDatePicker)).toHaveLength(1)
      expect(wrapper.find('.inline-schedule-toolbar').exists()).toBe(false)
      expect(wrapper.find('.inline-schedule-summary').exists()).toBe(false)
      expect(wrapper.findAllComponents(ElTableColumn).some(column => column.props('type') === 'selection')).toBe(false)
      const picker = wrapper.findComponent(ElDatePicker)
      picker.vm.$emit('update:modelValue', [])
      await flushPromises()
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule).not.toHaveBeenCalled()
      picker.vm.$emit('update:modelValue', ['2026-10-01T09:00:00', '2026-10-05T18:00:00'])
      await flushPromises()
      await button(wrapper, '保存排期').trigger('click'); await flushPromises()
      expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it('详情锁号不匹配时整批不提交，不静默使用新锁号', async () => {
    getShotDetail.mockResolvedValue({ data: { allowedActions: ['task.start'], task: { taskId: 11, lockVersion: 99 }, lockVersion: 2 } })
    const wrapper = await open()
    try {
      expect(document.body.textContent).toContain('任务或制作信息已变化')
      expect(button(wrapper, '确认批量开工')).toBeUndefined()
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it.each([409, 422, 403, 0])('失败 %s 显示部分结果且无自动重试', async status => {
    startTask.mockResolvedValueOnce({ data: { taskStatus: 'in_progress' } }).mockRejectedValueOnce({ httpStatus: status, message: '第二项失败' })
    const wrapper = await open()
    try {
      await fill(wrapper)
      await submit(wrapper)
      expect(startTask).toHaveBeenCalledTimes([409, 422].includes(status) ? 3 : 2)
      expect(document.body.textContent).toContain('第二项失败')
      expect(document.body.textContent).toContain('已开工，可以开始制作')
      expect(button(wrapper, '确认批量开工')).toBeUndefined()
      await button(wrapper, '关闭并刷新').trigger('click')
      expect(wrapper.emitted('close')[0][0]).toEqual({ attempted: true })
    } finally { wrapper.unmount() }
  })

  it('请求中防重复提交，项目失效后不再发送后续请求', async () => {
    let resolveStart
    let valid = true
    startTask.mockImplementation(() => new Promise(resolve => { resolveStart = resolve }))
    const wrapper = await open(() => valid)
    try {
      await fill(wrapper)
      await submit(wrapper)
      expect(button(wrapper, '确认批量开工').props('loading')).toBe(true)
      await submit(wrapper)
      expect(startTask).toHaveBeenCalledTimes(1)
      valid = false
      resolveStart({ data: { taskStatus: 'preparing' } })
      await flushPromises()
      expect(startTask).toHaveBeenCalledTimes(1)
    } finally { wrapper.unmount() }
  })

  it('卸载后丢弃详情迟到结果并停止获取其他项', async () => {
    let resolveDetail
    getShotDetail.mockImplementation(() => new Promise(resolve => { resolveDetail = resolve }))
    const wrapper = await open()
    wrapper.unmount()
    resolveDetail({ data: {} })
    await flushPromises()
    expect(getShotDetail).toHaveBeenCalledTimes(1)
    expect(startTask).not.toHaveBeenCalled()
  })
})
