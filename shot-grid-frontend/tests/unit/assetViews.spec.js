import { ElAlert, ElButton, ElCard, ElDatePicker, ElDescriptions, ElDescriptionsItem, ElDialog, ElDrawer, ElDropdown, ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElLoading, ElMessageBox, ElOption, ElPagination, ElRadioButton, ElRadioGroup, ElSelect, ElTable, ElTableColumn, ElTag, ElText } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  archiveAsset,
  archiveAssetItem,
  assignAssetItemTask,
  createAsset,
  createAssetItem,
  deleteAssetItem,
  downloadAssetThumbnail,
  getAssetDetail,
  getAssetItems,
  getAssetPage,
  getAssetRequirementPage,
  listAssetAssignees,
  resolveAssetRequirement,
  updateAsset,
  updateAssetItem
} from '@/api/shot-grid/assets'
import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { startTask } from '@/api/shot-grid/tasks'
import { useSessionStore } from '@/store/modules/session'
import { useThemeStore } from '@/store/modules/theme'
import { buttonLabel, completeTaskStartForm, expectedTaskTimes, setElSelectValue } from '../helpers/elementPlus'
import AssetDetailView from '@/views/asset/AssetDetailView.vue'
import AssetListView from '@/views/asset/AssetListView.vue'
import AssetArchiveDialog from '@/views/asset/components/AssetArchiveDialog.vue'
import AssetAssignDialog from '@/views/asset/components/AssetAssignDialog.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'
import AssetItemFormDialog from '@/views/asset/components/AssetItemFormDialog.vue'
import AssetItemDeleteDialog from '@/views/asset/components/AssetItemDeleteDialog.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import AssetRequirementDialog from '@/views/asset/components/AssetRequirementDialog.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  getProjectDetail: vi.fn(),
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/assets', () => ({
  archiveAsset: vi.fn(),
  archiveAssetItem: vi.fn(),
  deleteAssetItem: vi.fn(),
  assignAssetItemTask: vi.fn(),
  batchAssignAssetItemTasks: vi.fn(),
  batchDeleteAssets: vi.fn(),
  commitAssetImport: vi.fn(),
  createAsset: vi.fn(),
  createAssetItem: vi.fn(),
  downloadAssetImportTemplate: vi.fn(),
  downloadAssetThumbnail: vi.fn(),
  getAssetDetail: vi.fn(),
  getAssetItems: vi.fn(),
  getAssetPage: vi.fn(),
  getAssetRequirementPage: vi.fn(),
  ignoreAssetRequirement: vi.fn(),
  listAssetAssignees: vi.fn(),
  previewAssetImport: vi.fn(),
  rematchAssetRequirements: vi.fn(),
  resolveAssetRequirement: vi.fn(),
  updateAsset: vi.fn(),
  updateAssetItem: vi.fn()
}))
vi.mock('@/api/shot-grid/tasks', () => ({ startTask: vi.fn() }))

const projectRow = { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人' }
const memberRow = { userId: 7, userName: '杨景锋', nickName: 'YJF', producerCode: 'YJF' }
const assetRow = {
  assetId: 31,
  projectId: 8,
  assetType: 'Environment',
  assetName: '动力舱室内',
  description: '低温休眠舱内部环境',
  sortOrder: 10,
  lifecycleStatus: 'active',
  assetStatus: 'in_progress',
  itemCount: 1,
  usageShotCount: 12,
  assigneeUserIds: [7],
  assignees: [memberRow],
  directoryStatus: 'ready',
  thumbnail: null,
  allowedActions: ['asset.edit', 'asset.archive', 'assetItem.add'],
  lockVersion: 0,
  updateTime: '2026-08-11T10:00:00'
}
const assetItem = {
  assetItemId: 41,
  projectId: 8,
  assetId: 31,
  productionItem: '恐怖气氛主视角',
  description: '冷蓝色调主视角',
  sortOrder: 10,
  remark: null,
  lifecycleStatus: 'active',
  assetStatus: 'in_progress',
  task: null,
  latestVersion: null,
  finalVersion: null,
  thumbnail: null,
  allowedActions: ['assetItem.edit', 'assetItem.archive', 'task.assign'],
  lockVersion: 0,
  createTime: '2026-08-11T10:00:00',
  updateTime: '2026-08-11T10:00:00'
}

function assetDetail(targetProjectId = 8, targetAssetId = 31, name = '动力舱室内') {
  return {
    ...assetRow,
    projectId: targetProjectId,
    assetId: targetAssetId,
    assetName: name,
    descriptionLocked: false,
    storageDirName: '动力舱室内',
    remark: '保持冷蓝色调',
    items: [{ ...assetItem, projectId: targetProjectId, assetId: targetAssetId }],
    createBy: 'director',
    createTime: '2026-08-11T10:00:00',
    updateBy: 'director'
  }
}

function installSession(permissions) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin', nickName: '管理员' }
  session.permissions = permissions
  return pinia
}

async function mountList(permissions = ['shotgrid:asset:list', 'shotgrid:asset:add', 'shotgrid:asset:import']) {
  const pinia = installSession(permissions)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/assets', component: AssetListView },
      { path: '/projects/:projectId/assets/:assetId', component: { template: '<div>资产详情</div>' } }
    ]
  })
  await router.push('/assets?projectId=8')
  await router.isReady()
  const wrapper = mount(AssetListView, { global: { plugins: [pinia, router], stubs: { ProductionHistoryPanel: true }, components: { ElButton, ElCard, ElDatePicker, ElDescriptions, ElDescriptionsItem, ElDialog, ElDrawer, ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElPagination, ElRadioButton, ElRadioGroup, ElTable, ElTableColumn, ElTag } } })
  await flushPromises()
  await flushPromises()
  return { wrapper, router }
}

