import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElButton, ElCheckbox, ElTable } from 'element-plus'
import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { startTask } from '@/api/shot-grid/tasks'
import AssetStartDrawer from '@/views/asset/components/AssetStartDrawer.vue'
vi.mock('@/api/shot-grid/assets', () => ({ getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ startTask: vi.fn() }))
const asset = { projectId: 6, assetId: 10, assetName: '房间', lifecycleStatus: 'active', lockVersion: 2, allowedActions: ['task.start'] }
const item = { projectId: 6, assetId: 10, assetItemId: 11, productionItem: '概念设计', lifecycleStatus: 'active', lockVersion: 3, allowedActions: ['task.start'], task: { taskId: 20, lockVersion: 4, taskStatus: 'not_started', expectedStartTime: '2026-10-08T10:00:00', expectedEndTime: '2026-10-09T10:00:00' } }
let wrapper
const button = () => wrapper.findAllComponents(ElButton).find(node => node.text().startsWith('确认开工'))
beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()); useSessionStore().permissions = ['shotgrid:asset:query', 'shotgrid:task:start']; getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item] } }); startTask.mockReset().mockResolvedValue({ data: { taskStatus: 'preparing' } }) })
afterEach(() => wrapper?.unmount())
async function open() { wrapper = mount(AssetStartDrawer, { attachTo: document.body, props: { projectId: 6, contextKey: '6' } }); await wrapper.vm.open(asset); await flushPromises() }
it('单项直接确认，未确认条件不提交，开工携带三份锁', async () => {
  await open()
  await button().trigger('click'); await flushPromises()
  expect(startTask).not.toHaveBeenCalled()
  wrapper.findAllComponents(ElCheckbox).at(-1).vm.$emit('update:modelValue', true)
  await button().trigger('click'); await flushPromises()
  expect(startTask).toHaveBeenCalledWith(20, { lockVersion: 4, assetLockVersion: 2, assetItemLockVersion: 3, startConfirmed: true })
  expect(document.body.textContent).toContain('目录准备中')
})
it('多个分项不默认选择，未排期项不能选，失败停止后续提交', async () => {
  getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item, { ...item, assetItemId: 12, task: { ...item.task, taskId: 21 } }, { ...item, assetItemId: 13, task: { ...item.task, expectedEndTime: null } }] } })
  await open()
  expect(button().props('disabled')).toBe(true)
  const table = wrapper.getComponent(ElTable)
  expect(table.props('data')).toHaveLength(2)
  table.props('data').forEach(row => table.vm.$.exposed.toggleRowSelection(row, true))
  wrapper.findAllComponents(ElCheckbox).at(-1).vm.$emit('update:modelValue', true)
  await flushPromises()
  startTask.mockRejectedValue({ status: 409, message: '任务已变化' })
  await button().trigger('click'); await flushPromises()
  expect(startTask).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('未执行')
  expect(button()).toBeUndefined()
})
it('项目切换后忽略迟到数据', async () => {
  let resolve
  getAssetDetail.mockReturnValue(new Promise(done => { resolve = done }))
  wrapper = mount(AssetStartDrawer, { attachTo: document.body, props: { projectId: 6, contextKey: '6' } })
  const pending = wrapper.vm.open(asset)
  await wrapper.setProps({ projectId: 7, contextKey: '7' })
  resolve({ data: { ...asset, items: [item] } }); await pending; await flushPromises()
  expect(wrapper.text()).not.toContain('概念设计')
  expect(startTask).not.toHaveBeenCalled()
})
