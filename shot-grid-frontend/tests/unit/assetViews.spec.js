import { ElButton, ElIcon } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getAssetDetail, getAssetPage, listAssetAssignees } from '@/api/shot-grid/assets'
import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import { setElSelectValue } from '../helpers/elementPlus'
import AssetDetailView from '@/views/asset/AssetDetailView.vue'
import AssetListView from '@/views/asset/AssetListView.vue'
import AssetAssignDialog from '@/views/asset/components/AssetAssignDialog.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'

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
  commitAssetImport: vi.fn(),
  createAsset: vi.fn(),
  createAssetItem: vi.fn(),
  downloadAssetImportTemplate: vi.fn(),
  downloadAssetThumbnail: vi.fn(),
  getAssetDetail: vi.fn(),
  getAssetPage: vi.fn(),
  listAssetAssignees: vi.fn(),
  previewAssetImport: vi.fn(),
  updateAsset: vi.fn(),
  updateAssetItem: vi.fn()
}))

const projectRow = { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人' }
const memberRow = { userId: 7, userName: 'producer', nickName: '杨景锋', producerCode: 'YJF' }
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
  const wrapper = mount(AssetListView, { global: { plugins: [pinia, router], components: { ElButton, ElIcon } } })
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
  const wrapper = mount(AssetDetailView, { global: { plugins: [pinia, router], components: { ElButton, ElIcon } } })
  await flushPromises()
  return { wrapper, router }
}

describe('资产管理真实列表页', () => {
  beforeEach(() => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director', allowedActions: ['asset.create', 'asset.import'] } })
    listAssetAssignees.mockResolvedValue({ rows: [memberRow], total: 1, hasNext: false })
    getAssetPage.mockResolvedValue({ rows: [assetRow], total: 1, hasNext: false })
  })

  it('展示真实资产结果、四类筛选、分页与三种视图', async () => {
    const { wrapper } = await mountList()
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')
    expect(wrapper.text()).toContain('动力舱室内')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.find('.asset-table-wrap').text()).toContain('杨景锋（YJF）')
    expect(wrapper.text()).toContain('导入 Excel')
    expect(wrapper.text()).toContain('新建资产')

    const filterSelects = wrapper.find('.asset-filters').findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], 'Environment')
    await setElSelectValue(filterSelects[1], 'in_progress')
    await setElSelectValue(filterSelects[2], '7')
    await wrapper.find('form[aria-label="资产筛选"]').trigger('submit')
    await flushPromises()
    expect(getAssetPage).toHaveBeenLastCalledWith(8, expect.objectContaining({
      assetType: 'Environment',
      assetStatus: 'in_progress',
      assigneeUserId: '7'
    }), expect.anything())

    await wrapper.findAll('button').find(button => button.text().includes('卡片')).trigger('click')
    expect(wrapper.find('.asset-card').exists()).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('类型看板')).trigger('click')
    expect(wrapper.find('.type-board').text()).toContain('场景')
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