async function mountDetail(path = '/projects/8/assets/31', permissions = ['shotgrid:asset:query', 'shotgrid:asset:edit', 'shotgrid:asset:add', 'shotgrid:asset:archive', 'shotgrid:task:assign']) {
  const pinia = installSession(permissions)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/assets', component: { template: '<div>资产列表</div>' } },
      { path: '/projects/:projectId/assets/:assetId', component: AssetDetailView }
    ]
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(AssetDetailView, {
    global: {
      plugins: [pinia, router],
      components: { ElAlert, ElButton, ElSelect, ElOption, ElDatePicker, ElDescriptions, ElDescriptionsItem, ElDialog, ElForm, ElFormItem, ElIcon, ElInput, ElTag },
      stubs: {
        ProductionHistoryPanel: true,
        ProtectedAssetThumbnail: true,
        ElDialog: { template: '<section><slot name="header" /><slot /><slot name="footer" /></section>' }
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

function mountAssetDialog(component, props) {
  return mount(component, {
    props,
    global: {
      components: {
        ElAlert,
        ElButton,
        ElCard,
        ElDatePicker,
        ElDescriptions,
        ElDescriptionsItem,
        ElDialog,
        ElForm,
        ElFormItem,
        ElIcon,
        ElInput,
        ElInputNumber,
        ElOption,
        ElPagination,
        ElSelect,
        ElTable,
        ElTableColumn,
        ElTag
      },
      stubs: {
        ElDialog: {
          template: '<section><slot name="header" /><slot /><slot name="footer" /></section>'
        }
      },
      directives: { loading: ElLoading.directive }
    }
  })
}

describe('资产管理真实列表页', () => {
  beforeEach(() => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import'] } })
    listAssetAssignees.mockResolvedValue({ rows: [memberRow], total: 1, hasNext: false })
    getAssetPage.mockResolvedValue({ rows: [assetRow], total: 1, hasNext: false })
    getAssetDetail.mockResolvedValue({ data: assetDetail() })
    getAssetItems.mockReset().mockResolvedValue({ data: [assetItem] })
  })

  it('资产树表收起即汇总时间状态，展开仍按分项显示双时间', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-28T12:00:00'))
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, itemCount: 4, itemTimeGroups: [
      { taskStatus: 'in_progress', expectedEndTime: '2026-08-30T18:00:00', itemCount: 1 },
      { taskStatus: 'in_progress', expectedEndTime: '2026-08-29T12:00:00', itemCount: 1 },
      { taskStatus: 'in_progress', expectedEndTime: '2026-08-28T12:00:00', itemCount: 1 },
      { taskStatus: null, expectedEndTime: null, itemCount: 1 }
    ] }], total: 1, hasNext: false })
    getAssetItems.mockResolvedValue({ data: [
      { ...assetItem, task: { taskStatus: 'in_progress', expectedStartTime: '2026-08-28T09:30:00', expectedEndTime: '2026-08-30T18:00:00' } },
      { ...assetItem, assetItemId: 42, task: { taskStatus: 'in_progress', expectedStartTime: '2026-08-28T10:00:00', expectedEndTime: '2026-08-29T12:00:00' } },
      { ...assetItem, assetItemId: 43, task: { taskStatus: 'in_progress', expectedStartTime: '2026-08-27T09:00:00', expectedEndTime: '2026-08-28T12:00:00' } },
      { ...assetItem, assetItemId: 44, task: null }
    ] })
    let wrapper
    try {
      ;({ wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query']))
      expect(getAssetItems).not.toHaveBeenCalled()
      const parent = wrapper.find('.el-table__row--level-0')
      expect(parent.find('.task-expected-start').text()).toBe('—')
      expect(parent.find('.task-expected-end').text()).toBe('—')
      const summaryLabels = () => wrapper.findAll('.el-table__row--level-0 .task-time-state .el-tag').map(tag => tag.text())
      expect(summaryLabels()).toEqual(['已延期 1', '临近结束 1', '正常 1', '未设置时间 1'])
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const rows = wrapper.findAll('.el-table__row--level-1')
      expect(rows[0].find('.task-expected-start').text()).toBe('2026/08/28 09:30')
      expect(rows[0].find('.task-expected-end').text()).toBe('2026/08/30 18:00')
      expect(rows[1].find('.task-expected-start').text()).toBe('2026/08/28 10:00')
      expect(rows.map(row => row.find('.task-time-state').text())).toEqual(['正常', '临近结束', '已延期', '未设置时间'])
      expect(rows[3].find('.task-expected-start').text()).toBe('—')
      expect(rows[3].find('.task-expected-end').text()).toBe('—')
      expect(summaryLabels()).toEqual(['已延期 1', '临近结束 1', '正常 1', '未设置时间 1'])
      await wrapper.find('.el-table__expand-icon').trigger('click')
      expect(summaryLabels()).toEqual(['已延期 1', '临近结束 1', '正常 1', '未设置时间 1'])
    } finally { wrapper?.unmount(); vi.useRealTimers() }
  })

  it('父资产时间汇总随本地时钟和刷新更新，无分项显示横线且不预取子项', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date('2026-08-28T11:59:45'))
    const timedAsset = { ...assetRow, itemCount: 2, itemTimeGroups: [
      { taskStatus: 'in_progress', expectedEndTime: '2026-08-29T12:00:00', itemCount: 2 }
    ] }
    const emptyAsset = { ...assetRow, assetId: 32, assetName: '无分项资产', itemCount: 0, itemTimeGroups: [] }
    getAssetPage.mockResolvedValue({ rows: [timedAsset, emptyAsset], total: 2, hasNext: false })
    let wrapper
    try {
      ;({ wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query']))
      const cells = () => wrapper.findAll('.asset-data-table .el-table__row .task-time-state').map(cell => cell.text())
      expect(cells()).toEqual(['正常 2', '—'])
      await vi.advanceTimersByTimeAsync(30000)
      expect(cells()).toEqual(['临近结束 2', '—'])
      vi.setSystemTime(new Date('2026-08-29T12:00:00'))
      document.dispatchEvent(new Event('visibilitychange'))
      await flushPromises()
      expect(cells()).toEqual(['已延期 2', '—'])
      getAssetPage.mockResolvedValue({ rows: [{ ...timedAsset, itemTimeGroups: [
        { taskStatus: 'completed', expectedEndTime: '2026-08-29T12:00:00', itemCount: 2 }
      ] }, emptyAsset], total: 2, hasNext: false })
      await wrapper.findAll('button').find(button => buttonLabel(button) === '刷新').trigger('click')
      await flushPromises()
      expect(cells()).toEqual(['已完成 2', '—'])
      expect(getAssetItems).not.toHaveBeenCalled()
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper?.unmount(); vi.useRealTimers() }
  })

  it('树表父行保留资产描述，分项行只显示各自补充要求', async () => {
    getAssetItems.mockResolvedValue({ data: [assetItem, { ...assetItem, assetItemId: 42, productionItem: '反打视角', description: '反打补充要求' }] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const descriptions = wrapper.findAll('.el-table__row--level-1 .asset-description')
      expect(descriptions).toHaveLength(2)
      expect(wrapper.find('.el-table__row--level-0 .asset-description').text()).toContain(assetRow.description)
      for (const description of descriptions) expect(description.text()).not.toContain(assetRow.description)
      expect(descriptions[0].text()).toContain(`分项补充要求：${assetItem.description}`)
      expect(descriptions[1].text()).toContain('分项补充要求：反打补充要求')
    } finally { wrapper.unmount() }
  })

  it.each([
    { label: '编辑分项', component: AssetItemFormDialog },
    { label: '补齐制作分项', component: AssetItemFormDialog },
    { label: '分配任务', component: AssetAssignDialog },
    { label: '删除分项', component: AssetItemDeleteDialog }
  ])('树表子行的 $label 直接打开目标分项原有表单', async ({ label, component }) => {
    const target = { ...assetItem, assetItemId: 42, productionItem: label === '补齐制作分项' ? '' : '反打视角', assetStatus: 'unassigned', allowedActions: ['assetItem.edit', 'assetItem.delete', 'task.assign'] }
    getAssetItems.mockResolvedValue({ data: [assetItem, target] })
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), items: [assetItem, target] } })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:edit', 'shotgrid:asset:archive', 'shotgrid:task:assign'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const action = wrapper.findAll('.el-table__row--level-1')[1].findAll('button').find(button => buttonLabel(button) === label)
      expect(action).toBeDefined()
      expect(action.classes()).toContain('el-button--small')
      expect(action.attributes('aria-label')).toBe(label)
      expect(action.text()).toBe(label)
      expect(action.classes()).toContain('is-round')
      expect(action.classes()).toContain('is-plain')
      expect(action.classes().includes('is-dashed')).toBe(label === '补齐制作分项')
      await action.trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(component).props('item').assetItemId).toBe(42)
      expect(wrapper.findComponent(component).props('asset').assetId).toBe(31)
      expect(wrapper.findComponent(AssetDetailView).exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('树表补齐制作分项后刷新为编辑和分配入口', async () => {
    const incomplete = { ...assetItem, productionItem: '', assetStatus: 'unassigned', allowedActions: ['assetItem.edit'] }
    getAssetPage.mockImplementation(async () => ({ rows: [{ ...assetRow }], total: 1, hasNext: false }))
    getAssetItems.mockResolvedValue({ data: [incomplete] })
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), items: [incomplete] } })
    updateAssetItem.mockReset().mockImplementation(async () => {
      getAssetItems.mockResolvedValue({ data: [{ ...incomplete, productionItem: '舱室反打', allowedActions: ['assetItem.edit', 'task.assign'] }] })
      return { data: { ...incomplete, productionItem: '舱室反打' } }
    })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:edit', 'shotgrid:task:assign'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      await wrapper.find('.el-table__row--level-1').findAll('button').find(button => buttonLabel(button) === '补齐制作分项').trigger('click')
      await flushPromises()
      const dialog = wrapper.findComponent(AssetItemFormDialog)
      await dialog.findComponent(ElInput).setValue('舱室反打')
      await dialog.findAllComponents(ElButton).find(button => buttonLabel(button) === '保存分项').trigger('click')
      await flushPromises()
      expect(updateAssetItem).toHaveBeenCalledWith(8, 41, expect.objectContaining({ productionItem: '舱室反打', lockVersion: 0 }))
      expect(wrapper.findComponent(AssetItemFormDialog).exists()).toBe(false)
      expect(getAssetItems).toHaveBeenCalledTimes(2)
      const row = wrapper.find('.el-table__row--level-1')
      const labels = row.findAll('button').map(buttonLabel)
      expect(labels).toContain('编辑分项')
      expect(labels).toContain('分配任务')
      expect(labels).not.toContain('补齐制作分项')
    } finally { wrapper.unmount() }
  })

  it('树表分项操作在切换项目后中止并忽略迟到详情', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { ...projectRow, projectId: 9, projectName: '新项目' }], total: 2 })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:edit'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      let finish
      getAssetDetail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      await wrapper.find('.el-table__row--level-1').findAll('button').find(button => buttonLabel(button) === '编辑分项').trigger('click')
      const signal = getAssetDetail.mock.calls.at(-1)[2].signal
      await setElSelectValue(wrapper.find('.project-context').findComponent(ElSelect), '9')
      await flushPromises()
      finish({ data: assetDetail() })
      await flushPromises()
      expect(signal.aborted).toBe(true)
      expect(wrapper.findComponent(AssetItemFormDialog).exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('树表仅对选中分项确认开工，刷新后移除删除和开始入口', async () => {
    const target = { ...assetItem, lockVersion: 3, assetStatus: 'not_started', allowedActions: ['assetItem.delete', 'task.start', 'task.assign'], task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 } }
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, lockVersion: 2, allowedActions: ['task.start', 'asset.archive'] }], total: 1 })
    getAssetItems.mockResolvedValue({ data: [target] })
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), lockVersion: 2, allowedActions: ['task.start'], items: [target] } })
    startTask.mockReset().mockImplementation(async () => {
      getAssetItems.mockResolvedValue({ data: [{ ...target, assetStatus: 'preparing', allowedActions: [], task: { ...target.task, taskStatus: 'preparing', lockVersion: 5 } }] })
      getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, itemStatusCounts: { preparing: 1 }, allowedActions: [] }], total: 1 })
      return { data: { taskStatus: 'preparing' } }
    })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:task:start', 'shotgrid:task:assign', 'shotgrid:asset:archive'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const row = wrapper.find('.el-table__row--level-1')
      expect(row.findAll('button').map(buttonLabel)).toContain('改派任务')
      const button = row.findAll('button').find(item => buttonLabel(item) === '开始任务')
      expect(button).toBeDefined()
      await button.trigger('click')
      await flushPromises()
      await completeTaskStartForm(wrapper)
      expect(startTask).toHaveBeenCalledTimes(1)
      expect(startTask).toHaveBeenCalledWith(71, { lockVersion: 4, assetLockVersion: 2, assetItemLockVersion: 3, startConfirmed: true, ...expectedTaskTimes })
      expect(wrapper.find('.el-table__row--level-1').findAll('button').map(buttonLabel)).not.toContain('删除分项')
      expect(wrapper.find('.el-table__row--level-1').findAll('button').map(buttonLabel)).not.toContain('开始任务')
      expect(wrapper.find('.el-table__row--level-1').findAll('button').map(buttonLabel)).not.toContain('改派任务')
      expect(wrapper.find('.asset-row-actions').findComponent(ElDropdown).exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('树表动作重新读取分项权限，不能用旧的删除入口绕过已开工状态', async () => {
    getAssetItems.mockResolvedValue({ data: [{ ...assetItem, allowedActions: ['assetItem.delete'] }] })
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), items: [{ ...assetItem, allowedActions: [], task: { taskId: 71, taskStatus: 'in_progress' } }] } })
    deleteAssetItem.mockReset()
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:archive'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const button = wrapper.find('.el-table__row--level-1').findAll('button').find(item => buttonLabel(item) === '删除分项')
      expect(button).toBeDefined()
      await button.trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(AssetItemDeleteDialog).exists()).toBe(false)
      expect(deleteAssetItem).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it.each([
    { common: '同一段说明', item: '同一段说明', expected: '分项补充要求：同一段说明' },
    { common: '资产描述内容', item: '', expected: '—' },
    { common: '', item: '分项独有要求', expected: '分项补充要求：分项独有要求' },
    { common: '', item: '  ', expected: '—' }
  ])('树表分项说明仅展示补充要求，空值显示横线：$common / $item', async ({ common, item, expected }) => {
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, description: common }], total: 1 })
    getAssetItems.mockResolvedValue({ data: [{ ...assetItem, description: item }] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const cell = wrapper.find('.el-table__row--level-1 .asset-description')
      expect(cell.text()).toBe(expected)
      if (expected === '—') expect(cell.find('button').exists()).toBe(false)
      if (!common) expect(wrapper.find('.el-table__body-wrapper tr .asset-description').text()).toContain('暂无资产描述')
    } finally { wrapper.unmount() }
  })

  it('树表说明由原生文本组件截断，能展开全文并收起', async () => {
    const height = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function () {
      return this.classList.contains('asset-description-preview') ? 54 : 0
    })
    const scroll = vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function () {
      return this.classList.contains('asset-description-preview') ? 180 : 0
    })
    const fullDescription = '舱室共有说明。'.repeat(30)
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, description: fullDescription }], total: 1 })
    const { wrapper } = await mountList()
    try {
      const cell = wrapper.find('.asset-description')
      expect(cell.findComponent(ElText).exists()).toBe(true)
      expect(cell.findComponent(ElText).props('lineClamp')).toBe(3)
      await cell.find('button').trigger('click')
      expect(cell.findComponent(ElText).props('lineClamp')).toBeUndefined()
      expect(cell.text()).toContain(fullDescription)
      expect(cell.find('button').attributes('aria-expanded')).toBe('true')
      await cell.find('button').trigger('click')
      expect(cell.findComponent(ElText).props('lineClamp')).toBe(3)
    } finally { wrapper.unmount(); height.mockRestore(); scroll.mockRestore() }
  })

  it('树表概要将分项数放在名称旁、版本放在缩略图下，父级只显示状态汇总', async () => {
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, itemCount: 2, itemStatusCounts: { in_progress: 1, not_started: 1 } }], total: 1 })
    getAssetItems.mockResolvedValue({ data: [{ ...assetItem, latestVersion: { versionNo: 3 } }] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(wrapper.findAllComponents(ElTableColumn).map(column => column.props('label'))).not.toContain('分项 / 版本')
      expect(wrapper.find('.asset-identity').text()).toContain('2 个分项')
      expect(wrapper.find('.asset-status').findAllComponents(ElTag).map(tag => tag.text())).toEqual(['待开工 1', '制作中 1'])
      expect(wrapper.find('.asset-status-tag--not_started').text()).toBe('待开工 1')
      expect(wrapper.find('.asset-status-tag--in_progress').text()).toBe('制作中 1')
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1 .asset-thumbnail-cell').text()).toContain('V003')
      expect(wrapper.find('.el-table__row--level-1 .asset-status-tag').exists()).toBe(true)
    } finally { wrapper.unmount() }
  })

  it('树表父资产操作直接显示并打开对应资产编辑表单', async () => {
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:edit', 'shotgrid:asset:archive'])
    const theme = useThemeStore()
    const originalMode = theme.isDark
    try {
      const actions = wrapper.find('.asset-row-actions')
      expect(actions.findAll('button').map(buttonLabel)).toEqual(['详情', '编辑资产', '删除资产'])
      for (const button of actions.findAllComponents(ElButton)) {
        expect(button.props('size')).toBe('small')
        expect(button.attributes('aria-label')).toBeTruthy()
        expect(button.find('svg').exists()).toBe(true)
        expect(button.text()).toBe(button.attributes('aria-label'))
        expect(button.props('circle')).toBe(false)
        expect(button.props()).toMatchObject({ round: true, plain: true })
        expect(button.classes()).not.toContain('is-text')
      }
      theme.setDark(false)
      await flushPromises()
      expect(actions.findComponent(ElButton).props('dark')).toBe(false)
      theme.setDark(true)
      await flushPromises()
      expect(actions.findComponent(ElButton).props('dark')).toBe(true)
      expect(actions.findComponent(ElButton).element.style.getPropertyValue('--el-button-hover-text-color')).toBe('var(--sg-on-accent)')
      theme.setDark(originalMode)
      expect(actions.findAllComponents(ElButton).find(button => buttonLabel(button) === '删除资产').props('type')).toBe('danger')
      expect(actions.findComponent(ElDropdown).exists()).toBe(false)
      expect(actions.findComponent({ name: 'ElTooltip' }).exists()).toBe(false)
      await actions.findAll('button').find(button => buttonLabel(button) === '编辑资产').trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(AssetFormDialog).props('asset').assetId).toBe(31)
    } finally { theme.setDark(originalMode); wrapper.unmount() }
  })

  it('树表父资产删除仍经过确认，取消后不发送删除请求', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    archiveAsset.mockClear()
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:asset:archive'])
    try {
      const button = wrapper.find('.asset-row-actions').findAll('button').find(item => buttonLabel(item) === '删除资产')
      expect(button).toBeDefined()
      await button.trigger('click')
      await flushPromises()
      expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('动力舱室内'), '删除资产', expect.objectContaining({ cancelButtonText: '取消' }))
      expect(archiveAsset).not.toHaveBeenCalled()
    } finally { wrapper.unmount(); confirmSpy.mockRestore() }
  })

  it.each([false, true])('树表父资产写入口需要平台权限与服务端动作同时满足：平台有权限=%s', async hasWritePermission => {
    const permissions = ['shotgrid:asset:list', 'shotgrid:asset:query']
    if (hasWritePermission) {
      permissions.push('shotgrid:asset:edit', 'shotgrid:asset:archive')
      getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, allowedActions: [] }], total: 1 })
    }
    const { wrapper } = await mountList(permissions)
    try { expect(wrapper.find('.asset-row-actions').findAll('button').map(buttonLabel)).toEqual(['详情']) }
    finally { wrapper.unmount() }
  })

  it('树表首次展开才加载全部活动分项，父子主键不冲突且收起重开复用结果', async () => {
    let finishItems
    getAssetItems.mockImplementation(() => new Promise(resolve => { finishItems = resolve }))
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(getAssetItems).not.toHaveBeenCalled()
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      expect(wrapper.find('.el-table__expand-icon .is-loading').exists()).toBe(true)
      expect(getAssetItems).toHaveBeenCalledWith(8, 31, { signal: expect.any(AbortSignal) })
      finishItems({ data: [
        { ...assetItem, assetItemId: 31, task: { taskId: 51, assigneeUserId: 7, assigneeName: 'YJF', taskStatus: 'in_progress', lockVersion: 1 } },
        { ...assetItem, assetItemId: 42, productionItem: '舱门反打', description: '红色灯光', assetStatus: 'unassigned' },
        { ...assetItem, assetItemId: 43, productionItem: '旧稿', lifecycleStatus: 'archived' }
      ] })
      await flushPromises()
      const rows = wrapper.findAll('.el-table__body-wrapper tbody > tr')
      expect(rows).toHaveLength(3)
      expect(rows[1].text()).toContain('恐怖气氛主视角')
      expect(rows[1].text()).toContain('杨景锋')
      expect(rows[2].text()).toContain('舱门反打')
      expect(rows[2].text()).toContain('红色灯光')
      expect(rows[2].text()).toContain('待分配')
      expect(wrapper.find('.asset-table-wrap').text()).not.toContain('旧稿')
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(getAssetItems).toHaveBeenCalledTimes(1)
      expect(wrapper.findComponent(ElPagination).props('total')).toBe(1)
      getAssetDetail.mockResolvedValue({ data: {
        ...assetDetail(), items: [assetItem, { ...assetItem, assetItemId: 42, productionItem: '舱门反打' }]
      } })
      await rows[2].findAll('button').find(button => buttonLabel(button) === '分项详情').trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(AssetDetailView).props()).toMatchObject({ targetAssetId: 31, targetAssetItemId: 42 })
      expect(wrapper.findComponent(AssetDetailView).find('.item-card.is-targeted').text()).toContain('舱门反打')
      expect(startTask).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('树表使用标准选择列，全选只选择可操作父资产而不选择制作分项', async () => {
    getAssetPage.mockResolvedValue({ rows: [
      { ...assetRow, allowedActions: ['task.assign'] },
      { ...assetRow, assetId: 32, assetName: '不可操作资产', itemCount: 0, allowedActions: [] }
    ], total: 2 })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query', 'shotgrid:task:assign'])
    try {
      expect(wrapper.findAllComponents(ElTableColumn).some(column => column.props('type') === 'selection')).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      await wrapper.find('.el-table__header-wrapper input[type="checkbox"]').setValue(true)
      await vi.waitFor(() => expect(wrapper.findAll('.el-table__body-wrapper input[type="checkbox"]').filter(input => input.element.checked)).toHaveLength(1))
      expect(wrapper.text()).toContain('批量重新分配（1）')
      const child = wrapper.find('.el-table__row--level-1')
      expect(child.find('input[type="checkbox"]').element.disabled).toBe(true)
    } finally {
      wrapper.unmount()
    }
  })

  it('树表分项加载失败显示错误并能重试，不把失败伪装为无分项', async () => {
    getAssetItems.mockRejectedValueOnce({ httpStatus: 503, message: '分项服务暂不可用' }).mockResolvedValueOnce({ data: [assetItem] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(wrapper.find('.asset-table-wrap').text()).toContain('分项服务暂不可用')
      await wrapper.findAll('button').find(button => buttonLabel(button) === '重试分项').trigger('click')
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('恐怖气氛主视角')
      expect(wrapper.find('.asset-table-wrap').text()).not.toContain('分项服务暂不可用')
    } finally {
      wrapper.unmount()
    }
  })

  it('树表切换项目后中止分项查询并丢弃迟到结果', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectName: '新项目' }] })
    let finishItems
    getAssetItems.mockImplementation(() => new Promise(resolve => { finishItems = resolve }))
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      const signal = getAssetItems.mock.calls[0][2].signal
      getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, projectId: 9, assetId: 99, assetName: '新资产' }], total: 1 })
      await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '9')
      await flushPromises()
      expect(signal.aborted).toBe(true)
      finishItems({ data: [{ ...assetItem, productionItem: '旧项目迟到分项' }] })
      await flushPromises()
      expect(wrapper.find('.asset-table-wrap').text()).toContain('新资产')
      expect(wrapper.find('.asset-table-wrap').text()).not.toContain('旧项目迟到分项')
    } finally {
      wrapper.unmount()
    }
  })

  it('树表无查询权限时不请求分项，空分项结果不留下加载状态', async () => {
    const restricted = await mountList(['shotgrid:asset:list'])
    expect(restricted.wrapper.find('.el-table__expand-icon').exists()).toBe(false)
    expect(getAssetItems).not.toHaveBeenCalled()
    restricted.wrapper.unmount()
    getAssetItems.mockResolvedValue({ data: [] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(wrapper.find('.asset-table-wrap').text()).toContain('暂无活动分项')
      expect(wrapper.find('.el-table__expand-icon .is-loading').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('树表刷新保留展开并重读分项，筛选变化清理旧分项缓存', async () => {
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(true)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      const scrollElement = wrapper.find('.el-table__body-wrapper .el-scrollbar__wrap').element
      scrollElement.scrollTop = 90
      scrollElement.scrollLeft = 60
      getAssetPage.mockResolvedValue({ rows: [{ ...assetRow }], total: 1 })
      getAssetItems.mockResolvedValue({ data: [{ ...assetItem, productionItem: '刷新后的分项', assetStatus: 'completed' }] })
      await wrapper.findAll('button').find(button => buttonLabel(button) === '刷新').trigger('click')
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('刷新后的分项')
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('已完成')
      expect(getAssetItems).toHaveBeenCalledTimes(2)
      expect(wrapper.find('.el-table__body-wrapper .el-scrollbar__wrap').element.scrollTop).toBe(90)
      expect(wrapper.find('.el-table__body-wrapper .el-scrollbar__wrap').element.scrollLeft).toBe(60)
      await wrapper.find('.asset-filters').findComponent(ElInput).setValue('新筛选')
      await wrapper.findAll('button').find(button => buttonLabel(button) === '查询').trigger('click')
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').exists()).toBe(false)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(getAssetItems).toHaveBeenCalledTimes(3)
    } finally {
      wrapper.unmount()
    }
  })

  it('树表分项拒绝访问后不随列表轮询重复请求，人工刷新才重新尝试', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getAssetPage.mockImplementation(() => Promise.resolve({ rows: [{ ...assetRow, itemStatusCounts: { not_started: 1 } }], total: 1 }))
    getAssetItems.mockRejectedValue({ httpStatus: 403, message: '分项访问已收回' })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(wrapper.find('.asset-table-wrap').text()).toContain('分项访问已收回')
      expect(getAssetItems).toHaveBeenCalledTimes(1)
      await wrapper.findAll('button').find(button => buttonLabel(button) === '刷新').trigger('click')
      await flushPromises()
      expect(getAssetItems).toHaveBeenCalledTimes(2)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('树表慢分项请求跨过两轮轮询仍能完成，轮询不反复中止加载', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getAssetPage.mockImplementation(() => Promise.resolve({ rows: [{ ...assetRow, itemStatusCounts: { preparing: 1 } }], total: 1 }))
    let finishItems
    getAssetItems.mockImplementationOnce(() => new Promise(resolve => { finishItems = resolve })).mockResolvedValue({ data: [assetItem] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      const signal = getAssetItems.mock.calls[0][2].signal
      await vi.advanceTimersByTimeAsync(3500)
      expect(signal.aborted).toBe(false)
      expect(getAssetItems).toHaveBeenCalledTimes(1)
      finishItems({ data: [assetItem] })
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('恐怖气氛主视角')
      expect(getAssetPage).toHaveBeenCalledTimes(2)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('树表后台更新分项时保留缩略图预览，不重建整表或重复下载相同图片', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:tree-thumbnail') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const thumbnail = { fileId: 'thumb-1', name: '缩略图', url: '/shot-grid/versions/1/files/thumb-1/download' }
    downloadAssetThumbnail.mockResolvedValue(new Blob(['image']))
    getAssetPage.mockImplementation(() => Promise.resolve({ rows: [{ ...assetRow, thumbnail, itemStatusCounts: { preparing: 1 } }], total: 1 }))
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      await wrapper.find('.asset-thumbnail img').trigger('click')
      await flushPromises()
      expect(document.querySelector('.el-image-viewer__wrapper')).not.toBeNull()
      getAssetItems.mockResolvedValue({ data: [{ ...assetItem, productionItem: '后台更新分项' }] })
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('后台更新分项')
      expect(document.querySelector('.el-image-viewer__wrapper')).not.toBeNull()
      expect(downloadAssetThumbnail).toHaveBeenCalledTimes(1)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('树表后台刷新能加载原空分支，最后一个分项移除后清理旧子行', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getAssetPage.mockImplementation(() => Promise.resolve({ rows: [{ ...assetRow, itemStatusCounts: { preparing: 1 } }], total: 1 }))
    getAssetItems.mockResolvedValueOnce({ data: [] }).mockResolvedValue({ data: [assetItem] })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await wrapper.find('.el-table__expand-icon').trigger('click')
      await flushPromises()
      expect(wrapper.find('.asset-table-wrap').text()).toContain('暂无活动分项')
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').text()).toContain('恐怖气氛主视角')
      getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, itemCount: 0, itemStatusCounts: {} }], total: 1 })
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').exists()).toBe(false)
      expect(getAssetItems).toHaveBeenCalledTimes(2)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it.each(['失去操作权限', '离开当前分页'])('树表后台刷新剔除%s的旧勾选', async change => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const selectableAsset = { ...assetRow, assetStatus: 'not_started', allowedActions: ['task.assign'], itemStatusCounts: { not_started: 1 } }
    getAssetPage.mockResolvedValueOnce({ rows: [selectableAsset], total: 1 }).mockResolvedValue({
      rows: [change === '失去操作权限' ? { ...selectableAsset, allowedActions: [] } : { ...selectableAsset, assetId: 32 }], total: 1
    })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:task:assign'])
    try {
      await wrapper.find('.el-table__body-wrapper input[type="checkbox"]').setValue(true)
      await flushPromises()
      expect(wrapper.text()).toContain('批量重新分配（1）')
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(wrapper.find('.el-table__body-wrapper input[type="checkbox"]').element.checked).toBe(false)
      expect(wrapper.text()).not.toContain('批量重新分配（1）')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it.each(['分项全部移除', '父资产离开当前页'])('树表在父请求期间展开，%s后取消新分项请求并忽略迟到响应', async change => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    let finishPage
    let finishItems
    getAssetPage.mockResolvedValueOnce({ rows: [{ ...assetRow, itemStatusCounts: { preparing: 1 } }], total: 1 })
      .mockImplementationOnce(() => new Promise(resolve => { finishPage = resolve }))
    getAssetItems.mockImplementationOnce(() => new Promise(resolve => { finishItems = resolve }))
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:asset:query'])
    try {
      await vi.advanceTimersByTimeAsync(1500)
      await wrapper.find('.el-table__expand-icon').trigger('click')
      const signal = getAssetItems.mock.calls[0][2].signal
      finishPage({ rows: [{ ...assetRow, assetId: change === '父资产离开当前页' ? 32 : 31, itemCount: 0, itemStatusCounts: {} }], total: 1 })
      await flushPromises()
      expect(signal.aborted).toBe(true)
      finishItems({ data: [assetItem] })
      await flushPromises()
      expect(wrapper.find('.el-table__row--level-1').exists()).toBe(false)
      expect(wrapper.find('.el-table__expand-icon').exists()).toBe(false)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('展示真实资产结果、四类筛选、分页与三种视图', async () => {
    const { wrapper } = await mountList()
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('asset-filters'))
    expect(filterForm.props('model')).toMatchObject({ keyword: '', assetType: '', assetStatus: '', assigneeUserId: '' })
    expect(filterForm.props('rules')).toHaveProperty('keyword')
    expect(filterForm.findAllComponents(ElFormItem)).toHaveLength(5)
    expect(filterForm.findComponent(ElInput).classes()).toContain('sg-input')
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')
    expect(wrapper.text()).toContain('动力舱室内')
    expect(wrapper.text()).toContain('1个资产')
    expect(wrapper.find('.asset-table-wrap').text()).toContain('杨景锋')
    expect(wrapper.text()).toContain('导入 Excel')
    expect(wrapper.text()).toContain('新建资产')
    const tableTags = wrapper.find('.asset-table-wrap').findAllComponents(ElTag)
    expect(tableTags.find(tag => tag.text() === '场景')?.props('type')).toBe('primary')
    const productionStatusTag = tableTags.find(tag => tag.text() === '制作中')
    expect(productionStatusTag.props()).toMatchObject({ type: 'primary', effect: 'light', round: true })
    expect(productionStatusTag.classes()).toContain('asset-status-tag--in_progress')
    expect(wrapper.find('.asset-table-wrap').text()).not.toContain('目录已就绪')
    const tableColumns = wrapper.findAllComponents(ElTableColumn)
    const rightFixedColumns = tableColumns.filter(column => column.props('fixed') === 'right')
    expect(rightFixedColumns.map(column => column.props('label'))).toEqual(['时间状态', '制作人', '状态', '操作'])
    expect(tableColumns.slice(-3).map(column => column.props('label'))).toEqual(['制作人', '状态', '操作'])

    const filterSelects = wrapper.find('.asset-filters').findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], 'Environment')
    await setElSelectValue(filterSelects[1], 'in_progress')
    await setElSelectValue(filterSelects[2], '7')
    const queryButton = filterForm.findAllComponents(ElButton).find(button => buttonLabel(button) === '查询')
    expect(queryButton.props('nativeType')).toBe('button')
    await queryButton.trigger('click')
    await flushPromises()
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({
      assetType: 'Environment',
      assetStatus: 'in_progress',
      assigneeUserId: '7'
    }), expect.anything())

    const viewSwitch = wrapper.findComponent(ElRadioGroup)
    viewSwitch.vm.$emit('update:modelValue', 'card')
    await flushPromises()
    expect(wrapper.find('.asset-card').exists()).toBe(true)
    viewSwitch.vm.$emit('update:modelValue', 'type')
    await flushPromises()
    expect(wrapper.find('.type-board').text()).toContain('场景')
    expect(wrapper.find('.type-board__asset').findAllComponents(ElTag).map(tag => tag.text())).toEqual(['制作中'])
    wrapper.unmount()
  })

  it.each([
    { status: 'unassigned', counts: { unassigned: 6 }, labels: ['待分配 6'] },
    { status: 'in_progress', counts: { not_started: 4, in_progress: 2 }, labels: ['待开工 4', '制作中 2'] }
  ])('类型看板按分项计数展示状态，不重复聚合状态：$status', async ({ status, counts, labels }) => {
    getAssetPage.mockResolvedValue({ rows: [{ ...assetRow, assetStatus: status, itemCount: 6, itemStatusCounts: counts }], total: 1 })
    const { wrapper, router } = await mountList()
    try {
      wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', 'type')
      await flushPromises()
      const card = wrapper.find('.type-board__asset')
      expect(card.text()).toContain(assetRow.assetName)
      expect(card.text()).toContain('6 个制作分项')
      expect(card.findAllComponents(ElTag).map(tag => tag.text())).toEqual(labels)
      await card.trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(AssetDetailView).exists()).toBe(true)
      expect(router.currentRoute.value.path).toBe('/assets')
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it('资产下拉筛选 change 后立即查询第一页', async () => {
    const { wrapper } = await mountList()
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('asset-filters'))
    const filterSelects = filterForm.findAllComponents({ name: 'ElSelect' })
    getAssetPage.mockClear()

    await setElSelectValue(filterSelects[0], 'Environment')
    await flushPromises()
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ assetType: 'Environment', pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[1], 'in_progress')
    await flushPromises()
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ assetType: 'Environment', assetStatus: 'in_progress', pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[2], '7')
    await flushPromises()
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ assetType: 'Environment', assetStatus: 'in_progress', assigneeUserId: '7', pageNum: 1 }), expect.anything())
    wrapper.unmount()
  })

  it('通过 Element Plus Form 重置全部资产筛选并重新查询第一页', async () => {
    const { wrapper } = await mountList()
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('asset-filters'))
    await filterForm.find('input[aria-label="按资产名称或描述搜索"]').setValue('动力舱')
    const filterSelects = filterForm.findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], 'Environment')
    await setElSelectValue(filterSelects[1], 'in_progress')
    await setElSelectValue(filterSelects[2], '7')
    getAssetPage.mockClear()

    await filterForm.findAllComponents(ElButton).find(button => buttonLabel(button) === '重置').trigger('click')
    await flushPromises()

    expect(filterForm.props('model')).toMatchObject({ keyword: '', assetType: '', assetStatus: '', assigneeUserId: '', pageNum: 1 })
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({
      keyword: undefined,
      assetType: undefined,
      assetStatus: undefined,
      assigneeUserId: undefined,
      pageNum: 1
    }), expect.anything())
    wrapper.unmount()
  })

  it('点击详情在当前列表页右侧抽屉展示完整资产详情', async () => {
    const { wrapper, router } = await mountList()
    await wrapper.findAll('button').find(button => buttonLabel(button) === '详情').trigger('click')
    await flushPromises()

    const detail = wrapper.findComponent(AssetDetailView)
    expect(detail.exists()).toBe(true)
    expect(detail.props()).toMatchObject({ embedded: true, targetProjectId: 8, targetAssetId: 31 })
    expect(detail.text()).toContain('动力舱室内')
    const itemDescription = detail.find('.item-card .asset-description').text()
    expect(itemDescription).toContain(`资产描述：${assetRow.description}`)
    expect(itemDescription).toContain(`分项补充要求：${assetItem.description}`)
    expect(router.currentRoute.value.path).toBe('/assets')
    wrapper.unmount()
  })

  it('403 分流为权限错误而不是空资产列表', async () => {
    getAssetPage.mockRejectedValue({ httpStatus: 403, message: '不是项目成员' })
    const { wrapper } = await mountList(['shotgrid:asset:list'])
    expect(wrapper.text()).toContain('没有资产访问权限')
    expect(wrapper.text()).toContain('不是项目成员')
    expect(wrapper.text()).not.toContain('当前筛选没有资产')
    wrapper.unmount()
  })

  it('创建与导入入口同时受项目 allowedActions 和 session permission 约束', async () => {
    getProjectDetail.mockResolvedValue({ data: {
      ...projectRow,
      projectTypeName: 'AI 影视短片',
      aspectRatio: '16:9',
      projectStatus: 'active',
      storageStatus: 'ready',
      myProjectRole: 'director',
      allowedActions: []
    } })
    const { wrapper } = await mountList()
    const buttons = wrapper.findAll('button').map(buttonLabel)
    expect(buttons).not.toContain('新建资产')
    expect(buttons).not.toContain('导入 Excel')
    wrapper.unmount()
  })

  it('项目范围请求迟到时不能覆盖当前范围项目列表', async () => {
    let resolveAllScope
    getProjectPage.mockImplementation(params => {
      if (params.scope === 'all') {
        return new Promise(resolve => { resolveAllScope = resolve })
      }
      return Promise.resolve({ rows: [projectRow], total: 1, hasNext: false })
    })
    const { wrapper } = await mountList([
      'shotgrid:project:all',
      'shotgrid:asset:list',
      'shotgrid:asset:add',
      'shotgrid:asset:import'
    ])
    const scopeSelect = wrapper.find('.project-context').findAllComponents({ name: 'ElSelect' })[1]

    await setElSelectValue(scopeSelect, 'all')
    await setElSelectValue(scopeSelect, '')
    await flushPromises()
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')

    resolveAllScope({
      rows: [{ projectId: 9, projectCode: 'STALE', projectName: '迟到旧范围项目' }],
      total: 1,
      hasNext: false
    })
    await flushPromises()
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')
    expect(wrapper.text()).not.toContain('迟到旧范围项目')
    wrapper.unmount()
  })

  it('同一项目切走再返回重开后，旧创建完成事件不能关闭新实例或刷新', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      projectId,
      projectCode: projectId === 8 ? 'LCFR' : 'NEW',
      projectName: projectId === 8 ? '罗刹夫人' : '新项目',
      projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import']
    } }))
    const { wrapper } = await mountList()
    const switchProject = async id => {
      await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), String(id))
      await flushPromises()
    }

    await wrapper.findAll('button').find(button => button.text().includes('新建资产')).trigger('click')
    const oldDialog = wrapper.findComponent(AssetFormDialog)
    const oldGeneration = oldDialog.props('operationGeneration')
    await switchProject(9)
    await switchProject(8)
    await wrapper.findAll('button').find(button => button.text().includes('新建资产')).trigger('click')
    const newDialog = wrapper.findComponent(AssetFormDialog)
    const callsBefore = getAssetPage.mock.calls.length
    expect(newDialog.props('operationGeneration')).not.toBe(oldGeneration)

    oldDialog.vm.$emit('saved', { assetId: 99 }, { projectId: 8, assetId: null, operationGeneration: oldGeneration })
    await flushPromises()
    expect(wrapper.findComponent(AssetFormDialog).exists()).toBe(true)
    expect(wrapper.findComponent(AssetFormDialog).props('operationGeneration')).toBe(newDialog.props('operationGeneration'))
    expect(getAssetPage).toHaveBeenCalledTimes(callsBefore)
    wrapper.unmount()
  })

  it.each(['table', 'card', 'type'])('%s 视图的父资产入口只打开详情供选择分项，不直接开始任务', async viewMode => {
    getAssetPage.mockResolvedValue({ rows: [{
      ...assetRow,
      allowedActions: [...assetRow.allowedActions, 'task.start'],
      itemStatusCounts: { not_started: 1, in_progress: 1 }
    }], total: 1, hasNext: false })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:task:start'])
    try {
      wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', viewMode)
      await flushPromises()
      const entry = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '选择分项开工')
      expect(entry).toBeDefined()
      await entry.trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(AssetDetailView).exists()).toBe(true)
      expect(startTask).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('待开工 1')
      expect(wrapper.text()).toContain('制作中 1')
    } finally {
      wrapper.unmount()
    }
  })

  it('列表按分项目录准备状态自动刷新并在结束后停止', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getAssetPage.mockResolvedValueOnce({ rows: [{
      ...assetRow, allowedActions: ['asset.edit'], itemStatusCounts: { preparing: 1 }
    }], total: 1, hasNext: false }).mockResolvedValueOnce({ rows: [{
      ...assetRow, allowedActions: ['asset.edit'], itemStatusCounts: { in_progress: 1 }
    }], total: 1, hasNext: false })
    const { wrapper } = await mountList(['shotgrid:asset:list', 'shotgrid:task:assign'])
    try {
      const calls = getAssetPage.mock.calls.length
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(getAssetPage).toHaveBeenCalledTimes(calls + 1)
      expect(wrapper.text()).toContain('制作中 1')
      expect(wrapper.find('.el-table__body-wrapper input[type="checkbox"]').element.disabled).toBe(true)
      await vi.advanceTimersByTimeAsync(5000)
      expect(getAssetPage).toHaveBeenCalledTimes(calls + 1)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })
})

