import { ElAlert, ElButton, ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getMineTaskPage, getTaskDetail, startTask } from '@/api/shot-grid/tasks'
import { getMineReviewListPage, getRecentMineVersions } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { setElSelectValue } from '../helpers/elementPlus'
import TaskDetailView from '@/views/task/TaskDetailView.vue'
import TaskEditDialog from '@/views/task/components/TaskEditDialog.vue'
import WorkbenchView from '@/views/workbench/WorkbenchView.vue'

vi.mock('@/api/shot-grid/tasks', () => ({
  getMineTaskPage: vi.fn(),
  getProjectTaskPage: vi.fn(),
  getTaskDetail: vi.fn(),
  startTask: vi.fn(),
  updateTask: vi.fn()
}))
vi.mock('@/api/shot-grid/reviews', () => ({
  getMineReviewListPage: vi.fn(),
  getRecentMineVersions: vi.fn()
}))

function taskFixture(taskId = 31, overrides = {}) {
  return {
    taskId,
    taskName: `EP001-001-S${String(taskId).padStart(3, '0')} 镜头视频制作`,
    taskKind: 'shot_video',
    taskStatus: 'not_started',
    priority: 'high',
    dueDate: '2026-08-20',
    requirements: '保持冷蓝色调和稳定镜头',
    project: { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人', projectStatus: 'active' },
    assignee: { userId: 7, nickName: '杨景锋', producerCode: 'YJF', memberStatus: 'active' },
    target: {
      targetType: 'shot',
      targetId: 100 + taskId,
      targetName: `EP001-001-S${String(taskId).padStart(3, '0')}`,
      targetDescription: '休眠舱启动',
      lifecycleStatus: 'active',
      shotId: 100 + taskId,
      shotCode: `S${String(taskId).padStart(3, '0')}`
    },
    versionCount: 0,
    latestVersion: null,
    finalVersion: null,
    lockVersion: 2,
    createTime: '2026-08-11T10:00:00',
    updateTime: '2026-08-11T11:00:00',
    remark: null,
    createBy: 'director',
    updateBy: 'director',
    hasUncommittedSubmission: false,
    allowedActions: ['task.edit', 'task.assign', 'task.start'],
    ...overrides
  }
}

function installSession(permissions = []) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 7, userName: 'producer', nickName: '杨景锋' }
  session.permissions = permissions
  session.navigation = [
    { routeKey: 'projects', path: '/projects', orderNum: 2 },
    { routeKey: 'shots', path: '/shots', orderNum: 3 }
  ]
  return pinia
}

async function mountWorkbench(permissions = ['shotgrid:task:list', 'shotgrid:version:list']) {
  const pinia = installSession(permissions)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: WorkbenchView },
      { path: '/tasks/:taskId', component: { template: '<div>任务详情</div>' } },
      { path: '/projects', component: { template: '<div>项目</div>' } },
      { path: '/shots', component: { template: '<div>镜头</div>' } }
    ]
  })
  await router.push('/workbench')
  await router.isReady()
  const wrapper = mount(WorkbenchView, {
    global: { plugins: [pinia, router], components: { ElAlert, ElButton, ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElTag } }
  })
  await flushPromises()
  return { wrapper, router }
}

async function changeDatePicker(datePicker, value) {
  datePicker.vm.$emit('update:modelValue', value)
  await datePicker.vm.$nextTick()
  datePicker.findComponent({ name: 'Picker' }).vm.$emit('change', value)
  await datePicker.vm.$nextTick()
}

function findTag(wrapper, text) {
  return wrapper.findAllComponents(ElTag).find(tag => tag.text() === text)
}

