import {
  ElAlert,
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElPagination,
  ElProgress,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag
} from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addProjectMember,
  archiveProject,
  createProject,
  getProjectDetail,
  getProjectMemberRoleOptions,
  getProjectMembers,
  getProjectOverview,
  getProjectPage,
  getProjectRoleOptions,
  getProjectStorage,
  getStorageOperationPage,
  getStorageRootOptions,
  previewProjectPath,
  purgeProject,
  retryProjectStorage,
  updateProject,
  updateProjectMember
} from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectDetailView from '@/views/project/ProjectDetailView.vue'
import ProjectListView from '@/views/project/ProjectListView.vue'
import ProjectArchiveDialog from '@/views/project/components/ProjectArchiveDialog.vue'
import ProjectCreateDialog from '@/views/project/components/ProjectCreateDialog.vue'
import ProjectEditDialog from '@/views/project/components/ProjectEditDialog.vue'
import ProjectMemberPanel from '@/views/project/components/ProjectMemberPanel.vue'
import ProjectPurgeDialog from '@/views/project/components/ProjectPurgeDialog.vue'
import ProjectStoragePanel from '@/views/project/components/ProjectStoragePanel.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  addProjectMember: vi.fn(),
  archiveProject: vi.fn(),
  createProject: vi.fn(),
  getProjectDetail: vi.fn(),
  getProjectMemberRoleOptions: vi.fn(),
  getProjectMembers: vi.fn(),
  getProjectOverview: vi.fn(),
  getProjectPage: vi.fn(),
  getProjectRoleOptions: vi.fn(),
  getProjectStorage: vi.fn(),
  getStorageOperationDetail: vi.fn(),
  getStorageOperationPage: vi.fn(),
  getStorageRootOptions: vi.fn(),
  previewProjectPath: vi.fn(),
  purgeProject: vi.fn(),
  removeProjectMember: vi.fn(),
  retryProjectStorage: vi.fn(),
  retryStorageOperation: vi.fn(),
  updateProject: vi.fn(),
  updateProjectMember: vi.fn()
}))

const formComponents = {
  ElAlert,
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElPagination,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag
}
const projectModalStub = {
  name: 'ProjectModal',
  template: '<section class="project-modal-stub"><slot /></section>'
}

function buttonByText(wrapper, text) {
  return wrapper.findAllComponents(ElButton).find(button => button.text() === text)
}

const projectRow = {
  projectId: 8,
  projectCode: 'LCFR',
  projectName: '罗刹夫人',
  projectTypeName: 'AI 影视短片',
  aspectRatio: '16:9',
  projectStatus: 'active',
  storageStatus: 'ready',
  myProjectRole: 'director',
  currentPhase: 'shot_production',
  completedShots: 12,
  totalShots: 30,
  completedAssets: 4,
  totalAssets: 7,
  plannedDurationMs: 5_400_000,
  overallProgress: 40
}

const projectRoleOptions = [
  {
    projectRole: 'director',
    projectRoleLabel: '项目管理人',
    systemRoleId: 11,
    systemRoleKey: 'shotgrid_admin',
    systemRoleName: 'Shot Grid 项目管理人'
  },
  {
    projectRole: 'creator',
    projectRoleLabel: '制作人员',
    systemRoleId: 12,
    systemRoleKey: 'shotgrid_creator',
    systemRoleName: 'Shot Grid 制作人员'
  }
]

