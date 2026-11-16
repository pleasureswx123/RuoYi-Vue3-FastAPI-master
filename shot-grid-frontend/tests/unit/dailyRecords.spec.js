import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElButton, ElForm, ElSelect, ElInputNumber } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import DailyRecordsView from '@/views/workbench/DailyRecordsView.vue'
import { useSessionStore } from '@/store/modules/session'
import { dailyRequest, saveDailyRecords } from '@/api/shot-grid/dailyRecords'
import { getMineTaskPage } from '@/api/shot-grid/tasks'

vi.mock('@/api/shot-grid/dailyRecords', () => ({ dailyRequest: vi.fn(), saveDailyRecords: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ getMineTaskPage: vi.fn(), getTaskDetail: vi.fn() }))
let wrapper
const button = text => wrapper.findAllComponents(ElButton).find(b => b.text() === text)
async function setup(statistics = false) {
  const pinia = createPinia(); setActivePinia(pinia)
  const session = useSessionStore(); session.activeProjectId = '1'; session.user = { userId: 100 }; session.permissions = ['shotgrid:daily:write', 'shotgrid:daily:stats']
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/daily', name: statistics ? 'production-statistics' : 'daily-records', component: DailyRecordsView }] })
  await router.push('/daily?projectId=1'); await router.isReady()
  wrapper = mount(DailyRecordsView, { global: { plugins: [pinia, router, ElementPlus], stubs: { ElDrawer: { template: '<section><slot /><slot name="footer" /></section>' } } } })
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear()
  dailyRequest.mockImplementation(async (_id, suffix, _params, options) => options?.statistics && !suffix ? { data: { groups: [], platforms: [], submittedVersions: 2, approvedTasks: 1 } } : { data: { rows: [], total: 0 } })
  saveDailyRecords.mockResolvedValue({ data: [] })
  getMineTaskPage.mockResolvedValue({ rows: [{ taskId: 7, taskName: '镜头 0001', project: { projectId: 1 } }], total: 1 })
})
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })

it('每日记录默认当天范围，未填写必填字段不保存', async () => {
  await setup(); expect(dailyRequest.mock.calls[0][2].start).toBe(dailyRequest.mock.calls[0][2].end)
  await button('记录今日产出').trigger('click'); await flushPromises()
  await button('保存记录').trigger('click'); await flushPromises()
  expect(saveDailyRecords).not.toHaveBeenCalled()
})

it('多平台同任务一次保存，实际零积分保留，保存失败保留表单', async () => {
  await setup(); await button('记录今日产出').trigger('click'); await flushPromises()
  const form = wrapper.findAllComponents(ElForm).find(f => Object.hasOwn(f.props('model'), 'taskId'))
  const selects = form.findAllComponents(ElSelect)
  selects[0].vm.$emit('update:modelValue', 7)
  selects[1].vm.$emit('update:modelValue', '平台A')
  let inputs = form.findAllComponents(ElInputNumber)
  inputs[0].vm.$emit('update:modelValue', 2); inputs[1].vm.$emit('update:modelValue', 0)
  await flushPromises(); await button('＋ 添加平台记录').trigger('click'); await flushPromises()
  const platformSelects = form.findAllComponents(ElSelect).filter(s => s.props('placeholder') === '选择或输入')
  platformSelects[1].vm.$emit('update:modelValue', '平台B')
  inputs = form.findAllComponents(ElInputNumber)
  inputs[3].vm.$emit('update:modelValue', 3); inputs[5].vm.$emit('update:modelValue', 0.1)
  await flushPromises()
  saveDailyRecords.mockRejectedValueOnce(new Error('锁冲突'))
  await button('保存记录').trigger('click'); await flushPromises()
  expect(saveDailyRecords).toHaveBeenCalledTimes(1)
  const data = saveDailyRecords.mock.calls[0][1]
  expect(data.taskId).toBe(7); expect(data.lines).toHaveLength(2)
  expect(data.lines[0].actualPoints).toBe(0); expect(data.lines[1].actualPoints).toBeNull()
  expect(form.props('model').lines).toHaveLength(2)
  await button('保存记录').trigger('click'); await flushPromises()
  expect(saveDailyRecords.mock.calls[1][1].lines.map(l => l.recordId)).toEqual(data.lines.map(l => l.recordId))
})

it('统计页首次进入即读取本周统计和明细，不展示跨平台总积分', async () => {
  await setup(true)
  expect(dailyRequest).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).toContain('期间提交轮次')
  expect(wrapper.text()).toContain('期间曾通过任务（去重）')
  expect(wrapper.text()).toContain('不同平台积分不相加')
  expect(wrapper.text()).not.toContain('总积分')
})
