import { ElAlert, ElButton, ElCard, ElDatePicker, ElDialog, ElDrawer, ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElLoading, ElOption, ElPagination, ElRadioButton, ElRadioGroup, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  archiveAsset,
  assignAssetItemTask,
  createAsset,
  createAssetItem,
  getAssetDetail,
  getAssetPage,
  getAssetRequirementPage,
  listAssetAssignees,
  resolveAssetRequirement
} from '@/api/shot-grid/assets'
import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import { setElSelectValue } from '../helpers/elementPlus'
import AssetDetailView from '@/views/asset/AssetDetailView.vue'
import AssetListView from '@/views/asset/AssetListView.vue'
import AssetArchiveDialog from '@/views/asset/components/AssetArchiveDialog.vue'
import AssetAssignDialog from '@/views/asset/components/AssetAssignDialog.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'
import AssetItemFormDialog from '@/views/asset/components/AssetItemFormDialog.vue'
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
  assignAssetItemTask: vi.fn(),
  batchAssignAssetItemTasks: vi.fn(),
  batchDeleteAssets: vi.fn(),
  commitAssetImport: vi.fn(),
  createAsset: vi.fn(),
  createAssetItem: vi.fn(),
  downloadAssetImportTemplate: vi.fn(),
  downloadAssetThumbnail: vi.fn(),
  getAssetDetail: vi.fn(),
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
  const wrapper = mount(AssetListView, { global: { plugins: [pinia, router], components: { ElButton, ElCard, ElDatePicker, ElDialog, ElDrawer, ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElPagination, ElRadioButton, ElRadioGroup, ElTable, ElTableColumn, ElTag } } })
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
      components: { ElButton, ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElTag },
      stubs: { ProductionHistoryPanel: true, ProtectedAssetThumbnail: true }
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
    expect(productionStatusTag.props()).toMatchObject({ type: 'primary', effect: 'dark', round: true })
    expect(wrapper.find('.asset-table-wrap').text()).not.toContain('目录已就绪')
    const tableColumns = wrapper.findAllComponents(ElTableColumn)
    const rightFixedColumns = tableColumns.filter(column => column.props('fixed') === 'right')
    expect(rightFixedColumns.map(column => column.props('label'))).toEqual(['制作人', '状态', '操作'])
    expect(tableColumns.slice(-3).map(column => column.props('label'))).toEqual(['制作人', '状态', '操作'])

    const filterSelects = wrapper.find('.asset-filters').findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], 'Environment')
    await setElSelectValue(filterSelects[1], 'in_progress')
    await setElSelectValue(filterSelects[2], '7')
    const queryButton = filterForm.findAllComponents(ElButton).find(button => button.text() === '查询')
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
    wrapper.unmount()
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

    await filterForm.findAllComponents(ElButton).find(button => button.text() === '重置').trigger('click')
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
    await wrapper.findAll('button').find(button => button.text() === '详情').trigger('click')
    await flushPromises()

    const detail = wrapper.findComponent(AssetDetailView)
    expect(detail.exists()).toBe(true)
    expect(detail.props()).toMatchObject({ embedded: true, targetProjectId: 8, targetAssetId: 31 })
    expect(detail.text()).toContain('动力舱室内')
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
    const buttons = wrapper.findAll('button').map(button => button.text())
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
})

describe('资产详情动作镜像与路由隔离', () => {
  beforeEach(() => {
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import'] } })
    listAssetAssignees.mockResolvedValue({ rows: [memberRow], total: 1, hasNext: false })
    getAssetDetail.mockResolvedValue({ data: assetDetail() })
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
    const restrictedButtons = restricted.wrapper.findAll('button').map(button => button.text())
    expect(restrictedButtons).not.toContain('新增制作分项')
    expect(restrictedButtons).not.toContain('编辑资产')
    expect(restrictedButtons).not.toContain('归档资产')
    expect(restrictedButtons).not.toContain('分配任务')
    restricted.wrapper.unmount()
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
    const gallery = wrapper.find('.asset-hero__gallery')
    const thumbnails = gallery.findAllComponents(ProtectedAssetThumbnail)
    expect(thumbnails).toHaveLength(2)
    expect(thumbnails.map(component => component.props('thumbnail'))).toEqual([firstThumbnail, secondThumbnail])
    expect(gallery.text()).toContain('主视角V001 · 待审核')
    expect(gallery.text()).toContain('反打视角V002 · 最终版本')
    expect(gallery.text()).not.toContain('已归档视角')
    wrapper.unmount()
  })

  it('制作任务开始后详情页不再提供编辑分项入口', async () => {
    getAssetDetail.mockResolvedValue({
      data: {
        ...assetDetail(),
        items: [{
          ...assetItem,
          task: { assigneeUserId: 7, assigneeName: '曲占锋', taskStatus: 'in_progress', priority: 'normal' },
          allowedActions: ['task.assign']
        }]
      }
    })
    const { wrapper } = await mountDetail()
    const buttons = wrapper.findAll('button').map(button => button.text())
    expect(buttons).not.toContain('编辑分项')
    expect(buttons).toContain('改派任务')
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

  it('归档表单通过按钮点击和 Form.validate 阻止空原因', async () => {
    const wrapper = mountAssetDialog(AssetArchiveDialog, {
      projectId: 8,
      operationGeneration: 1,
      asset: assetDetail()
    })
    const form = wrapper.findComponent(ElForm)
    const confirmButton = form.findAllComponents(ElButton).find(button => button.text() === '确认归档')
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
    const confirmButton = form.findAllComponents(ElButton).find(button => button.text() === '确认分配')
    expect(form.props('rules')).toHaveProperty('assigneeUserId')
    expect(form.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual(['assigneeUserId', 'taskDescription', 'priority', 'dueDate'])

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

  it('资产创建表单在名称校验通过后由点击按钮创建资产', async () => {
    const wrapper = mountAssetDialog(AssetFormDialog, {
      projectId: 8,
      operationGeneration: 1
    })
    const form = wrapper.findComponent(ElForm)
    const createButton = form.findAllComponents(ElButton).find(button => button.text() === '创建资产')
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
    const saveButton = form.findAllComponents(ElButton).find(button => button.text() === '新增分项')
    expect(sortItem.findComponent(ElInputNumber).exists()).toBe(true)
    expect(form.props('model')).not.toHaveProperty('assigneeUserId')
    expect(form.props('model')).not.toHaveProperty('taskDescription')
    expect(wrapper.text()).toContain('保存后状态：未分配')

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
    const queryButton = filterForm.findAllComponents(ElButton).find(button => button.text() === '查询')
    expect(filterForm.props('rules')).toHaveProperty('keyword')
    expect(queryButton.props('nativeType')).toBe('button')

    getAssetRequirementPage.mockClear()
    await queryButton.trigger('click')
    await flushPromises()
    expect(getAssetRequirementPage).toHaveBeenCalledTimes(1)

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '选择资产').trigger('click')
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
