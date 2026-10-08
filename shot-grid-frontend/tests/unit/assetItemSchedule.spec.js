import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getProjectDetail } from '@/api/shot-grid/projects'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import AssetItemScheduleDialog from '@/views/asset/components/AssetItemScheduleDialog.vue'
import { canScheduleAssetItem, assetItemScheduleLabel } from '@/views/asset/assetItemActions'

vi.mock('@/api/shot-grid/assets', () => ({ getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({ getProjectDetail: vi.fn() }))
vi.mock('@/api/shot-grid/schedules', () => ({ updateTaskSchedule: vi.fn() }))
vi.mock('@/views/schedule/components/ScheduleEditDialog.vue', () => ({ default: {
  name: 'ScheduleEditDialog', props: ['visible', 'task', 'draft', 'saving', 'error'],
  emits: ['save-request', 'cancel', 'update:visible'], template: '<div />'
} }))
const parent = { projectId: 6, assetId: 10, lifecycleStatus: 'active', allowedActions: [] }
const item = { projectId: 6, assetId: 10, assetItemId: 11, lifecycleStatus: 'active', productionItem: '三视图',
  task: { taskId: 20, taskStatus: 'not_started', lockVersion: 3 } }
const command = { expectedStartTime: '2026-10-10T09:00:00', expectedEndTime: '2026-10-11T18:00:00', changeReason: '', operationSource: 'dialog' }
function setup() {
  const wrapper = mount(AssetItemScheduleDialog, { props: { projectId: 6, contextKey: '6' } })
  return { wrapper, dialog: () => wrapper.findComponent({ name: 'ScheduleEditDialog' }) }
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  useSessionStore().permissions = ['shotgrid:asset:query', 'shotgrid:task:schedule']
  getProjectDetail.mockResolvedValue({ data: { projectId: 6, myProjectRole: 'director', projectStatus: 'active' } })
  getAssetDetail.mockResolvedValue({ data: { ...parent, assetName: '房间', items: [item] } })
  updateTaskSchedule.mockResolvedValue({ data: {} })
})
describe('资产分项独立排期', () => {
  it('仅排期权限即可打开和保存，使用重读锁版本且不触发开工', async () => {
    const { wrapper, dialog } = setup()
    try {
      await wrapper.vm.open(parent, item)
      expect(dialog().props('visible')).toBe(true)
      expect(dialog().props('task').target.name).toBe('房间 · 三视图')
      dialog().vm.$emit('save-request', command)
      dialog().vm.$emit('save-request', command)
      await flushPromises()
      expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
      expect(updateTaskSchedule).toHaveBeenCalledWith(20, { ...command, lockVersion: 3 }, expect.stringContaining('asset-schedule:20:'))
      expect(wrapper.emitted('changed')[0][0]).toEqual({ projectId: 6, assetId: 10, assetItemId: 11 })
      expect(item.task.taskStatus).toBe('not_started')
    } finally { wrapper.unmount() }
  })
  it('完整排期显示调整入口，已完成和跨资产分项不能排期', () => {
    expect(assetItemScheduleLabel(item)).toBe('设置排期')
    expect(assetItemScheduleLabel({ task: command })).toBe('调整排期')
    expect(canScheduleAssetItem(parent, item, true)).toBe(true)
    expect(canScheduleAssetItem(parent, { ...item, assetId: 12 }, true)).toBe(false)
    expect(canScheduleAssetItem(parent, { ...item, task: { ...item.task, taskStatus: 'completed' } }, true)).toBe(false)
    expect(canScheduleAssetItem(parent, item, false)).toBe(false)
  })
  it('成员没有管理范围时重读后拒绝排期', async () => {
    getProjectDetail.mockResolvedValue({ data: { projectId: 6, myProjectRole: 'creator', projectStatus: 'active' } })
    const { wrapper, dialog } = setup()
    try {
      await wrapper.vm.open(parent, item)
      expect(dialog().props('visible')).toBe(false)
      expect(updateTaskSchedule).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('切换项目丢弃迟到的读取结果', async () => {
    let resolve
    getAssetDetail.mockReturnValue(new Promise(done => { resolve = done }))
    const { wrapper, dialog } = setup()
    try {
      const loading = wrapper.vm.open(parent, item)
      await wrapper.setProps({ projectId: 7, contextKey: '7' })
      resolve({ data: { ...parent, items: [item] } })
      await loading
      expect(dialog().props('visible')).toBe(false)
      expect(updateTaskSchedule).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('409 保留提示并阻止以旧版本再次保存', async () => {
    updateTaskSchedule.mockRejectedValue({ status: 409, message: '版本冲突' })
    const { wrapper, dialog } = setup()
    try {
      await wrapper.vm.open(parent, item)
      dialog().vm.$emit('save-request', command)
      await flushPromises()
      expect(dialog().props('error').message).toContain('重新打开排期')
      dialog().vm.$emit('save-request', command)
      await flushPromises()
      expect(updateTaskSchedule).toHaveBeenCalledTimes(1)
      expect(wrapper.emitted('changed')).toBeUndefined()
    } finally { wrapper.unmount() }
  })
})