async function mountDetail(path = '/tasks/31', permissions = ['shotgrid:task:query', 'shotgrid:task:start', 'shotgrid:task:edit']) {
  const pinia = installSession(permissions)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: { template: '<div>工作台</div>' } },
      { path: '/tasks/:taskId', component: TaskDetailView },
      { path: '/projects/:projectId/shots/:shotId', component: { template: '<div>镜头详情</div>' } },
      { path: '/projects/:projectId/assets/:assetId', component: { template: '<div>资产详情</div>' } }
    ]
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(TaskDetailView, {
    global: {
      plugins: [pinia, router],
      components: { ElButton, ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElTag },
      stubs: {
        VersionWorkspace: {
          props: ['taskId', 'taskKind', 'allowedActions', 'hasUncommittedSubmission', 'operationGeneration'],
          template: '<div data-testid="version-workspace" />'
        }
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('真实任务工作台', () => {
  beforeEach(() => {
    getMineTaskPage.mockResolvedValue({ rows: [taskFixture()], total: 1, hasNext: false })
    getMineReviewListPage.mockResolvedValue({ rows: [], total: 0 })
    getRecentMineVersions.mockResolvedValue({ rows: [], total: 0 })
  })

  it('展示跨项目真实任务，并提交服务端分页筛选', async () => {
    getMineReviewListPage.mockClear()
    const { wrapper, router } = await mountWorkbench()
    expect(wrapper.text()).toContain('我的制作任务')
    expect(wrapper.text()).not.toContain('其他可访问模块')
    expect(wrapper.text()).not.toContain('待我审核')
    expect(wrapper.find('.review-queue').exists()).toBe(false)
    expect(wrapper.find('.recent-submissions').exists()).toBe(true)
    expect(wrapper.find('.task-workbench').element.nextElementSibling).toBe(wrapper.find('.recent-submissions').element)
    expect(getMineReviewListPage).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('罗刹夫人')
    expect(wrapper.find('.task-row').text()).toContain('杨景锋')

    const filterForm = wrapper.findComponent(ElForm)
    expect(filterForm.props('model')).toMatchObject({
      keyword: '',
      taskKind: '',
      taskStatus: '',
      priority: '',
      dueDateRange: [],
      orderValue: 'updateTime:descending'
    })
    expect(filterForm.props('rules')).toMatchObject({
      dueDateRange: [expect.objectContaining({ trigger: 'change' })]
    })
    expect(filterForm.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual([
      'keyword',
      'taskKind',
      'taskStatus',
      'priority',
      'dueDateRange',
      'orderValue',
      undefined
    ])
    const queryButton = filterForm.findAllComponents(ElButton)
      .find(button => button.text() === '查询')
    const form = filterForm
    await form.find('input[placeholder="任务、项目、镜头或资产"]').setValue('动力舱')
    const selects = form.findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(selects[0], 'shot_video')
    await setElSelectValue(selects[1], 'revision')
    await setElSelectValue(selects[2], 'urgent')
    await queryButton.trigger('click')
    await flushPromises()

    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({
      keyword: '动力舱',
      taskKind: 'shot_video',
      taskStatus: 'revision',
      priority: 'urgent',
      pageNum: 1,
      orderByColumn: 'updateTime',
      isAsc: 'descending'
    }), expect.anything())

    await wrapper.find('.task-row').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/tasks/31')
    wrapper.unmount()
  })

  it('任务类型、状态、截止日期、优先级与最近版本使用 ElTag 动态类型', async () => {
    getMineTaskPage.mockResolvedValueOnce({ rows: [taskFixture(31, {
      taskKind: 'asset_image',
      taskStatus: 'revision',
      priority: 'urgent',
      dueDate: '2020-01-01'
    })], total: 1, hasNext: false })
    getRecentMineVersions.mockResolvedValueOnce({ rows: [{
      versionId: 91,
      versionNumber: 'V001',
      changelog: '完成首版',
      versionStatus: 'final'
    }], total: 1 })
    getMineReviewListPage.mockResolvedValueOnce({ rows: [{
      reviewListId: 101,
      reviewListName: '角色批量审核',
      projectCode: 'LCFR',
      reviewMode: 'manual_batch',
      versionCount: 3
    }], total: 1 })

    const { wrapper } = await mountWorkbench([
      'shotgrid:task:list',
      'shotgrid:version:list',
      'shotgrid:reviewList:list',
      'shotgrid:version:review'
    ])
    expect(findTag(wrapper, '1 项我的任务').props()).toMatchObject({ type: 'info', size: 'small', effect: 'plain', round: true })
    expect(findTag(wrapper, '资产').props()).toMatchObject({ type: 'primary', size: 'small', effect: 'plain', round: true })
    expect(findTag(wrapper, '待修订').props()).toMatchObject({ type: 'danger', effect: 'light', round: true })
    expect(findTag(wrapper, '2020-01-01 · 已逾期').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
    expect(findTag(wrapper, '紧急').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
    expect(findTag(wrapper, '最终版本').props()).toMatchObject({ type: 'success', effect: 'plain', round: true })
    expect(findTag(wrapper, '人工批量').props()).toMatchObject({ type: 'primary', size: 'small', effect: 'plain', round: true })
    expect(wrapper.find('.review-queue').text()).toContain('LCFR · 3 个版本')
    expect(wrapper.find('.recent-submissions').text()).toContain('V001 · 完成首版')
    expect(wrapper.find('.review-queue').element.nextElementSibling).toBe(wrapper.find('.task-workbench').element)
    expect(wrapper.find('.task-workbench').element.nextElementSibling).toBe(wrapper.find('.recent-submissions').element)
    expect(wrapper.find('.task-row__kind').exists()).toBe(false)
    expect(wrapper.find('.status-chip').exists()).toBe(false)
    expect(wrapper.find('.priority-chip').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Element Plus 筛选控件 change 后立即查询，并通过 Form 重置', async () => {
    const { wrapper } = await mountWorkbench()
    const filterForm = wrapper.findComponent(ElForm)
    const selects = filterForm.findAllComponents({ name: 'ElSelect' })
    const datePickers = filterForm.findAllComponents(ElDatePicker)
    getMineTaskPage.mockClear()

    expect(datePickers).toHaveLength(1)
    expect(datePickers[0].props()).toMatchObject({
      type: 'daterange',
      unlinkPanels: true,
      valueFormat: 'YYYY-MM-DD',
      format: 'YYYY/MM/DD',
      rangeSeparator: '至',
      startPlaceholder: '开始日期',
      endPlaceholder: '结束日期'
    })

    await setElSelectValue(selects[0], 'shot_video')
    await flushPromises()
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({ taskKind: 'shot_video', pageNum: 1 }), expect.anything())

    await setElSelectValue(selects[1], 'revision')
    await flushPromises()
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({ taskStatus: 'revision', pageNum: 1 }), expect.anything())

    await setElSelectValue(selects[2], 'urgent')
    await flushPromises()
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({ priority: 'urgent', pageNum: 1 }), expect.anything())

    await changeDatePicker(datePickers[0], ['2026-08-01', '2026-08-31'])
    await flushPromises()
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({
      dueDateFrom: '2026-08-01',
      dueDateTo: '2026-08-31',
      pageNum: 1
    }), expect.anything())

    await setElSelectValue(selects[3], 'dueDate:ascending')
    await flushPromises()
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({ orderByColumn: 'dueDate', isAsc: 'ascending', pageNum: 1 }), expect.anything())

    await filterForm.findAllComponents(ElButton).find(button => button.text() === '重置').trigger('click')
    await flushPromises()
    expect(filterForm.props('model')).toMatchObject({
      keyword: '',
      taskKind: '',
      taskStatus: '',
      priority: '',
      dueDateRange: [],
      orderValue: 'updateTime:descending',
      pageNum: 1
    })
    expect(getMineTaskPage).toHaveBeenLastCalledWith(expect.objectContaining({
      taskKind: undefined,
      taskStatus: undefined,
      priority: undefined,
      dueDateFrom: undefined,
      dueDateTo: undefined,
      orderByColumn: 'updateTime',
      isAsc: 'descending',
      pageNum: 1
    }), expect.anything())
    wrapper.unmount()
  })

  it('403 和 5xx 分流为错误态，不伪装成空任务', async () => {
    getMineTaskPage.mockRejectedValueOnce({ httpStatus: 403, message: '不是任何活动项目成员' })
    const forbidden = await mountWorkbench()
    expect(forbidden.wrapper.text()).toContain('没有任务访问权限')
    expect(forbidden.wrapper.text()).toContain('不是任何活动项目成员')
    expect(forbidden.wrapper.text()).not.toContain('当前筛选暂无任务')
    forbidden.wrapper.unmount()

    getMineTaskPage.mockRejectedValueOnce({ httpStatus: 503, message: '任务服务维护中' })
    const unavailable = await mountWorkbench()
    expect(unavailable.wrapper.text()).toContain('任务服务暂不可用')
    expect(unavailable.wrapper.text()).not.toContain('当前筛选暂无任务')
    unavailable.wrapper.unmount()
  })

  it('过期的筛选请求迟到时不能覆盖当前结果', async () => {
    let resolveOld
    getMineTaskPage.mockImplementation(params => {
      if (params.keyword === '旧查询') return new Promise(resolve => { resolveOld = resolve })
      if (params.keyword === '新查询') return Promise.resolve({ rows: [taskFixture(33, { taskName: '当前任务' })], total: 1, hasNext: false })
      return Promise.resolve({ rows: [taskFixture()], total: 1, hasNext: false })
    })
    const { wrapper } = await mountWorkbench()
    const form = wrapper.find('form[aria-label="我的任务筛选"]')
    const search = form.find('input[placeholder="任务、项目、镜头或资产"]')
    const queryButton = form.findAllComponents(ElButton)
      .find(button => button.text() === '查询')
    const taskKindSelect = wrapper.findComponent(ElForm).findAllComponents({ name: 'ElSelect' })[0]

    await search.setValue('旧查询')
    await queryButton.trigger('click')
    await vi.waitFor(() => expect(resolveOld).toBeTypeOf('function'))
    await search.setValue('新查询')
    await setElSelectValue(taskKindSelect, 'shot_video')
    await vi.waitFor(() => expect(wrapper.text()).toContain('当前任务'))

    resolveOld({ rows: [taskFixture(32, { taskName: '迟到旧任务' })], total: 1, hasNext: false })
    await flushPromises()
    expect(wrapper.text()).toContain('当前任务')
    expect(wrapper.text()).not.toContain('迟到旧任务')
    wrapper.unmount()
  })

  it('旧请求未完成时切换为无效日期范围，会取消旧上下文并拒绝迟到回写', async () => {
    let resolveOld
    getMineTaskPage.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const { wrapper } = await mountWorkbench()
    const filterForm = wrapper.findComponent(ElForm)
    const datePicker = filterForm.findComponent(ElDatePicker)
    await changeDatePicker(datePicker, ['2026-08-30', '2026-08-01'])
    await flushPromises()
    expect(filterForm.props('model').dueDateRange).toEqual(['2026-08-30', '2026-08-01'])

    const dueDateRangeItem = filterForm.find('.task-filter-item--date-range')
    await vi.waitFor(() => {
      expect(dueDateRangeItem.classes().join(' ')).toContain('is-error')
      expect(dueDateRangeItem.find('.el-form-item__error').text()).toBe('截止日期起点不能晚于终点。')
    })
    expect(getMineTaskPage).toHaveBeenCalledTimes(1)
    resolveOld({ rows: [taskFixture(88, { taskName: '迟到任务' })], total: 1 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('迟到任务')
    wrapper.unmount()
  })
})

describe('任务详情、状态动作与异步上下文', () => {
  beforeEach(() => {
    getTaskDetail.mockResolvedValue({ data: taskFixture() })
    startTask.mockResolvedValue({ data: taskFixture(31, {
      taskStatus: 'in_progress',
      lockVersion: 3,
      allowedActions: ['task.edit', 'task.assign', 'version.add']
    }) })
  })

  it('开始与编辑动作同时受 allowedActions 和平台权限双门禁', async () => {
    const { wrapper } = await mountDetail()
    expect(wrapper.text()).toContain('EP001-001-S031')
    expect(wrapper.text()).toContain('开始任务')
    expect(wrapper.text()).toContain('编辑任务')

    await wrapper.findAll('button').find(button => button.text().includes('开始任务')).trigger('click')
    await flushPromises()
    expect(startTask).toHaveBeenCalledWith(31, { lockVersion: 2 })
    expect(wrapper.text()).toContain('制作中')
    wrapper.unmount()

    getTaskDetail.mockResolvedValueOnce({ data: taskFixture(31, { allowedActions: ['task.start', 'task.edit'] }) })
    const missingPlatformPermission = await mountDetail('/tasks/31', ['shotgrid:task:query'])
    expect(missingPlatformPermission.wrapper.findAll('button').map(button => button.text())).not.toContain('开始任务')
    expect(missingPlatformPermission.wrapper.findAll('button').map(button => button.text())).not.toContain('编辑任务')
    missingPlatformPermission.wrapper.unmount()

    getTaskDetail.mockResolvedValueOnce({ data: taskFixture(31, { allowedActions: [] }) })
    const missingBackendAction = await mountDetail()
    expect(missingBackendAction.wrapper.findAll('button').map(button => button.text())).not.toContain('开始任务')
    expect(missingBackendAction.wrapper.findAll('button').map(button => button.text())).not.toContain('编辑任务')
    missingBackendAction.wrapper.unmount()
  })

  it('任务详情的状态、优先级、类型、生命周期和版本标记使用 ElTag', async () => {
    getTaskDetail.mockResolvedValueOnce({ data: taskFixture(31, {
      taskKind: 'asset_image',
      taskStatus: 'pending_review',
      priority: 'urgent',
      target: {
        targetType: 'asset_item',
        targetId: 131,
        targetName: '角色概念图',
        targetDescription: '女主角色设定',
        lifecycleStatus: 'active',
        assetId: 18,
        productionItem: '角色概念图'
      },
      latestVersion: { versionNumber: 'V002', versionStatus: 'rejected', submittedTime: '2026-08-18T10:00:00' },
      finalVersion: { versionNumber: 'V001' }
    }) })

    const { wrapper } = await mountDetail()
    expect(findTag(wrapper, '待审核').props()).toMatchObject({ type: 'warning', effect: 'light', round: true })
    expect(findTag(wrapper, '紧急优先级').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
    expect(findTag(wrapper, '资产图片').props()).toMatchObject({ type: 'primary', effect: 'plain', round: true })
    expect(findTag(wrapper, '活动').props()).toMatchObject({ type: 'success', effect: 'plain', round: true })
    expect(findTag(wrapper, '已退回').props()).toMatchObject({ type: 'danger', effect: 'light', round: true })
    expect(findTag(wrapper, '最终版本：V001').props()).toMatchObject({ type: 'success', effect: 'plain', round: true })
    wrapper.unmount()
  })

  it('404 与开始任务的 409 冲突均显示可区分状态', async () => {
    getTaskDetail.mockRejectedValueOnce({ httpStatus: 404, message: '任务已归档或不可见' })
    const missing = await mountDetail()
    expect(missing.wrapper.text()).toContain('任务不存在')
    expect(missing.wrapper.text()).toContain('任务已归档或不可见')
    missing.wrapper.unmount()

    getTaskDetail.mockResolvedValueOnce({ data: taskFixture() })
    startTask.mockRejectedValueOnce({ httpStatus: 409, errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT', message: '任务已被修改' })
    const conflict = await mountDetail()
    await conflict.wrapper.findAll('button').find(button => button.text().includes('开始任务')).trigger('click')
    await flushPromises()
    expect(conflict.wrapper.text()).toContain('任务已发生变更')
    expect(conflict.wrapper.text()).toContain('任务已被修改')
    conflict.wrapper.unmount()
  })

  it('快速切换任务路由会立即清理旧详情，并拒绝迟到响应', async () => {
    let resolveTask32
    getTaskDetail.mockImplementation(targetTaskId => {
      if (targetTaskId === 31) return Promise.resolve({ data: taskFixture(31, { taskName: '初始任务' }) })
      if (targetTaskId === 32) return new Promise(resolve => { resolveTask32 = resolve })
      return Promise.resolve({ data: taskFixture(33, { taskName: '当前任务' }) })
    })
    const { wrapper, router } = await mountDetail()
    expect(wrapper.text()).toContain('初始任务')

    await router.push('/tasks/32')
    await flushPromises()
    expect(wrapper.text()).toContain('正在加载任务详情')
    expect(wrapper.text()).not.toContain('初始任务')
    await router.push('/tasks/33')
    await flushPromises()
    expect(wrapper.text()).toContain('当前任务')

    resolveTask32({ data: taskFixture(32, { taskName: '迟到旧任务' }) })
    await flushPromises()
    expect(wrapper.text()).toContain('当前任务')
    expect(wrapper.text()).not.toContain('迟到旧任务')
    wrapper.unmount()
  })

  it('切走后返回同一任务重开编辑，旧完成事件不得关闭或刷新新实例', async () => {
    getTaskDetail.mockImplementation(targetTaskId => Promise.resolve({ data: taskFixture(targetTaskId, { taskName: targetTaskId === 31 ? '同一任务' : '中转任务' }) }))
    const { wrapper, router } = await mountDetail()
    await wrapper.findAll('button').find(button => button.text().includes('编辑任务')).trigger('click')
    const oldDialog = wrapper.findComponent(TaskEditDialog)
    const oldGeneration = oldDialog.props('operationGeneration')

    await router.push('/tasks/32')
    await flushPromises()
    await router.push('/tasks/31')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('编辑任务')).trigger('click')
    const newDialog = wrapper.findComponent(TaskEditDialog)
    const callsBefore = getTaskDetail.mock.calls.length
    expect(newDialog.props('operationGeneration')).not.toBe(oldGeneration)

    oldDialog.vm.$emit('saved', taskFixture(), { taskId: 31, projectId: 8, operationGeneration: oldGeneration })
    await flushPromises()
    expect(wrapper.findComponent(TaskEditDialog).exists()).toBe(true)
    expect(wrapper.findComponent(TaskEditDialog).props('operationGeneration')).toBe(newDialog.props('operationGeneration'))
    expect(getTaskDetail).toHaveBeenCalledTimes(callsBefore)
    wrapper.unmount()
  })
})
