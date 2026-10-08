import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElCheckboxGroup, ElCollapse, ElInput } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { adjustAssetProduction, getAssetDetail } from '@/api/shot-grid/assets'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import AssetProductionAdjustmentDialog from '@/views/asset/components/AssetProductionAdjustmentDialog.vue'

vi.mock('@/api/shot-grid/assets', () => ({ adjustAssetProduction: vi.fn(), getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
const asset = { projectId: 6, assetId: 10, lockVersion: 2 }
const item = { projectId: 6, assetId: 10, assetItemId: 11, lockVersion: 3, description: '原分项说明',
  allowedActions: ['task.adjust'], task: { taskId: 20, lockVersion: 4, taskStatus: 'in_progress' } }
let wrapper
let current
const button = label => wrapper.findAllComponents(ElButton).find(node => node.text() === label)
async function open() {
  wrapper = mount(AssetProductionAdjustmentDialog, { attachTo: document.body, props: { context: {
    projectId: 6, targets: [{ ...item, asset, displayLabel: '房间 · 主视角' }],
    permissions: ['shotgrid:task:edit', 'shotgrid:task:query', 'shotgrid:asset:edit'], validateContext: () => current
  } } })
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  current = true
  getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item] } })
  getTaskDetail.mockResolvedValue({ data: { taskId: 20, lockVersion: 4, requirements: '原制作要求', priority: 'normal' } })
  adjustAssetProduction.mockReset().mockResolvedValue({ data: {} })
})
afterEach(() => wrapper?.unmount())
describe('资产制作要求受控调整', () => {
  it('单项直接填写，仅保存变更字段并携带三份锁', async () => {
    await open()
    wrapper.getComponent(ElCollapse).vm.$emit('update:modelValue', ['more'])
    await flushPromises()
    const inputs = wrapper.findAllComponents(ElInput).filter(input => input.props('type') === 'textarea')
    await inputs[0].get('textarea').setValue('新的制作要求')
    await inputs[2].get('textarea').setValue('新的分项说明')
    await button('保存修改').trigger('click')
    await flushPromises()
    expect(adjustAssetProduction).toHaveBeenCalledTimes(1)
    expect(adjustAssetProduction).toHaveBeenCalledWith(6, { reason: '', items: [{
      taskId: 20, assetId: 10, assetItemId: 11, lockVersion: 4, assetLockVersion: 2, assetItemLockVersion: 3,
      changes: { requirements: '新的制作要求', description: '新的分项说明' }
    }] })
  })
  it('批量仍需选择字段并核对后保存全部目标', async () => {
    const second = { ...item, assetItemId: 12, task: { ...item.task, taskId: 21 } }
    getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item, second] } })
    getTaskDetail.mockImplementation(async taskId => ({ data: { taskId, lockVersion: 4, requirements: '原制作要求', priority: 'normal' } }))
    wrapper = mount(AssetProductionAdjustmentDialog, { attachTo: document.body, props: { context: {
      projectId: 6, targets: [item, second].map(row => ({ ...row, asset, displayLabel: `房间 · ${row.assetItemId}` })),
      permissions: ['shotgrid:task:edit', 'shotgrid:task:query'], validateContext: () => current
    } } })
    await flushPromises()
    wrapper.getComponent(ElCheckboxGroup).vm.$emit('update:modelValue', ['requirements'])
    await flushPromises()
    await wrapper.findAllComponents(ElInput).find(input => input.props('type') === 'textarea').get('textarea').setValue('共同要求')
    await button('下一步：核对').trigger('click'); await flushPromises()
    expect(adjustAssetProduction).not.toHaveBeenCalled()
    await button('确认保存').trigger('click'); await flushPromises()
    expect(adjustAssetProduction.mock.calls[0][1].items.map(row => row.assetItemId)).toEqual([11, 12])
  })
  it('重读分项锁已变化时阻止编辑和保存', async () => {
    getAssetDetail.mockResolvedValue({ data: { ...asset, items: [{ ...item, lockVersion: 5 }] } })
    await open()
    expect(document.body.textContent).toContain('分项或任务已变化')
    expect(button('保存修改').props('disabled')).toBe(true)
    expect(adjustAssetProduction).not.toHaveBeenCalled()
  })
})