describe('资产详情动作镜像与路由隔离', () => {
  beforeEach(() => {
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import'] } })
    listAssetAssignees.mockResolvedValue({ rows: [memberRow], total: 1, hasNext: false })
    getAssetDetail.mockResolvedValue({ data: assetDetail() })
    startTask.mockReset()
  })

  it('资产详情显示每个分项自己的预期时间范围，无任务不显示任务时间', async () => {
    getAssetDetail.mockResolvedValueOnce({ data: {
      ...assetDetail(),
      items: [
        { ...assetItem, task: { taskStatus: 'in_progress', priority: 'normal', expectedStartTime: '2099-09-01T09:30:00', expectedEndTime: '2099-09-04T18:00:00' } },
        { ...assetItem, assetItemId: 42, productionItem: '反打视角', task: { taskStatus: 'in_progress', priority: 'normal', expectedStartTime: '2099-09-05T10:00:00', expectedEndTime: '2099-09-06T20:00:00' } },
        { ...assetItem, assetItemId: 43, productionItem: '未分配分项', task: null }
      ]
    } })
    const { wrapper } = await mountDetail()
    try {
      const cards = wrapper.findAll('.item-card')
      expect(cards[0].text()).toContain('预期制作时间')
      expect(cards[0].text()).toContain('2099/09/01 09:30')
      expect(cards[0].text()).toContain('2099/09/04 18:00')
      expect(cards[1].text()).toContain('2099/09/05 10:00')
      expect(cards[1].text()).toContain('2099/09/06 20:00')
      expect(cards[1].text()).not.toContain('2099/09/01')
      expect(cards[2].find('[aria-label="时间提醒"]').exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('管理员只在允许的制作分项确认开工，使用三份锁版本且不联动其他分项', async () => {
    getAssetDetail.mockResolvedValue({ data: {
      ...assetDetail(),
      lockVersion: 2,
      allowedActions: ['task.start'],
      items: [
        {
          ...assetItem,
          lockVersion: 3,
          allowedActions: ['task.start'],
          task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
        },
        {
          ...assetItem,
          assetItemId: 42,
          productionItem: '不应联动的反打视角',
          allowedActions: [],
          task: { taskId: 72, lockVersion: 5, taskStatus: 'not_started', assigneeUserId: 7 }
        }
      ]
    } })
    startTask.mockResolvedValue({ data: { taskId: 71, taskStatus: 'preparing' } })
    const { wrapper } = await mountDetail('/projects/8/assets/31', ['shotgrid:task:start'])
    try {
      const startButton = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '开始任务')
      expect(startButton).toBeDefined()
      expect(startButton.props('size')).toBe('small')
      await startButton.trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain('动力舱室内')
      expect(wrapper.text()).toContain('恐怖气氛主视角')
      expect(wrapper.text()).toContain('杨景锋')
      await completeTaskStartForm(wrapper)
      expect(startTask).toHaveBeenCalledTimes(1)
      expect(startTask).toHaveBeenCalledWith(71, {
        lockVersion: 4,
        assetLockVersion: 2,
        assetItemLockVersion: 3,
        startConfirmed: true, ...expectedTaskTimes
      })
      expect(startTask).not.toHaveBeenCalledWith(72, expect.anything())
    } finally {
      wrapper.unmount()
    }
  })

  it.each(['platform', 'parent', 'item'])('缺少 %s 开工授权时不显示制作分项开始按钮', async missing => {
    getAssetDetail.mockResolvedValue({ data: {
      ...assetDetail(),
      allowedActions: missing === 'parent' ? [] : ['task.start'],
      items: [{
        ...assetItem,
        allowedActions: missing === 'item' ? [] : ['task.start'],
        task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
      }]
    } })
    const { wrapper } = await mountDetail('/projects/8/assets/31', missing === 'platform' ? [] : ['shotgrid:task:start'])
    try {
      expect(wrapper.findAllComponents(ElButton).map(buttonLabel)).not.toContain('开始任务')
    } finally {
      wrapper.unmount()
    }
  })

  it('取消制作分项开工确认后不调用开始接口', async () => {
    getAssetDetail.mockResolvedValue({ data: {
      ...assetDetail(), lockVersion: 2, allowedActions: ['task.start'], items: [{
        ...assetItem, lockVersion: 3, allowedActions: ['task.start'],
        task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
      }]
    } })
    const { wrapper } = await mountDetail('/projects/8/assets/31', ['shotgrid:task:start'])
    try {
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '开始任务').trigger('click')
      await flushPromises()
      await completeTaskStartForm(wrapper, 'cancel')
      expect(startTask).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('自动刷新待开工分项，更新后停止轮询且保留当前详情', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getAssetDetail.mockResolvedValueOnce({ data: {
      ...assetDetail(), itemStatusCounts: { not_started: 1 }, items: [{
        ...assetItem, assetStatus: 'not_started', task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
      }]
    } }).mockResolvedValueOnce({ data: {
      ...assetDetail(), itemStatusCounts: { in_progress: 1 }, items: [{
        ...assetItem, assetStatus: 'in_progress', task: { taskId: 71, lockVersion: 5, taskStatus: 'in_progress', assigneeUserId: 7 }
      }]
    } })
    const { wrapper } = await mountDetail()
    try {
      const calls = getAssetDetail.mock.calls.length
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(getAssetDetail).toHaveBeenCalledTimes(calls + 1)
      expect(wrapper.text()).toContain('制作中')
      await vi.advanceTimersByTimeAsync(10000)
      expect(getAssetDetail).toHaveBeenCalledTimes(calls + 1)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('普通刷新保留资产草稿与打开时旧锁，不能用新锁提交旧稿', async () => {
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), lockVersion: 2 } })
    updateAsset.mockReset().mockRejectedValue({ httpStatus: 409, message: '资产已被他人修改' })
    const { wrapper } = await mountDetail()
    try {
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '编辑资产').trigger('click')
      const dialog = wrapper.findComponent(AssetFormDialog)
      const description = dialog.findAllComponents(ElFormItem).find(item => item.props('prop') === 'description')
      await description.get('textarea').setValue('尚未提交的资产说明')
      getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), lockVersion: 6, description: '他人更新后的资产说明' } })
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '刷新').trigger('click')
      await flushPromises()
      const refreshedDialog = wrapper.findComponent(AssetFormDialog)
      expect(refreshedDialog.exists()).toBe(true)
      expect(wrapper.find('.asset-hero__main').text()).toContain('他人更新后的资产说明')
      expect(refreshedDialog.findAllComponents(ElFormItem).find(item => item.props('prop') === 'description').get('textarea').element.value).toBe('尚未提交的资产说明')
      await refreshedDialog.findAllComponents(ElButton).find(button => buttonLabel(button) === '保存资产').trigger('click')
      await flushPromises()
      expect(updateAsset).toHaveBeenCalledWith(8, 31, {
        description: '尚未提交的资产说明', sortOrder: 10, remark: '保持冷蓝色调', lockVersion: 2
      })
    } finally {
      wrapper.unmount()
    }
  })

  it.each([
    { entry: '编辑资产', component: AssetFormDialog, submitLabel: '保存资产', api: updateAsset, targetId: 31, field: 'description', refreshedValue: '最新资产说明', lockField: 'lockVersion', oldLock: 2, newLock: 6 },
    { entry: '编辑分项', component: AssetItemFormDialog, submitLabel: '保存分项', api: updateAssetItem, targetId: 41, field: 'description', refreshedValue: '最新分项说明', lockField: 'lockVersion', oldLock: 3, newLock: 7 },
    { entry: '改派任务', component: AssetAssignDialog, submitLabel: '确认改派', api: assignAssetItemTask, targetId: 41, field: 'taskDescription', refreshedValue: '最新任务要求', lockField: 'taskLockVersion', oldLock: 4, newLock: 8 },
    { entry: '删除分项', component: AssetItemDeleteDialog, submitLabel: '确认删除', api: deleteAssetItem, targetId: 41, field: 'reason', refreshedValue: '', lockField: 'lockVersion', oldLock: 3, newLock: 7 },
    { entry: '归档资产', component: AssetArchiveDialog, submitLabel: '确认归档', api: archiveAsset, targetId: 31, field: 'reason', refreshedValue: '', lockField: 'lockVersion', oldLock: 2, newLock: 6 },
    { entry: '归档分项', component: AssetArchiveDialog, submitLabel: '确认归档', api: archiveAssetItem, targetId: 41, field: 'reason', refreshedValue: '', lockField: 'lockVersion', oldLock: 3, newLock: 7 }
  ])('$entry 发生 409 后刷新会关闭旧上下文，重新核对后使用新快照', async ({ entry, component, submitLabel, api, targetId, field, refreshedValue, lockField, oldLock, newLock }) => {
    const detail = {
      ...assetDetail(), lockVersion: 2, items: [{
        ...assetItem, lockVersion: 3,
        allowedActions: entry === '删除分项' ? ['assetItem.delete'] : assetItem.allowedActions,
        task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7, requirements: '原任务要求', priority: 'normal' }
      }]
    }
    getAssetDetail.mockResolvedValue({ data: detail })
    api.mockReset().mockRejectedValue({ httpStatus: 409, message: '数据已被他人修改，请重新核对' })
    const { wrapper } = await mountDetail()
    try {
      const actionButton = (container, label) => container.findAllComponents(ElButton).find(button => buttonLabel(button) === label)
      await actionButton(wrapper, entry).trigger('click')
      const oldDialog = wrapper.findComponent(component)
      const oldGeneration = oldDialog.props('operationGeneration')
      const oldField = oldDialog.findAllComponents(ElFormItem).find(item => item.props('prop') === field)
      await oldField.get('textarea').setValue('旧上下文中的草稿')
      await actionButton(oldDialog, submitLabel).trigger('click')
      await flushPromises()
      expect(api).toHaveBeenCalledTimes(1)
      expect(api).toHaveBeenLastCalledWith(8, targetId, expect.objectContaining({ [field]: '旧上下文中的草稿', [lockField]: oldLock }))

      let resolveRefresh
      getAssetDetail.mockImplementationOnce(() => new Promise(resolve => { resolveRefresh = resolve }))
      await actionButton(oldDialog, '刷新后重试').trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(component).exists()).toBe(false)
      expect(wrapper.findAllComponents(ElButton).some(button => buttonLabel(button) === submitLabel)).toBe(false)
      expect(api).toHaveBeenCalledTimes(1)

      resolveRefresh({ data: {
        ...detail, lockVersion: 6, description: '最新资产说明', items: [{
          ...detail.items[0], lockVersion: 7, description: '最新分项说明',
          task: { ...detail.items[0].task, lockVersion: 8, requirements: '最新任务要求' }
        }]
      } })
      await flushPromises()
      expect(wrapper.findComponent(component).exists()).toBe(false)
      expect(api).toHaveBeenCalledTimes(1)
      await actionButton(wrapper, entry).trigger('click')
      const newDialog = wrapper.findComponent(component)
      expect(newDialog.props('operationGeneration')).not.toBe(oldGeneration)
      const newField = newDialog.findAllComponents(ElFormItem).find(item => item.props('prop') === field)
      expect(newField.get('textarea').element.value).toBe(refreshedValue)
      if (field === 'reason') await newField.get('textarea').setValue('重新核对后的操作原因')
      await actionButton(newDialog, submitLabel).trigger('click')
      await flushPromises()
      expect(api).toHaveBeenCalledTimes(2)
      expect(api).toHaveBeenLastCalledWith(8, targetId, expect.objectContaining({
        [field]: field === 'reason' ? '重新核对后的操作原因' : refreshedValue,
        [lockField]: newLock
      }))
    } finally {
      wrapper.unmount()
    }
  })

  it('开工成功后详情刷新未结束时发生 ABA，不发出旧 changed 事件', async () => {
    const initial = {
      ...assetDetail(), lockVersion: 2, allowedActions: ['task.start'], items: [{
        ...assetItem, lockVersion: 3, allowedActions: ['task.start'],
        task: { taskId: 71, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
      }]
    }
    getAssetDetail.mockResolvedValue({ data: initial })
    startTask.mockResolvedValue({ data: { taskId: 71, taskStatus: 'preparing' } })
    const { wrapper, router } = await mountDetail('/projects/8/assets/31', ['shotgrid:task:start'])
    try {
      let resolveOldRefresh
      getAssetDetail.mockImplementationOnce(() => new Promise(resolve => { resolveOldRefresh = resolve }))
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '开始任务').trigger('click')
      await flushPromises()
      await completeTaskStartForm(wrapper)
      expect(startTask).toHaveBeenCalledTimes(1)
      expect(getAssetDetail).toHaveBeenCalledTimes(2)
      getAssetDetail.mockImplementation((targetProjectId, targetAssetId) => Promise.resolve({ data: assetDetail(targetProjectId, targetAssetId, targetAssetId === 31 ? '返回后的当前资产' : '中转资产') }))
      await router.push('/projects/8/assets/32')
      await flushPromises()
      await router.push('/projects/8/assets/31')
      await flushPromises()
      expect(wrapper.text()).toContain('返回后的当前资产')
      resolveOldRefresh({ data: { ...initial, description: '不应显示的旧刷新结果' } })
      await flushPromises()
      expect(wrapper.text()).not.toContain('不应显示的旧刷新结果')
      expect(wrapper.emitted('changed')).toBeUndefined()
    } finally {
      wrapper.unmount()
    }
  })

  it('切换资产后迟到的开工确认不提交旧分项任务', async () => {
    getAssetDetail.mockImplementation((targetProjectId, targetAssetId) => Promise.resolve({ data: {
      ...assetDetail(targetProjectId, targetAssetId, targetAssetId === 31 ? '原资产' : '新资产'), lockVersion: 2,
      allowedActions: ['task.start'], items: [{
        ...assetItem, assetId: targetAssetId, lockVersion: 3, allowedActions: ['task.start'],
        task: { taskId: targetAssetId === 31 ? 71 : 72, lockVersion: 4, taskStatus: 'not_started', assigneeUserId: 7 }
      }]
    } }))
    const { wrapper, router } = await mountDetail('/projects/8/assets/31', ['shotgrid:task:start'])
    try {
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '开始任务').trigger('click')
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '开始任务').trigger('click')
      const oldDialog = wrapper.findComponent({ name: 'TaskStartDialog' })
      expect(oldDialog.exists()).toBe(true)
      await router.push('/projects/8/assets/32')
      await flushPromises()
      expect(wrapper.findComponent({ name: 'TaskStartDialog' }).exists()).toBe(false)
      oldDialog.vm.$emit('started', { data: { taskStatus: 'preparing' } })
      await flushPromises()
      expect(startTask).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('新资产')
      expect(wrapper.text()).not.toContain('原资产')
    } finally {
      wrapper.unmount()
    }
  })

  it('资产与制作分项按钮同时受后端 allowedActions 和 session permission 约束', async () => {
    const { wrapper } = await mountDetail()
    expect(wrapper.text()).toContain('动力舱室内')
    expect(wrapper.text()).toContain('恐怖气氛主视角')
    expect(wrapper.text()).toContain('新增制作分项')
    expect(wrapper.text()).toContain('编辑资产')
    expect(wrapper.text()).toContain('归档资产')
    expect(wrapper.text()).toContain('分配任务')
    const tags = wrapper.findAllComponents(ElTag)
    expect(tags.find(tag => tag.text() === '场景')?.props('type')).toBe('primary')
    expect(tags.find(tag => tag.text() === '制作中')?.props('type')).toBe('primary')
    expect(tags.find(tag => tag.text() === '目录已就绪')?.props('type')).toBe('primary')
    expect(tags.find(tag => tag.text() === '活动')?.props('type')).toBe('success')
    wrapper.unmount()

    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), allowedActions: [], items: [{ ...assetItem, allowedActions: [] }] } })
    const restricted = await mountDetail()
    const restrictedButtons = restricted.wrapper.findAll('button').map(buttonLabel)
    expect(restrictedButtons).not.toContain('新增制作分项')
    expect(restrictedButtons).not.toContain('编辑资产')
    expect(restrictedButtons).not.toContain('归档资产')
    expect(restrictedButtons).not.toContain('分配任务')
    restricted.wrapper.unmount()
  })

  it.each([
    [true, true, true],
    [true, false, false],
    [false, true, false]
  ])('删除分项入口取后端动作与平台权限交集 %s/%s', async (allowed, permitted, visible) => {
    getAssetDetail.mockResolvedValue({ data: {
      ...assetDetail(), items: [{ ...assetItem, allowedActions: allowed ? ['assetItem.delete'] : [] }]
    } })
    const { wrapper } = await mountDetail('/projects/8/assets/31', permitted ? ['shotgrid:asset:archive'] : [])
    expect(wrapper.findAll('button').some(button => buttonLabel(button) === '删除分项')).toBe(visible)
    wrapper.unmount()
  })

  it('删除分项成功后刷新卡片、缩略图与制作履历，并通知资产列表', async () => {
    getAssetDetail.mockResolvedValue({ data: {
      ...assetDetail(), items: [{ ...assetItem, allowedActions: ['assetItem.delete'] }]
    } })
    const { wrapper } = await mountDetail()
    await wrapper.findAll('button').find(button => buttonLabel(button) === '删除分项').trigger('click')
    const dialog = wrapper.findComponent(AssetItemDeleteDialog)
    expect(dialog.props('item').assetItemId).toBe(41)
    getAssetDetail.mockResolvedValue({ data: { ...assetDetail(), items: [], itemCount: 0 } })
    dialog.vm.$emit('deleted', { deletedAssetItemId: 41 }, {
      projectId: 8, assetId: 31, assetItemId: 41, operationGeneration: dialog.props('operationGeneration')
    })
    await flushPromises()
    expect(wrapper.findComponent(AssetItemDeleteDialog).exists()).toBe(false)
    expect(wrapper.find('.item-card').exists()).toBe(false)
    expect(wrapper.find('.asset-hero__item').exists()).toBe(false)
    expect(wrapper.emitted('changed').at(-1)).toEqual([{ projectId: 8, assetId: 31 }])
    wrapper.unmount()
  })

  it('详情头部按活动制作分项顺序展示各自当前缩略图', async () => {
    const firstThumbnail = {
      fileId: 'thumbnail-1',
      name: '主视角.jpg',
      url: '/shot-grid/versions/91/files/thumbnail-1/download'
    }
    const secondThumbnail = {
      fileId: 'thumbnail-2',
      name: '反打视角.jpg',
      url: '/shot-grid/versions/92/files/thumbnail-2/download'
    }
    getAssetDetail.mockResolvedValue({
      data: {
        ...assetDetail(),
        items: [
          {
            ...assetItem,
            assetItemId: 42,
            productionItem: '反打视角',
            sortOrder: 20,
            latestVersion: { versionNo: 2, versionStatus: 'final' },
            thumbnail: secondThumbnail
          },
          {
            ...assetItem,
            assetItemId: 41,
            productionItem: '主视角',
            sortOrder: 10,
            latestVersion: { versionNo: 1, versionStatus: 'pending_review' },
            thumbnail: firstThumbnail
          },
          {
            ...assetItem,
            assetItemId: 43,
            productionItem: '已归档视角',
            lifecycleStatus: 'archived'
          }
        ]
      }
    })

    const { wrapper } = await mountDetail()
    const hero = wrapper.find('.asset-hero')
    const header = hero.find('.el-card__header')
    expect(header.exists()).toBe(true)
    expect(header.text()).toContain('动力舱室内')
    expect(header.find('.asset-hero__actions').exists()).toBe(true)
    expect(header.text()).not.toContain(assetRow.description)
    expect(hero.find('.asset-hero__main').text()).toContain(assetRow.description)
    const gallery = wrapper.find('.asset-hero__gallery')
    const thumbnails = gallery.findAllComponents(ProtectedAssetThumbnail)
    expect(thumbnails).toHaveLength(2)
    expect(thumbnails.map(component => component.props('thumbnail'))).toEqual([firstThumbnail, secondThumbnail])
    expect(gallery.text()).toContain('主视角V001 · 待审核')
    expect(gallery.text()).toContain('反打视角V002 · 最终版本')
    expect(gallery.text()).not.toContain('已归档视角')
    wrapper.unmount()
  })

  it('制作任务开始后详情页不再提供编辑分项和改派入口', async () => {
    getAssetDetail.mockResolvedValue({
      data: {
        ...assetDetail(),
        items: [{
          ...assetItem,
          task: { assigneeUserId: 7, assigneeName: '曲占锋', taskStatus: 'in_progress', priority: 'normal' },
          allowedActions: []
        }]
      }
    })
    const { wrapper } = await mountDetail()
    const buttons = wrapper.findAll('button').map(buttonLabel)
    expect(buttons).not.toContain('编辑分项')
    expect(buttons).not.toContain('改派任务')
    wrapper.unmount()
  })

  it('制作分项任务、优先级与版本状态使用对应 ElTag 类型', async () => {
    getAssetDetail.mockResolvedValue({
      data: {
        ...assetDetail(),
        items: [{
          ...assetItem,
          task: { assigneeUserId: 7, assigneeName: '杨景锋', taskStatus: 'pending_review', priority: 'urgent' },
          latestVersion: { versionNo: 2, versionStatus: 'rejected' },
          finalVersion: { versionNo: 1, versionStatus: 'final' }
        }]
      }
    })
    const { wrapper } = await mountDetail()
    const tags = wrapper.findAllComponents(ElTag)

    expect(tags.find(tag => tag.text() === '待审核')?.props('type')).toBe('warning')
    expect(tags.find(tag => tag.text() === '紧急优先级')?.props('type')).toBe('danger')
    expect(tags.find(tag => tag.text() === '已退回')?.props('type')).toBe('danger')
    expect(tags.find(tag => tag.text() === '最终版本')?.props('type')).toBe('success')
    wrapper.unmount()
  })

  it('快速切换项目与资产会立即清理旧详情并拒绝迟到响应', async () => {
    let resolveProject9
    getAssetDetail.mockImplementation((targetProjectId, targetAssetId) => {
      if (targetProjectId === 8) return Promise.resolve({ data: assetDetail(8, targetAssetId, '旧资产') })
      if (targetProjectId === 9) return new Promise(resolve => { resolveProject9 = resolve })
      return Promise.resolve({ data: assetDetail(10, targetAssetId, '当前资产') })
    })
    const { wrapper, router } = await mountDetail()
    expect(wrapper.text()).toContain('旧资产')
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    expect(wrapper.findComponent(AssetAssignDialog).exists()).toBe(true)

    await router.push('/projects/9/assets/51')
    await flushPromises()
    expect(wrapper.text()).toContain('正在加载资产详情')
    expect(wrapper.text()).not.toContain('旧资产')
    expect(wrapper.findComponent(AssetAssignDialog).exists()).toBe(false)

    await router.push('/projects/10/assets/61')
    await flushPromises()
    expect(wrapper.text()).toContain('当前资产')
    resolveProject9({ data: assetDetail(9, 51, '迟到旧资产') })
    await flushPromises()
    expect(wrapper.text()).toContain('当前资产')
    expect(wrapper.text()).not.toContain('迟到旧资产')
    wrapper.unmount()
  })

  it('返回同一资产重开分配弹窗后旧完成事件不能关闭新实例或刷新', async () => {
    getAssetDetail.mockImplementation((targetProjectId, targetAssetId) => Promise.resolve({ data: assetDetail(targetProjectId, targetAssetId, targetProjectId === 8 ? '同一资产' : '中转资产') }))
    const { wrapper, router } = await mountDetail()
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    const oldDialog = wrapper.findComponent(AssetAssignDialog)
    const oldGeneration = oldDialog.props('operationGeneration')

    await router.push('/projects/9/assets/51')
    await flushPromises()
    await router.push('/projects/8/assets/31')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    const newDialog = wrapper.findComponent(AssetAssignDialog)
    const callsBefore = getAssetDetail.mock.calls.length
    expect(newDialog.props('operationGeneration')).not.toBe(oldGeneration)

    oldDialog.vm.$emit('assigned', { taskId: 71 }, {
      projectId: 8,
      assetId: 31,
      assetItemId: 41,
      operationGeneration: oldGeneration,
      wasReassign: false
    })
    await flushPromises()
    expect(wrapper.findComponent(AssetAssignDialog).exists()).toBe(true)
    expect(wrapper.findComponent(AssetAssignDialog).props('operationGeneration')).toBe(newDialog.props('operationGeneration'))
    expect(getAssetDetail).toHaveBeenCalledTimes(callsBefore)
    wrapper.unmount()
  })
})

