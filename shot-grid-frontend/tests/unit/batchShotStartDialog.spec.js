import { ElAlert, ElButton, ElCheckbox, ElDatePicker, ElDialog, ElForm, ElFormItem, ElOption, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BatchShotStartDialog from '@/views/shot/components/BatchShotStartDialog.vue'
import { getShotDetail } from '@/api/shot-grid/shots'
import { startTask } from '@/api/shot-grid/tasks'
import { buttonLabel, expectedTaskTimes } from '../helpers/elementPlus'

vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ startTask: vi.fn() }))
const shots = [1, 2, 3].map(id => ({ shotId: id, taskId: id + 10, shotCode: `000${id}`, taskLockVersion: id, lockVersion: id + 1 }))
const components = { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElOption, ElSelect, ElTable, ElTableColumn }
async function open(validateContext = () => true) {
  const wrapper = mount(BatchShotStartDialog, {
    props: { context: { shots, projectId: 8, members: [], validateContext } },
    global: { components, stubs: { ShotProductionInfo: true } }
  })
  await flushPromises()
  return wrapper
}
const button = (wrapper, label) => wrapper.findAllComponents(ElButton).find(item => buttonLabel(item) === label)
async function fill(wrapper) {
  wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', [expectedTaskTimes.expectedStartTime, expectedTaskTimes.expectedEndTime])
  await wrapper.findComponent(ElCheckbox).find('input').setValue(true)
  await flushPromises()
}
async function submit(wrapper) {
  await button(wrapper, '确认批量开工').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  getShotDetail.mockImplementation((_projectId, shotId) => Promise.resolve({ data: {
    ...shots[shotId - 1], allowedActions: ['task.start'],
    task: { taskId: shotId + 10, lockVersion: shotId,
      ...(shotId === 2 ? { expectedStartTime: '2026-01-01T09:00:00', expectedEndTime: '2026-01-02T18:00:00' } : {}) }
  } }))
  startTask.mockReset().mockResolvedValue({ data: { taskStatus: 'preparing' } })
})

describe('镜头批量开工', () => {
  it('选择今天沿用未来五分钟与结束日18点，禁用过去日期和时分秒并能提交', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 28, 10, 30, 20))
    const wrapper = await open()
    try {
      const picker = wrapper.findComponent(ElDatePicker)
      const [start, end] = picker.props('defaultTime')
      expect([start.getHours(), start.getMinutes(), start.getSeconds()]).toEqual([10, 35, 20])
      expect([end.getHours(), end.getMinutes(), end.getSeconds()]).toEqual([18, 0, 0])
      expect(picker.props('disabledDate')(new Date(2026, 8, 27))).toBe(true)
      expect(picker.props('disabledDate')(new Date(2026, 8, 28))).toBe(false)
      picker.vm.$emit('calendar-change', [new Date(2026, 8, 28), new Date(2026, 9, 7)])
      await flushPromises()
      expect(picker.props('disabledHours')('start')).toContain(9)
      expect(picker.props('disabledHours')('start')).not.toContain(10)
      expect(picker.props('disabledMinutes')(10, 'start')).toContain(29)
      expect(picker.props('disabledSeconds')(10, 30, 'start')).toContain(19)
      expect(picker.props('disabledHours')('end')).toEqual([])
      picker.vm.$emit('update:modelValue', ['2026-09-28T10:35:20', '2026-10-07T18:00:00'])
      await submit(wrapper)
      expect(startTask).toHaveBeenNthCalledWith(1, 11, expect.objectContaining({
        expectedStartTime: '2026-09-28T10:35:20', expectedEndTime: '2026-10-07T18:00:00'
      }))
    } finally { wrapper.unmount(); vi.useRealTimers() }
  })

  it('真实表单拒绝缺少确认、缺少或无效时间，重置后恢复草稿，成功提交保留已有排期', async () => {
    const wrapper = await open()
    try {
      expect(wrapper.findComponent(ElCheckbox).props('modelValue')).toBe(true)
      await wrapper.findComponent(ElCheckbox).find('input').setValue(false)
      await submit(wrapper)
      expect(startTask).not.toHaveBeenCalled()
      await vi.waitFor(() => expect(wrapper.findComponent(ElForm).text()).toContain('请先确认全部镜头的开工条件'))
      await fill(wrapper)
      await wrapper.findComponent(ElCheckbox).find('input').setValue(false)
      await button(wrapper, '重置').trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(ElCheckbox).props('modelValue')).toBe(true)
      expect(wrapper.findComponent(ElDatePicker).props('modelValue')).toEqual([])
      await fill(wrapper)
      wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2000-01-01T09:00:00', '2000-01-02T18:00:00'])
      await submit(wrapper)
      expect(startTask).not.toHaveBeenCalled()
      await fill(wrapper)
      await submit(wrapper)
      expect(startTask).toHaveBeenCalledTimes(3)
      expect(startTask).toHaveBeenNthCalledWith(1, 11, { lockVersion: 1, shotLockVersion: 2, assetsConfirmed: true, ...expectedTaskTimes })
      expect(startTask).toHaveBeenNthCalledWith(2, 12, { lockVersion: 2, shotLockVersion: 3, assetsConfirmed: true, priority: 'normal' })
      expect(document.body.textContent).toContain('已确认开工 3 / 3')
      expect(button(wrapper, '确认批量开工')).toBeUndefined()
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