async function mountProjectList(permissions = []) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin', nickName: '管理员', dept: null }
  session.permissions = permissions
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects', component: ProjectListView },
      { path: '/projects/:projectId/overview', component: { template: '<div>详情</div>' } }
    ]
  })
  await router.push('/projects')
  await router.isReady()
  const wrapper = mount(ProjectListView, {
    global: { plugins: [pinia, router], components: { ElButton, ElCard, ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElPagination, ElProgress, ElSkeleton, ElTag } }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('项目管理页面', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, allowedActions: [] } })
    getProjectOverview.mockResolvedValue({ data: { overallProgress: 40 } })
    getProjectRoleOptions.mockResolvedValue({ data: projectRoleOptions })
    getProjectMemberRoleOptions.mockResolvedValue({ data: projectRoleOptions })
    getStorageRootOptions.mockResolvedValue({ data: [{ storageRootId: 7, rootName: '主存储', rootCode: 'MAIN', uncRootPath: '\\\\nas\\shot-grid' }] })
    previewProjectPath.mockResolvedValue({ data: { projectPathPreview: '\\\\nas\\shot-grid\\罗刹夫人', pathConflict: false } })
    createProject.mockResolvedValue({ data: { projectId: 8 } })
    updateProject.mockResolvedValue({ data: { ...projectRow, lockVersion: 2 } })
    archiveProject.mockResolvedValue({ data: { ...projectRow, projectStatus: 'archived' } })
    purgeProject.mockResolvedValue({ data: { purgeId: 91, projectId: 8, purgeStatus: 'pending' } })
    getProjectMembers.mockResolvedValue({ rows: [] })
    addProjectMember.mockResolvedValue({ data: {} })
    updateProjectMember.mockResolvedValue({ data: {} })
    getProjectStorage.mockResolvedValue({
      data: {
        projectId: 8,
        storageStatus: 'failed',
        projectPathSnapshot: '\\\\nas\\shot-grid\\罗刹夫人',
        lockVersion: 3,
        updateTime: '2026-08-18T10:00:00'
      }
    })
    getStorageOperationPage.mockResolvedValue({ rows: [], total: 0 })
    retryProjectStorage.mockResolvedValue({ data: {} })
  })

  it('展示真实范围列表并按接口权限显示创建入口', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 13, hasNext: true })
    const { wrapper } = await mountProjectList(['shotgrid:project:add', 'shotgrid:project:all'])

    const filterForm = wrapper.findComponent(ElForm)
    expect(filterForm.classes()).toContain('el-form')
    expect(filterForm.props('model')).toMatchObject({
      keyword: '',
      projectStatus: '',
      scope: '',
      orderByColumn: 'createTime',
      isAsc: 'descending',
      pageNum: 1,
      pageSize: 12
    })
    expect(filterForm.props('rules')).toMatchObject({
      keyword: expect.any(Array),
      projectStatus: expect.any(Array),
      orderByColumn: expect.any(Array)
    })
    expect(filterForm.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual([
      'keyword',
      'projectStatus',
      'scope',
      'orderByColumn',
      'isAsc',
      undefined
    ])
    expect(buttonByText(filterForm, '查询').props('nativeType')).toBe('button')
    expect(wrapper.text()).toContain('罗刹夫人')
    expect(wrapper.text()).toContain('创建项目')
    expect(wrapper.text()).toContain('12/30')
    expect(wrapper.find('.project-card.el-card').exists()).toBe(true)
    expect(wrapper.find('.project-card .el-progress').exists()).toBe(true)
    const cardTags = wrapper.find('.project-card').findAllComponents(ElTag)
    expect(cardTags.find(tag => tag.text() === '进行中')?.props('type')).toBe('success')
    expect(cardTags.find(tag => tag.text() === '存储就绪')?.props('type')).toBe('success')
    expect(cardTags.find(tag => tag.text() === '我的角色：项目管理人')?.props('type')).toBe('primary')
    expect(cardTags.find(tag => tag.text() === 'AI 影视短片')?.props('type')).toBe('primary')
    expect(wrapper.find('.project-pagination.el-pagination').exists()).toBe(true)
    await wrapper.find('.project-pagination .btn-next').trigger('click')
    await flushPromises()
    expect(getProjectPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageNum: 2 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    wrapper.unmount()
  })

  it('Element Plus Form model 驱动项目查询参数', async () => {
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])
    const filterForm = wrapper.findComponent(ElForm)
    getProjectPage.mockClear()

    await filterForm.find('input[aria-label="搜索项目名称或代号"]').setValue('LCFR')
    await buttonByText(filterForm, '查询').trigger('click')
    await flushPromises()

    expect(filterForm.props('model')).toMatchObject({ keyword: 'LCFR', pageNum: 1 })
    expect(getProjectPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: 'LCFR', pageNum: 1 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    wrapper.unmount()
  })

  it('项目查询按钮先通过 ElForm 校验，非法模型不会发起请求', async () => {
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])
    const filterForm = wrapper.findComponent(ElForm)
    getProjectPage.mockClear()

    filterForm.props('model').keyword = 'X'.repeat(201)
    await nextTick()
    await buttonByText(filterForm, '查询').trigger('click')
    await flushPromises()

    expect(getProjectPage).not.toHaveBeenCalled()
    expect(filterForm.findComponent(ElFormItem).vm.$.exposed.validateState.value).toBe('error')
    wrapper.unmount()
  })

  it('没有 project:add 权限时不渲染创建动作', async () => {
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])

    expect(wrapper.text()).not.toContain('创建项目')
    wrapper.unmount()
  })

  it('项目详情用 ElTag 表达项目状态、类型、角色、阶段与存储状态', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const session = useSessionStore()
    session.user = { userId: 1, userName: 'admin', nickName: '管理员' }
    session.permissions = ['shotgrid:project:query']
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/projects', component: { template: '<div>项目列表</div>' } },
        { path: '/projects/:projectId/overview', component: ProjectDetailView }
      ]
    })
    await router.push('/projects/8/overview')
    await router.isReady()
    const wrapper = mount(ProjectDetailView, {
      global: {
        plugins: [pinia, router],
        components: { ElButton, ElIcon, ElTag },
        stubs: {
          ProjectMemberPanel: true,
          ProjectStoragePanel: true,
          ProjectStatePanel: true,
          ProjectEditDialog: true,
          ProjectArchiveDialog: true
        }
      }
    })
    await flushPromises()

    const tags = wrapper.findAllComponents(ElTag)
    expect(tags.find(tag => tag.text() === '进行中')?.props('type')).toBe('success')
    expect(tags.find(tag => tag.text() === 'AI 影视短片')?.props('type')).toBe('primary')
    expect(tags.find(tag => tag.text() === '镜头制作')?.props('type')).toBe('info')
    expect(tags.find(tag => tag.text() === '项目管理人')?.props('type')).toBe('primary')
    expect(tags.find(tag => tag.text() === '存储就绪')?.props('type')).toBe('success')
    wrapper.unmount()
  })

  it('403 不会伪装成空列表', async () => {
    getProjectPage.mockRejectedValue({ httpStatus: 403, message: '无权查看全部项目' })
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])

    expect(wrapper.text()).toContain('没有项目访问权限')
    expect(wrapper.text()).toContain('无权查看全部项目')
    expect(wrapper.text()).not.toContain('当前范围暂无项目')
    wrapper.unmount()
  })

  it('创建项目使用 ElForm 规则门禁，并由按钮点击进入加载与幂等请求', async () => {
    let resolveCreate
    createProject.mockImplementation(() => new Promise(resolve => { resolveCreate = resolve }))
    const wrapper = mount(ProjectCreateDialog, {
      props: { currentUser: { userId: 1, userName: 'admin', nickName: '管理员', dept: { deptId: 10, deptName: '制作部' } } },
      global: {
        components: formComponents,
        stubs: { ProjectModal: projectModalStub, MemberCandidateSelect: true }
      }
    })
    await flushPromises()
    const form = wrapper.findComponent(ElForm)
    const model = form.props('model')
    Object.assign(model, { projectName: '罗刹夫人', projectCode: '*', storageRootId: '7' })
    await nextTick()

    const submitButton = buttonByText(form, '创建并初始化 NAS')
    expect(form.props('rules')).toMatchObject({ projectName: expect.any(Array), projectCode: expect.any(Array), storageRootId: expect.any(Array), members: expect.any(Array) })
    expect(submitButton.props('nativeType')).toBe('button')
    await submitButton.trigger('click')
    await flushPromises()
    expect(createProject).not.toHaveBeenCalled()

    model.projectCode = 'lcfr'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    await submitButton.trigger('click')
    await flushPromises()
    expect(createProject).toHaveBeenCalledWith(
      expect.objectContaining({ projectCode: 'LCFR', projectName: '罗刹夫人', storageRootId: 7, directorUserIds: [1] }),
      expect.any(String)
    )
    expect(createProject).toHaveBeenCalledTimes(1)
    expect(submitButton.props('loading')).toBe(true)

    resolveCreate({ data: { projectId: 8 } })
    await flushPromises()
    expect(wrapper.emitted('created')).toEqual([[{ projectId: 8 }]])
    wrapper.unmount()
  })

  it('项目角色映射不完整时明确提示并禁止创建', async () => {
    getProjectRoleOptions.mockResolvedValue({ data: [projectRoleOptions[1]] })
    const wrapper = mount(ProjectCreateDialog, {
      props: { currentUser: { userId: 1, userName: 'admin', nickName: '管理员', dept: null } },
      global: {
        components: formComponents,
        stubs: { ProjectModal: projectModalStub, MemberCandidateSelect: true }
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('项目角色配置缺失')
    expect(wrapper.text()).toContain('项目管理人')
    expect(buttonByText(wrapper, '创建并初始化 NAS').props('disabled')).toBe(true)
    expect(createProject).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('编辑项目先校验 ElForm，再提交规范化数据', async () => {
    const wrapper = mount(ProjectEditDialog, {
      props: {
        project: {
          ...projectRow,
          projectDescription: '旧描述',
          projectType: 'ai_short_film',
          currentPhase: 'shot_production',
          remark: '',
          lockVersion: 1
        }
      },
      global: { components: formComponents, stubs: { ProjectModal: projectModalStub } }
    })
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '保存修改')
    form.props('model').projectName = '   '
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(updateProject).not.toHaveBeenCalled()

    form.props('model').projectName = ' 罗刹夫人·修订 '
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(8, expect.objectContaining({ projectName: '罗刹夫人·修订', lockVersion: 1 }))
    expect(submitButton.props('nativeType')).toBe('button')
    wrapper.unmount()
  })

  it('归档项目通过 ElForm 校验归档原因后才执行危险动作', async () => {
    const wrapper = mount(ProjectArchiveDialog, {
      props: { project: { ...projectRow, lockVersion: 4 } },
      global: { components: formComponents, stubs: { ProjectModal: projectModalStub } }
    })
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '确认归档')
    await submitButton.trigger('click')
    await flushPromises()
    expect(archiveProject).not.toHaveBeenCalled()

    form.props('model').reason = ' 项目已经完成交付 '
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(archiveProject).toHaveBeenCalledWith(8, { reason: '项目已经完成交付', lockVersion: 4 })
    expect(submitButton.props('nativeType')).toBe('button')
    wrapper.unmount()
  })

  it('永久删除要求项目名称完全一致和删除原因后才提交', async () => {
    const wrapper = mount(ProjectPurgeDialog, {
      props: { project: { ...projectRow, lockVersion: 4 } },
      global: { components: formComponents, stubs: { ProjectModal: projectModalStub } }
    })
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '确认永久删除')
    form.props('model').projectName = '错误名称'
    form.props('model').reason = '演示测试数据'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(purgeProject).not.toHaveBeenCalled()

    form.props('model').projectName = ' 罗刹夫人 '
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(purgeProject).toHaveBeenCalledWith(8, {
      projectName: '罗刹夫人',
      reason: '演示测试数据',
      lockVersion: 4
    })
    expect(submitButton.props('nativeType')).toBe('button')
    expect(wrapper.emitted('purged')).toEqual([[{ purgeId: 91, projectId: 8, purgeStatus: 'pending' }]])
    wrapper.unmount()
  })

  it('添加项目成员由 ElForm 角色规则门禁并通过按钮提交', async () => {
    const wrapper = mount(ProjectMemberPanel, {
      props: { projectId: 8, canManage: true, permissions: ['shotgrid:member:add'] },
      global: {
        components: formComponents,
        stubs: { ProjectModal: projectModalStub, MemberCandidateSelect: true, ProjectStatePanel: true }
      }
    })
    await flushPromises()
    wrapper.findComponent({ name: 'MemberCandidateSelect' }).vm.$emit('select', {
      userId: 21,
      userName: 'creator01',
      nickName: '制作人甲',
      deptName: '制作部'
    })
    await nextTick()
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '添加')
    form.props('model').projectRole = 'owner'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(addProjectMember).not.toHaveBeenCalled()

    form.props('model').projectRole = 'creator'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(addProjectMember).toHaveBeenCalledWith(8, { userId: 21, projectRole: 'creator' })
    expect(submitButton.props('nativeType')).toBe('button')
    wrapper.unmount()
  })

  it('编辑项目成员同样通过独立 ElForm 实例校验', async () => {
    getProjectMembers.mockResolvedValue({
      rows: [{ userId: 21, userName: 'creator01', nickName: '制作人甲', projectRole: 'creator', joinedTime: '2026-08-18T10:00:00' }]
    })
    const wrapper = mount(ProjectMemberPanel, {
      props: { projectId: 8, canManage: true, permissions: ['shotgrid:member:edit'] },
      global: {
        components: formComponents,
        stubs: { ProjectModal: projectModalStub, MemberCandidateSelect: true, ProjectStatePanel: true }
      }
    })
    await flushPromises()
    expect(wrapper.findAllComponents(ElTag).find(tag => tag.text() === '制作人员')?.props('type')).toBe('info')
    await wrapper.find('.member-actions button').trigger('click')
    await nextTick()
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '保存')
    form.props('model').projectRole = 'owner'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(updateProjectMember).not.toHaveBeenCalled()

    form.props('model').projectRole = 'director'
    await nextTick()
    await submitButton.trigger('click')
    await flushPromises()
    expect(updateProjectMember).toHaveBeenCalledWith(8, 21, { projectRole: 'director' })
    wrapper.unmount()
  })

  it('目录重试表单校验原因并在关闭时重置 Element Plus 模型', async () => {
    const wrapper = mount(ProjectStoragePanel, {
      props: { projectId: 8, canRetryProject: true },
      global: { components: formComponents, stubs: { ProjectModal: projectModalStub, ProjectStatePanel: true } }
    })
    await flushPromises()
    expect(wrapper.findAllComponents(ElTag).find(tag => tag.text() === '存储异常')?.props('type')).toBe('danger')
    await buttonByText(wrapper, '重试项目初始目录').trigger('click')
    await nextTick()
    const form = wrapper.findComponent(ElForm)
    const submitButton = buttonByText(form, '提交重试')
    await submitButton.trigger('click')
    await flushPromises()
    expect(retryProjectStorage).not.toHaveBeenCalled()

    form.props('model').reason = ' NAS 权限已经恢复 '
    await nextTick()
    await buttonByText(form, '取消').trigger('click')
    await nextTick()
    await buttonByText(wrapper, '重试项目初始目录').trigger('click')
    await nextTick()
    const reopenedForm = wrapper.findComponent(ElForm)
    expect(reopenedForm.props('model').reason).toBe('')
    reopenedForm.props('model').reason = 'NAS 权限已经恢复'
    await nextTick()
    const reopenedSubmitButton = buttonByText(reopenedForm, '提交重试')
    expect(reopenedSubmitButton.props('nativeType')).toBe('button')
    await reopenedSubmitButton.trigger('click')
    await flushPromises()
    expect(retryProjectStorage).toHaveBeenCalledWith(
      8,
      { reason: 'NAS 权限已经恢复', lockVersion: 3 },
      expect.any(String)
    )
    wrapper.unmount()
  })

  it('目录操作列表用 ElTag 区分执行状态', async () => {
    getStorageOperationPage.mockResolvedValue({
      rows: [{
        operationId: 91,
        operationStatus: 'failed',
        operationType: 'ensure_asset_directory',
        targetRelativePath: 'Assets/Environment/动力舱',
        attemptCount: 2,
        updateTime: '2026-08-18T10:10:00'
      }],
      total: 1
    })
    const wrapper = mount(ProjectStoragePanel, {
      props: { projectId: 8, canDiagnose: true },
      global: { components: formComponents, stubs: { ProjectModal: projectModalStub, ProjectStatePanel: true } }
    })
    await flushPromises()

    const failedTag = wrapper.findAllComponents(ElTag).find(tag => tag.text() === '执行失败')
    expect(failedTag?.props('type')).toBe('danger')
    expect(failedTag?.props('effect')).toBe('plain')
    wrapper.unmount()
  })
})