describe('资产表单统一使用 Element Plus 校验链路', () => {
  beforeEach(() => {
    archiveAsset.mockReset().mockResolvedValue({ data: { assetId: 31 } })
    assignAssetItemTask.mockReset().mockResolvedValue({ data: { taskId: 71 } })
    createAsset.mockReset().mockResolvedValue({ data: { assetId: 31 } })
    createAssetItem.mockReset().mockResolvedValue({ data: { assetItemId: 41 } })
    getAssetPage.mockReset().mockResolvedValue({ rows: [assetRow], total: 1, hasNext: false })
    getAssetRequirementPage.mockReset().mockResolvedValue({
      rows: [{
        requirementId: 91,
        episodeNo: 1,
        sceneNo: 1,
        shotNo: 1,
        shotId: 11,
        assetType: 'Environment',
        rawName: '动力舱室内',
        resolutionStatus: 'pending'
      }],
      total: 1,
      hasNext: false
    })
    resolveAssetRequirement.mockReset().mockResolvedValue({ data: { requirementId: 91 } })
  })

  it('删除分项确认校验原因、携带锁版本并阻止重复提交', async () => {
    let finishDelete
    deleteAssetItem.mockReset().mockImplementation(() => new Promise(resolve => { finishDelete = resolve }))
    const wrapper = mountAssetDialog(AssetItemDeleteDialog, {
      projectId: 8, operationGeneration: 1, asset: assetDetail(), item: { ...assetItem, lockVersion: 3 }
    })
    const form = wrapper.findComponent(ElForm)
    const confirm = form.findAllComponents(ElButton).find(button => buttonLabel(button) === '确认删除')
    await confirm.trigger('click')
    await flushPromises()
    expect(deleteAssetItem).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(form.text()).toContain('请填写删除原因'))
    await form.get('textarea').setValue('  新增后不再需要  ')
    await Promise.all([confirm.trigger('click'), confirm.trigger('click')])
    await flushPromises()
    expect(deleteAssetItem).toHaveBeenCalledTimes(1)
    expect(deleteAssetItem).toHaveBeenCalledWith(8, 41, { reason: '新增后不再需要', lockVersion: 3 })
    expect(confirm.props('loading')).toBe(true)
    expect(form.findAllComponents(ElButton).find(button => buttonLabel(button) === '取消').props('disabled')).toBe(true)
    finishDelete({ data: { projectId: 8, assetId: 31, deletedAssetItemId: 41 } })
    await flushPromises()
    expect(wrapper.emitted('deleted')[0]).toEqual([
      { projectId: 8, assetId: 31, deletedAssetItemId: 41 },
      { projectId: 8, assetId: 31, assetItemId: 41, lockVersion: 3, operationGeneration: 1 }
    ])
    wrapper.unmount()
  })

  it('删除发生状态冲突时保留原因，允许刷新且不报告成功', async () => {
    deleteAssetItem.mockReset().mockRejectedValue({ httpStatus: 409, message: '制作任务已经开始，分项不能删除' })
    const wrapper = mountAssetDialog(AssetItemDeleteDialog, {
      projectId: 8, operationGeneration: 1, asset: assetDetail(), item: assetItem
    })
    await wrapper.get('textarea').setValue('误建分项')
    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '确认删除').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('制作任务已经开始，分项不能删除')
    expect(wrapper.get('textarea').element.value).toBe('误建分项')
    expect(wrapper.emitted('deleted')).toBeUndefined()
    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '刷新后重试').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    wrapper.unmount()
  })

  it('取消删除重置原因，关闭后未返回的删除结果不再更新旧弹窗', async () => {
    let finishDelete
    deleteAssetItem.mockReset().mockImplementation(() => new Promise(resolve => { finishDelete = resolve }))
    const props = { projectId: 8, operationGeneration: 1, asset: assetDetail(), item: assetItem }
    const canceled = mountAssetDialog(AssetItemDeleteDialog, props)
    await canceled.get('textarea').setValue('误建')
    await canceled.findAllComponents(ElButton).find(button => buttonLabel(button) === '取消').trigger('click')
    expect(canceled.findComponent(ElForm).props('model').reason).toBe('')
    expect(canceled.emitted('close')).toHaveLength(1)
    expect(deleteAssetItem).not.toHaveBeenCalled()
    canceled.unmount()
    const wrapper = mountAssetDialog(AssetItemDeleteDialog, props)
    await wrapper.get('textarea').setValue('误建')
    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '确认删除').trigger('click')
    await flushPromises()
    wrapper.unmount()
    finishDelete({ data: { deletedAssetItemId: 41 } })
    await flushPromises()
    expect(wrapper.emitted('deleted')).toBeUndefined()
  })

  it('归档表单通过按钮点击和 Form.validate 阻止空原因', async () => {
    const wrapper = mountAssetDialog(AssetArchiveDialog, {
      projectId: 8,
      operationGeneration: 1,
      asset: assetDetail()
    })
    const form = wrapper.findComponent(ElForm)
    const confirmButton = form.findAllComponents(ElButton).find(button => buttonLabel(button) === '确认归档')
    expect(form.props('model')).toMatchObject({ reason: '' })
    expect(form.props('rules')).toHaveProperty('reason')
    expect(form.findComponent(ElFormItem).props('prop')).toBe('reason')
    expect(confirmButton.props('nativeType')).toBe('button')

    await confirmButton.trigger('click')
    await flushPromises()
    expect(archiveAsset).not.toHaveBeenCalled()

    await form.findComponent(ElInput).find('textarea').setValue('项目结束归档')
    await confirmButton.trigger('click')
    await flushPromises()
    expect(archiveAsset).toHaveBeenCalledWith(8, 31, expect.objectContaining({ reason: '项目结束归档' }))
    wrapper.unmount()
  })

  it('任务分配表单校验制作人后才调用真实接口', async () => {
    const wrapper = mountAssetDialog(AssetAssignDialog, {
      projectId: 8,
      operationGeneration: 1,
      asset: assetDetail(),
      item: assetItem,
      members: [memberRow]
    })
    const form = wrapper.findComponent(ElForm)
    const confirmButton = form.findAllComponents(ElButton).find(button => buttonLabel(button) === '确认分配')
    expect(form.props('rules')).toHaveProperty('assigneeUserId')
    expect(form.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual(['assigneeUserId', 'taskDescription'])

    await confirmButton.trigger('click')
    await flushPromises()
    expect(assignAssetItemTask).not.toHaveBeenCalled()

    form.props('model').assigneeUserId = '7'
    await wrapper.vm.$nextTick()
    await confirmButton.trigger('click')
    await flushPromises()
    expect(assignAssetItemTask).toHaveBeenCalledWith(8, 41, expect.objectContaining({ assigneeUserId: 7, taskLockVersion: null }))
    wrapper.unmount()
  })

  it('开工后共有说明只读，仍能保存排序和内部备注', async () => {
    updateAsset.mockReset().mockResolvedValue({ data: assetDetail() })
    const wrapper = mountAssetDialog(AssetFormDialog, {
      projectId: 8, operationGeneration: 1, asset: { ...assetDetail(), descriptionLocked: true }
    })
    const [description, remark] = wrapper.findAll('textarea')
    expect(description.element.readOnly).toBe(true)
    expect(remark.element.readOnly).toBe(false)
    expect(wrapper.text()).toContain('已有制作分项开工，资产描述已锁定')
    const sort = wrapper.findComponent(ElInputNumber).get('input')
    await sort.setValue('18')
    await sort.trigger('change')
    await remark.setValue('调整内部协作备注')
    const save = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '保存资产')
    await save.trigger('click')
    await flushPromises()
    expect(updateAsset).toHaveBeenCalledWith(8, 31, {
      description: assetRow.description, sortOrder: 18, remark: '调整内部协作备注', lockVersion: 0
    })
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })

  it('未开工共有说明可编辑，保存期间阻止重复提交', async () => {
    let finishUpdate
    updateAsset.mockReset().mockImplementation(() => new Promise(resolve => { finishUpdate = resolve }))
    const wrapper = mountAssetDialog(AssetFormDialog, {
      projectId: 8, operationGeneration: 1, asset: assetDetail()
    })
    const description = wrapper.findAll('textarea')[0]
    expect(description.element.readOnly).toBe(false)
    await description.setValue('修改共有制作要求')
    const save = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '保存资产')
    await Promise.all([save.trigger('click'), save.trigger('click')])
    await flushPromises()
    expect(updateAsset).toHaveBeenCalledTimes(1)
    expect(updateAsset).toHaveBeenCalledWith(8, 31, expect.objectContaining({ description: '修改共有制作要求' }))
    expect(save.props('loading')).toBe(true)
    expect(wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '取消').props('disabled')).toBe(true)
    wrapper.unmount()
    finishUpdate({ data: assetDetail() })
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
  })

  it('旧弹窗遇到共有说明锁定时恢复原说明并保留其他草稿供重试', async () => {
    updateAsset.mockReset().mockRejectedValueOnce({
      httpStatus: 409, errorKey: 'SG_ASSET_DESCRIPTION_LOCKED', message: '共有说明已锁定，仍可修改排序和备注'
    }).mockResolvedValue({ data: assetDetail() })
    const wrapper = mountAssetDialog(AssetFormDialog, {
      projectId: 8, operationGeneration: 1, asset: assetDetail()
    })
    const [description, remark] = wrapper.findAll('textarea')
    await description.setValue('开工前打开的草稿')
    await remark.setValue('保留这份内部备注')
    const sort = wrapper.findComponent(ElInputNumber).get('input')
    await sort.setValue('18')
    await sort.trigger('change')
    const save = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '保存资产')
    await save.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(description.element.readOnly).toBe(true)
    expect(description.element.value).toBe(assetRow.description)
    expect(remark.element.value).toBe('保留这份内部备注')
    expect(sort.element.value).toBe('18')
    expect(wrapper.text()).toContain('共有说明已锁定，仍可修改排序和备注')
    await save.trigger('click')
    await flushPromises()
    expect(updateAsset).toHaveBeenLastCalledWith(8, 31, {
      description: assetRow.description, sortOrder: 18, remark: '保留这份内部备注', lockVersion: 0
    })
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })

  it('资产创建表单在名称校验通过后由点击按钮创建资产', async () => {
    const wrapper = mountAssetDialog(AssetFormDialog, {
      projectId: 8,
      operationGeneration: 1
    })
    const form = wrapper.findComponent(ElForm)
    const createButton = form.findAllComponents(ElButton).find(button => buttonLabel(button) === '创建资产')
    expect(form.props('rules')).toHaveProperty('assetName')
    expect(createButton.props('nativeType')).toBe('button')

    await createButton.trigger('click')
    await flushPromises()
    expect(createAsset).not.toHaveBeenCalled()

    form.props('model').assetName = '新场景资产'
    await wrapper.vm.$nextTick()
    await createButton.trigger('click')
    await flushPromises()
    expect(createAsset).toHaveBeenCalledWith(8, expect.objectContaining({ assetName: '新场景资产', assetType: 'Character' }))
    const createPayload = createAsset.mock.calls[0][1]
    expect(createPayload.items[0]).not.toHaveProperty('assigneeUserId')
    expect(createPayload.items[0]).not.toHaveProperty('taskDescription')
    expect(wrapper.text()).toContain('创建后状态：未分配')
    wrapper.unmount()
  })

  it('制作分项表单只保存未分配分项，任务由后续分配操作创建', async () => {
    const wrapper = mountAssetDialog(AssetItemFormDialog, {
      projectId: 8,
      operationGeneration: 1,
      asset: assetDetail()
    })
    const form = wrapper.findComponent(ElForm)
    const sortItem = form.findAllComponents(ElFormItem).find(item => item.props('prop') === 'sortOrder')
    const saveButton = form.findAllComponents(ElButton).find(button => buttonLabel(button) === '新增分项')
    expect(sortItem.findComponent(ElInputNumber).exists()).toBe(true)
    expect(form.props('model')).not.toHaveProperty('assigneeUserId')
    expect(form.props('model')).not.toHaveProperty('taskDescription')
    expect(wrapper.text()).toContain('保存后状态：未分配')
    expect(wrapper.text()).toContain(assetRow.description)
    expect(form.findAllComponents(ElFormItem).find(item => item.props('prop') === 'description').props('label')).toBe('分项补充要求')

    form.props('model').productionItem = '恐怖气氛主视角'
    form.props('model').sortOrder = 2
    await wrapper.vm.$nextTick()
    await saveButton.trigger('click')
    await flushPromises()
    expect(createAssetItem).toHaveBeenCalledWith(8, 31, expect.objectContaining({ sortOrder: 2 }))
    const itemPayload = createAssetItem.mock.calls[0][2]
    expect(itemPayload).not.toHaveProperty('assigneeUserId')
    expect(itemPayload).not.toHaveProperty('taskDescription')
    wrapper.unmount()
  })

  it('资产需求筛选和匹配表单均由普通按钮触发 Form.validate', async () => {
    const wrapper = mountAssetDialog(AssetRequirementDialog, {
      projectId: 8,
      canResolve: true,
      canIgnore: false,
      canRematch: false
    })
    await flushPromises()
    const requirementTags = wrapper.findAllComponents(ElTag)
    expect(requirementTags.find(tag => tag.text() === '场景')?.props('type')).toBe('primary')
    expect(requirementTags.find(tag => tag.text() === '待匹配')?.props('type')).toBe('warning')
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.attributes('aria-label') === '资产需求筛选')
    const queryButton = filterForm.findAllComponents(ElButton).find(button => buttonLabel(button) === '查询')
    expect(filterForm.props('rules')).toHaveProperty('keyword')
    expect(queryButton.props('nativeType')).toBe('button')

    getAssetRequirementPage.mockClear()
    await queryButton.trigger('click')
    await flushPromises()
    expect(getAssetRequirementPage).toHaveBeenCalledTimes(1)

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '选择资产').trigger('click')
    await flushPromises()
    const resolveForm = wrapper.findAllComponents(ElForm).find(form => form.attributes('aria-label') === '资产需求匹配表单')
    const resolveButton = wrapper.findAll('button').find(button => button.text().includes('确认匹配'))
    expect(resolveForm.props('rules')).toHaveProperty('assetId')
    expect(resolveForm.props('rules')).toHaveProperty('reason')

    await resolveButton.trigger('click')
    await flushPromises()
    expect(resolveAssetRequirement).not.toHaveBeenCalled()

    resolveForm.props('model').assetId = '31'
    resolveForm.props('model').reason = '名称与类型确认一致'
    await wrapper.vm.$nextTick()
    await resolveButton.trigger('click')
    await flushPromises()
    expect(resolveAssetRequirement).toHaveBeenCalledWith(8, 91, { assetId: 31, reason: '名称与类型确认一致' }, expect.any(String))
    wrapper.unmount()
  })
})

describe('资产列表弹窗绑定', () => {
  it('导入弹窗绑定当前项目和唯一操作代次', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import'] } })
    listAssetAssignees.mockResolvedValue({ rows: [memberRow], total: 1, hasNext: false })
    getAssetPage.mockResolvedValue({ rows: [assetRow], total: 1, hasNext: false })
    const { wrapper } = await mountList()
    await wrapper.findAll('button').find(button => button.text().includes('导入 Excel')).trigger('click')
    const dialog = wrapper.findComponent(AssetImportDialog)
    expect(dialog.props('projectId')).toBe(8)
    expect(dialog.props('operationGeneration')).toBeGreaterThan(0)
    wrapper.unmount()
  })
})
