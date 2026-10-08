import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElRadioGroup, ElSelect, ElSwitch, ElTable } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import { batchAssignAssetItemTasks, getAssetDetail, listAssetAssignees } from '@/api/shot-grid/assets'
import { getProjectDetail } from '@/api/shot-grid/projects'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import AssetItemBatchWorkspace from '@/views/asset/components/AssetItemBatchWorkspace.vue'

const feedbackOpen = vi.hoisted(() => vi.fn())
vi.mock('@/api/shot-grid/assets', () => ({ batchAssignAssetItemTasks: vi.fn(), getAssetDetail: vi.fn(), listAssetAssignees: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({ getProjectDetail: vi.fn() }))
vi.mock('@/api/shot-grid/schedules', () => ({ updateTaskSchedule: vi.fn() }))
vi.mock('@/components/RelatedDetailDrawer.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/version/BatchOverallFeedbackDialog.vue', () => ({ default: {
  setup(_props, { expose }) { expose({ open: feedbackOpen }) }, template: '<div />'
} }))
const asset = { projectId: 6, assetId: 10, assetName: '房间', lifecycleStatus: 'active' }
const range = ['2026-10-10T09:00:00', '2026-10-11T18:00:00']
const items = [11, 12].map((assetItemId, index) => ({ ...asset, assetItemId, productionItem: `视角${index}`, allowedActions: ['task.assign'],
  task: { taskId: 20 + index, taskStatus: 'not_started', lockVersion: 3, assigneeUserId: 7, expectedStartTime: range[0], expectedEndTime: range[1] } }))
let wrapper
const button = label => wrapper.findAllComponents(ElButton).find(item => item.text().includes(label))
async function click(label) { await button(label).trigger('click'); await flushPromises() }
async function choose(action) { wrapper.getComponent(ElRadioGroup).vm.$emit('change', action); await flushPromises() }
async function open() {
  wrapper = mount(AssetItemBatchWorkspace, { attachTo: document.body, props: { projectId: 6, contextKey: '6' } })
  await wrapper.vm.open([asset])
  await flushPromises()
  const table = wrapper.getComponent(ElTable)
  for (const row of table.props('data')) table.vm.$.exposed.toggleRowSelection(row, true)
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  useSessionStore().permissions = ['shotgrid:asset:query', 'shotgrid:task:assign', 'shotgrid:task:schedule']
  getProjectDetail.mockResolvedValue({ data: { projectId: 6, myProjectRole: 'director', projectStatus: 'active' } })
  getAssetDetail.mockResolvedValue({ data: { ...asset, items } })
  listAssetAssignees.mockResolvedValue({ rows: [{ userId: 7, userName: '制作甲', producerCode: 'A' }, { userId: 8, userName: '制作乙', producerCode: 'B' }] })
  batchAssignAssetItemTasks.mockReset().mockResolvedValue({ data: {} })
  updateTaskSchedule.mockReset().mockResolvedValue({ data: {} })
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })
describe('资产分项批量工作区', () => {
  it('内网 HTTP 缺少 randomUUID 时仍显示所选排期行并生成独立请求键', async () => {
    vi.stubGlobal('crypto', { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) })
    await open()
    await choose('schedule')
    const scheduleRows = wrapper.getComponent(ElTable).props('data')
    expect(scheduleRows.map(row => row.assetItemId)).toEqual([11, 12])
    expect(button('确认保存').text()).toContain('2 个分项')
    expect(scheduleRows[0].key).not.toBe(scheduleRows[1].key)
    scheduleRows.forEach(row => { row.range = ['2026-10-12T09:00:00', '2026-10-13T18:00:00'] })
    await click('确认保存')
    expect(updateTaskSchedule).toHaveBeenCalledTimes(2)
    expect(updateTaskSchedule.mock.calls.map(call => call[2])).toEqual(scheduleRows.map(row => row.key))
  })
  it('父资产批量入口只加载当前状态分项，切换操作不扩大范围', async () => {
    getAssetDetail.mockResolvedValue({ data: { ...asset, items: [{ ...items[0], assetStatus: 'revision' }, { ...items[1], assetStatus: 'reviewing' }] } })
    wrapper = mount(AssetItemBatchWorkspace, { attachTo: document.body, props: { projectId: 6, contextKey: '6:revision', itemStatus: 'revision' } })
    await wrapper.vm.open([asset])
    await flushPromises()
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.assetItemId)).toEqual([11])
    await choose('schedule')
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.assetItemId)).toEqual([11])
  })

  it('从父资产排期入口加载后，真实复选框可勾选并进入排期表单', async () => {
    wrapper = mount(AssetItemBatchWorkspace, { attachTo: document.body, props: { projectId: 6, contextKey: '6' } })
    await wrapper.vm.open([asset], [], 'schedule')
    await flushPromises()
    expect(listAssetAssignees).toHaveBeenCalledWith(6, { pageNum: 1, pageSize: 100 }, expect.any(Object))
    const producerCells = [...document.body.querySelectorAll('.el-table__body-wrapper tr')].map(row => row.querySelectorAll('td')[2]?.textContent.trim())
    expect(producerCells).toEqual(['制作甲', '制作甲'])
    const checkbox = document.body.querySelector('.el-table__body-wrapper input[type="checkbox"]')
    expect(checkbox.disabled).toBe(false)
    checkbox.click()
    await flushPromises()
    await click('下一步：填写排期')
    expect(button('确认保存').text()).toContain('1 个分项')
    expect(updateTaskSchedule).not.toHaveBeenCalled()
  })

  it('切换操作过滤不适用分项，并可查看具体原因', async () => {
    getAssetDetail.mockResolvedValue({ data: { ...asset, items: [items[0], { ...items[1], task: null }] } })
    await open()
    await choose('schedule')
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.assetItemId)).toEqual([11])
    expect(document.body.textContent).toContain('1 个分项不适用于此操作')
    wrapper.getComponent(ElSwitch).vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(wrapper.getComponent(ElTable).props('data')).toHaveLength(2)
    expect(document.body.textContent).toContain('请先分配制作人')
    expect(button('下一步：填写排期').props('disabled')).toBe(false)
  })
  it('列表所选分项限定操作范围，返回选择保留勾选', async () => {
    wrapper = mount(AssetItemBatchWorkspace, { attachTo: document.body, props: { projectId: 6, contextKey: '6' } })
    await wrapper.vm.open([asset], [12], 'assign')
    await flushPromises()
    expect(button('确认保存').text()).toContain('1 个分项')
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.assetItemId)).toEqual([12])
    await click('返回选择')
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.assetItemId)).toEqual([12])
    expect(button('下一步：选择制作人').props('disabled')).toBe(false)
    expect(batchAssignAssetItemTasks).not.toHaveBeenCalled()
  })

  it('明确勾选分项后逐行分配不同制作人，连续点击只发送一批并使用任务锁', async () => {
    await open()
    await choose('assign')
    const selects = wrapper.findAllComponents(ElSelect)
    selects[2].vm.$emit('update:modelValue', '8')
    button('确认保存').vm.$emit('click', new MouseEvent('click'))
    button('确认保存').vm.$emit('click', new MouseEvent('click'))
    await flushPromises()
    expect(batchAssignAssetItemTasks.mock.calls).toEqual([
      [6, 7, [{ assetItemId: 11, taskLockVersion: 3 }]],
      [6, 8, [{ assetItemId: 12, taskLockVersion: 3 }]]
    ])
  })
  it('第一组失败即停止，保留结果并禁止重复保存', async () => {
    batchAssignAssetItemTasks.mockRejectedValue({ status: 409, message: '任务已变化' })
    await open()
    await choose('assign')
    wrapper.findAllComponents(ElSelect)[2].vm.$emit('update:modelValue', '8')
    await click('确认保存')
    expect(batchAssignAssetItemTasks).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('任务已变化')
    expect(document.body.textContent).toContain('未执行')
    expect(button('确认保存')).toBeUndefined()
    expect(button('完成')).toBeTruthy()
  })
  it('批量排期跳过未改动项，只保存真正调整的分项', async () => {
    await open()
    await choose('schedule')
    const table = wrapper.getComponent(ElTable)
    table.props('data')[1].range = ['2026-10-12T09:00:00', '2026-10-13T18:00:00']
    await click('确认保存')
    expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
    expect(updateTaskSchedule).toHaveBeenCalledWith(21, expect.objectContaining({ lockVersion: 3, expectedStartTime: '2026-10-12T09:00:00' }), expect.any(String))
    expect(document.body.textContent).toContain('未改动，已跳过')
  })
  it('逐行表单校验无效制作人，失败不发送请求', async () => {
    await open()
    await choose('assign')
    wrapper.findAllComponents(ElSelect)[1].vm.$emit('update:modelValue', '')
    await click('确认保存')
    expect(batchAssignAssetItemTasks).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(document.body.textContent).toContain('请选择有效制作人'))
  })
  it('切换项目后忽略迟到结果，不保存第二组', async () => {
    let resolve
    batchAssignAssetItemTasks.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await open()
    await choose('assign')
    wrapper.findAllComponents(ElSelect)[2].vm.$emit('update:modelValue', '8')
    await click('确认保存')
    await wrapper.setProps({ projectId: 7, contextKey: '7' })
    resolve({ data: {} })
    await flushPromises()
    expect(batchAssignAssetItemTasks).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
  it('批量反馈传递勾选分项的最新版本和完整分项标题', async () => {
    useSessionStore().permissions = ['shotgrid:asset:query', 'shotgrid:version:review', 'shotgrid:version:query', 'shotgrid:note:add']
    getAssetDetail.mockResolvedValue({ data: { ...asset, items: items.map((item, index) => ({
      ...item, allowedActions: ['task.review'], latestVersion: { versionId: 30 + index, versionNumber: 'V002' }
    })) } })
    await open()
    await choose('review')
    expect(feedbackOpen).toHaveBeenCalledWith(6, [
      expect.objectContaining({ assetItemId: 11, displayLabel: '房间 · 视角0', latestVersion: { versionId: 30, versionNumber: 'V002' } }),
      expect.objectContaining({ assetItemId: 12, displayLabel: '房间 · 视角1', latestVersion: { versionId: 31, versionNumber: 'V002' } })
    ], expect.any(Function))
  })
})
