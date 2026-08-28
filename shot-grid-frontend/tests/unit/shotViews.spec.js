import { ElAlert, ElButton, ElCard, ElDatePicker, ElDescriptions, ElDescriptionsItem, ElDialog, ElDrawer, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElMessageBox, ElOption, ElPagination, ElRadioButton, ElRadioGroup, ElSelect, ElTable, ElTableColumn, ElTag, ElUpload } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { startTask } from '@/api/shot-grid/tasks'
import {
  batchAssignShotTasks,
  batchDeleteShots,
  commitShotImport,
  createEpisode,
  createScene,
  createShot,
  getEpisodePage,
  getScenePage,
  getShotDetail,
  getShotPage,
  listShotAssignees,
  previewShotImport,
  assignShotTask,
  reorderShot,
  updateShot
} from '@/api/shot-grid/shots'
import { useSessionStore } from '@/store/modules/session'
import { buttonLabel, completeTaskStartForm, expectedTaskTimes, setElSelectValue } from '../helpers/elementPlus'
import ShotDetailView from '@/views/shot/ShotDetailView.vue'
import ShotListView from '@/views/shot/ShotListView.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import EpisodeSceneCreateDialog from '@/views/shot/components/EpisodeSceneCreateDialog.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'

const sortableCreate = vi.hoisted(() => vi.fn(() => ({ destroy: vi.fn() })))

vi.mock('sortablejs', () => ({ default: { create: sortableCreate } }))
vi.mock('@/api/shot-grid/tasks', () => ({ startTask: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  getProjectDetail: vi.fn(),
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/shots', () => ({
  archiveShot: vi.fn(),
  assignShotTask: vi.fn(),
  batchAssignShotTasks: vi.fn(),
  batchDeleteShots: vi.fn(),
  commitShotImport: vi.fn(),
  createEpisode: vi.fn(),
  createScene: vi.fn(),
  createShot: vi.fn(),
  downloadProtectedThumbnail: vi.fn(),
  getEpisodePage: vi.fn(),
  getScenePage: vi.fn(),
  getShotDetail: vi.fn(),
  getShotPage: vi.fn(),
  listShotAssignees: vi.fn(),
  previewShotImport: vi.fn(),
  reorderShot: vi.fn(),
  updateShot: vi.fn()
}))

const projectRow = { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人' }
const shotRow = {
  shotId: 41,
  projectId: 8,
  episodeId: 21,
  episodeNo: 1,
  episodeCode: 'EP001',
  sceneId: 31,
  sceneNo: 1,
  sceneCode: '001',
  sceneName: '动力舱',
  shotNo: 1,
  shotCode: '0001',
  storageDirName: '001_0001',
  directoryStatus: 'ready',
  durationMs: 3500,
  shotSize: '近景',
  cameraPosition: '平视',
  cameraMovement: '推进',
  focalLength: '35/25',
  description: '镜头缓慢推进动力舱',
  dialogue: '动力系统恢复了吗？',
  soundEffect: '设备低频轰鸣声',
  colorReference: '冷蓝色调',
  remark: '保持画面压迫感',
  environmentAssets: [{ assetId: 2, assetName: '动力舱', assetType: 'Environment' }],
  characterAssets: [],
  sortOrder: 1,
  sequencePosition: 1,
  status: 'in_progress',
  assignee: { userId: 7, nickName: 'YJF', producerCode: 'YJF' },
  thumbnail: null,
  latestVersion: null,
  latestFeedback: null,
  assetCount: 1,
  lockVersion: 0,
  taskLockVersion: 4,
  allowedActions: []
}

const assignableShotRow = { ...shotRow, status: 'not_started', allowedActions: ['task.assign'] }

const formComponents = { ElAlert, ElButton, ElDatePicker, ElDescriptions, ElDescriptionsItem, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElOption, ElSelect, ElUpload }

async function mountView(permissions = ['shotgrid:shot:list', 'shotgrid:shot:add', 'shotgrid:shot:import', 'shotgrid:member:list'], configureRouter = null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin', nickName: '管理员' }
  session.permissions = permissions
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/shots', component: ShotListView },
      { path: '/projects/:projectId/shots/:shotId', component: { template: '<div>镜头详情</div>' } }
    ]
  })
  configureRouter?.(router)
  await router.push('/shots?projectId=8')
  await router.isReady()
  const wrapper = mount(ShotListView, {
    global: { plugins: [pinia, router], components: { ...formComponents, ElCard, ElDialog, ElDrawer, ElPagination, ElRadioButton, ElRadioGroup, ElTable, ElTableColumn, ElTag } }
  })
  await flushPromises()
  await flushPromises()
  return { wrapper, router }
}

async function mountDetailView(path = '/projects/8/shots/41') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/shots', component: { template: '<div>镜头列表</div>' } },
      { path: '/projects/:projectId/shots/:shotId', component: ShotDetailView }
    ]
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ShotDetailView, {
    global: {
      plugins: [router],
      components: { ...formComponents, ElDialog, ElTag },
      stubs: { ProductionHistoryPanel: true }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

function findTag(wrapper, text) {
  return wrapper.findAllComponents(ElTag).find(tag => tag.text() === text)
}

function shotRowCheckboxes(wrapper) {
  return wrapper.find('.shot-data-table').findAll('.el-table__body-wrapper tbody tr')
    .map(row => row.find('input[type="checkbox"]'))
}

function shotHeaderCheckbox(wrapper) {
  return wrapper.find('.shot-data-table .el-table__header-wrapper input[type="checkbox"]')
}

function selectedTableShots(wrapper) {
  return wrapper.findComponent(ElTable).vm.$.exposed.getSelectionRows()
}

async function setShotHeaderSelection(wrapper, selected) {
  const table = wrapper.findComponent(ElTable)
  const previousEvents = table.emitted('select-all')?.length || 0
  await shotHeaderCheckbox(wrapper).setValue(selected)
  // Element Plus 表头全选有 10ms 防抖，等待真实选择事件而不是只等待 Vue 更新。
  if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(10)
  await vi.waitFor(() => expect(table.emitted('select-all')?.length).toBe(previousEvents + 1))
  await flushPromises()
}

function shotDetail(projectId, shotId, shotCode, description) {
  return {
    ...shotRow,
    projectId,
    shotId,
    shotCode,
    description,
    dialogue: null,
    soundEffect: null,
    colorReference: null,
    remark: null,
    assets: [],
    task: null,
    status: 'unassigned',
    createBy: 'director',
    createTime: '2026-08-11T10:00:00',
    updateBy: 'director',
    updateTime: '2026-08-11T10:00:00',
    allowedActions: ['shot.edit', 'shot.archive', 'task.assign']
  }
}

describe('镜头管理真实列表页', () => {
  beforeEach(() => {
    sortableCreate.mockClear()
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director' } })
    getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 21, episodeNo: 1, episodeCode: 'EP001', episodeName: '第一集', sortOrder: 10 }], total: 1, hasNext: false })
    getScenePage.mockResolvedValue({ rows: [{ sceneId: 31, sceneNo: 1, sceneCode: '001', sceneName: '动力舱', sortOrder: 10 }], total: 1, hasNext: false })
    listShotAssignees.mockResolvedValue({ rows: [{ userId: 7, userName: '杨景锋', nickName: 'YJF', projectRole: 'creator', producerCode: 'YJF' }], total: 1, hasNext: false })
    getShotPage.mockResolvedValue({ rows: [shotRow], total: 1, hasNext: false })
    getShotDetail.mockResolvedValue({ data: shotDetail(8, 41, '0001', '镜头缓慢推进动力舱') })
    batchAssignShotTasks.mockResolvedValue({ data: { assignedShotIds: [41], assignedCount: 1 } })
    batchDeleteShots.mockResolvedValue({ data: { deletedShotIds: [41], deletedCount: 1 } })
    createEpisode.mockReset()
    createScene.mockReset()
    createEpisode.mockResolvedValue({ data: { episodeId: 22, episodeNo: 2, episodeCode: 'EP002' } })
    createScene.mockResolvedValue({ data: { sceneId: 32, episodeId: 21, sceneNo: 2, sceneCode: '002' } })
    reorderShot.mockResolvedValue({ data: { shotId: 41, sequencePosition: 1, lockVersion: 1 } })
  })

  it('镜头表格向只读制作人显示双时间与独立时间状态，空时间不伪造', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-28T12:00:00'))
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'creator' } })
    getShotPage.mockResolvedValue({ rows: [
      { ...shotRow, expectedStartTime: '2026-08-28T09:30:00', expectedEndTime: '2026-08-30T18:00:00' },
      { ...shotRow, shotId: 42, expectedStartTime: '2026-08-28T10:00:00', expectedEndTime: '2026-08-29T12:00:00' },
      { ...shotRow, shotId: 43, expectedStartTime: '2026-08-27T09:00:00', expectedEndTime: '2026-08-28T12:00:00' },
      { ...shotRow, shotId: 44, expectedStartTime: null, expectedEndTime: null },
      { ...shotRow, shotId: 45, status: 'completed', expectedStartTime: '2026-08-27T09:00:00', expectedEndTime: '2026-08-28T10:00:00' }
    ], total: 5 })
    let wrapper
    try {
      ;({ wrapper } = await mountView(['shotgrid:shot:list']))
      const headers = wrapper.findAll('.el-table__header-wrapper th').map(cell => cell.text())
      expect(headers).toEqual(expect.arrayContaining(['开始时间', '结束时间', '时间状态']))
      const rows = wrapper.findAll('.shot-data-table .el-table__body-wrapper tbody tr')
      expect(rows[0].find('.task-expected-start').text()).toBe('2026/08/28 09:30')
      expect(rows[0].find('.task-expected-end').text()).toBe('2026/08/30 18:00')
      expect(rows.map(row => row.find('.task-time-state').text())).toEqual(['正常', '临近结束', '已延期', '未设置时间', '已完成'])
      expect(rows[3].find('.task-expected-start').text()).toBe('—')
      expect(rows[3].find('.task-expected-end').text()).toBe('—')
    } finally { wrapper?.unmount(); vi.useRealTimers() }
  })

  it.each([false, true])('镜头行直接进入分配表单并保留任务锁版本：已有任务=%s', async withTask => {
    const row = { ...assignableShotRow, status: withTask ? 'not_started' : 'unassigned', taskLockVersion: withTask ? 6 : null, assignee: withTask ? shotRow.assignee : null }
    const task = withTask ? { taskId: 71, lockVersion: 6, assignee: { userId: 7 }, priority: 'normal' } : null
    getShotPage.mockResolvedValue({ rows: [row], total: 1 })
    getShotDetail.mockResolvedValue({ data: { ...row, task, allowedActions: ['task.assign'] } })
    assignShotTask.mockReset().mockResolvedValue({ data: { taskId: 71 } })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:assign'])
    try {
      const label = withTask ? '改派任务' : '分配任务'
      const actions = wrapper.find('.shot-row-actions')
      const button = actions.findAll('button').find(item => buttonLabel(item) === label)
      expect(button).toBeDefined()
      for (const action of actions.findAllComponents(ElButton)) {
        expect(action.props('size')).toBe('small')
        expect(action.attributes('aria-label')).toBeTruthy()
        expect(action.find('svg').exists()).toBe(true)
        expect(action.text()).toBe(action.attributes('aria-label'))
        expect(action.props('circle')).toBe(false)
        expect(action.props()).toMatchObject({ round: true, plain: true })
        expect(action.classes()).not.toContain('is-text')
      }
      await button.trigger('click')
      await flushPromises()
      const dialog = wrapper.findComponent(ShotAssignDialog)
      expect(dialog.exists()).toBe(true)
      expect(dialog.props('shot').shotId).toBe(41)
      expect(wrapper.findComponent(ShotDetailView).exists()).toBe(false)
      await setElSelectValue(dialog.findComponent(ElSelect), '7')
      await dialog.findAllComponents(ElButton).find(item => buttonLabel(item) === (withTask ? '确认改派' : '创建并分配任务')).trigger('click')
      await flushPromises()
      expect(assignShotTask).toHaveBeenCalledWith(8, 41, withTask ? { assigneeUserId: 7, taskLockVersion: 6 } : { assigneeUserId: 7 })
      expect(wrapper.findComponent(ShotAssignDialog).exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('开工窗口展示制作人、完整内容及预期时间范围，未填写不能开工', async () => {
    const row = { ...shotRow, status: 'not_started', taskId: 71, taskLockVersion: 3, lockVersion: 2, allowedActions: ['task.start'] }
    getShotPage.mockResolvedValue({ rows: [row], total: 1 })
    getShotDetail.mockResolvedValue({ data: { ...row, task: { taskId: 71, lockVersion: 3, priority: 'high', assignee: row.assignee } } })
    startTask.mockReset().mockResolvedValue({ data: { taskStatus: 'preparing' } })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:start'])
    try {
      await wrapper.findAllComponents(ElButton).find(item => buttonLabel(item) === '开始任务').trigger('click')
      await flushPromises()
      const dialog = wrapper.findComponent({ name: 'TaskStartDialog' })
      expect(dialog.exists()).toBe(true)
      expect(dialog.findComponent(ElDatePicker).props('type')).toBe('datetimerange')
      expect(document.body.textContent).toContain('杨景锋')
      await dialog.findAllComponents(ElButton).find(item => buttonLabel(item) === '确认开工').trigger('click')
      await flushPromises()
      expect(startTask).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it('镜头行分配操作重新检查服务端权限并隔离切换项目后的迟到详情', async () => {
    getShotPage.mockResolvedValue({ rows: [assignableShotRow], total: 1 })
    getProjectPage.mockResolvedValue({ rows: [projectRow, { ...projectRow, projectId: 9, projectName: '新项目' }], total: 2 })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:assign'])
    getShotDetail.mockResolvedValueOnce({ data: { ...shotRow, allowedActions: [] } })
    try {
      const button = wrapper.find('.shot-row-actions').findAll('button').find(item => buttonLabel(item) === '改派任务')
      expect(button).toBeDefined()
      await button.trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(ShotAssignDialog).exists()).toBe(false)
      let finish
      getShotDetail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      await wrapper.find('.shot-row-actions').findAll('button').find(item => buttonLabel(item) === '改派任务').trigger('click')
      const signal = getShotDetail.mock.calls.at(-1)[2].signal
      await setElSelectValue(wrapper.find('.project-context').findComponent(ElSelect), '9')
      await flushPromises()
      finish({ data: { ...shotRow, allowedActions: ['task.assign'] } })
      await flushPromises()
      expect(signal.aborted).toBe(true)
      expect(wrapper.findComponent(ShotAssignDialog).exists()).toBe(false)
    } finally { wrapper.unmount() }
  })

  it('原生表格选择同步批量操作，表头全选跳过不能操作的镜头', async () => {
    getShotPage.mockResolvedValue({ rows: [
      assignableShotRow,
      { ...assignableShotRow, shotId: 42, shotCode: '0002' },
      { ...shotRow, shotId: 43, shotCode: '0003', status: 'completed' }
    ], total: 3 })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:task:assign'])
    try {
      const checkboxes = shotRowCheckboxes(wrapper)
      expect(checkboxes.map(checkbox => checkbox.element.disabled)).toEqual([false, false, true])
      await checkboxes[0].setValue(true)
      await flushPromises()
      expect(selectedTableShots(wrapper).map(row => row.shotId)).toEqual([41])
      expect(wrapper.text()).toContain('批量重新分配（1）')
      expect(shotHeaderCheckbox(wrapper).element.indeterminate).toBe(true)

      await setShotHeaderSelection(wrapper, true)
      expect(selectedTableShots(wrapper).map(row => row.shotId)).toEqual([41, 42])
      expect(wrapper.text()).toContain('批量重新分配（2）')
      expect(checkboxes[2].element.checked).toBe(false)

      await setShotHeaderSelection(wrapper, false)
      expect(selectedTableShots(wrapper)).toEqual([])
      expect(wrapper.text()).not.toContain('批量重新分配')
    } finally {
      wrapper.unmount()
    }
  })

  it.each([
    ['preparing', []], ['in_progress', []], ['reviewing', []], ['revision', []], ['completed', []],
    ['not_started', undefined]
  ])('镜头 %s 缺少改派权限投影时不显示入口且不能批量选择', async (status, allowedActions) => {
    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status, allowedActions }], total: 1 })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:assign'])
    try {
      expect(wrapper.find('.shot-row-actions').findAll('button').map(buttonLabel)).not.toContain('改派任务')
      expect(shotRowCheckboxes(wrapper)[0].element.disabled).toBe(true)
      await setShotHeaderSelection(wrapper, true)
      expect(selectedTableShots(wrapper)).toEqual([])
    } finally { wrapper.unmount() }
  })

  it('没有批量操作权限时行选择禁用，表头全选不会选中镜头', async () => {
    const { wrapper } = await mountView(['shotgrid:shot:list'])
    expect(shotRowCheckboxes(wrapper)[0].element.disabled).toBe(true)
    await setShotHeaderSelection(wrapper, true)
    expect(selectedTableShots(wrapper)).toEqual([])
    wrapper.unmount()
  })

  it('表格刷新使用加载遮罩，空结果由表格空态展示', async () => {
    const { wrapper } = await mountView()
    let resolvePage
    try {
      getShotPage.mockImplementationOnce(() => new Promise(resolve => { resolvePage = resolve }))
      await wrapper.find('button[aria-label="刷新镜头"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('.shot-data-table .el-loading-mask').exists()).toBe(true)
      resolvePage({ rows: [], total: 0 })
      await flushPromises()
      expect(wrapper.find('.shot-data-table .el-table__empty-text').text()).toContain('当前筛选没有镜头')
      expect(wrapper.find('.shot-data-table .el-table__empty-text').text()).toContain('可以调整集、场次、状态或制作人筛选')
    } finally {
      resolvePage?.({ rows: [], total: 0 })
      wrapper.unmount()
    }
  })

  it('列表自动刷新移除已开工和消失的选择，待开工镜头继续低频查询', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getShotPage.mockResolvedValueOnce({ rows: [
      { ...shotRow, status: 'preparing' },
      { ...assignableShotRow, shotId: 42, shotCode: '0002' },
      { ...assignableShotRow, shotId: 43, shotCode: '0003' }
    ], total: 3 })
    getShotPage.mockResolvedValue({ rows: [
      { ...shotRow, description: '轮询后的最新镜头内容' },
      { ...assignableShotRow, shotId: 42, shotCode: '0002' }
    ], total: 2 })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:task:assign'])
    try {
      expect(findTag(wrapper, '目录准备中')).toBeDefined()
      await setShotHeaderSelection(wrapper, true)
      expect(wrapper.text()).toContain('批量重新分配（2）')
      const calls = getShotPage.mock.calls.length
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(wrapper.find('.shot-data-table .el-loading-mask').exists()).toBe(false)
      expect(getShotPage).toHaveBeenCalledTimes(calls + 1)
      expect(findTag(wrapper, '制作中')).toBeDefined()
      expect(findTag(wrapper, '目录准备中')).toBeUndefined()
      expect(shotRowCheckboxes(wrapper).map(checkbox => checkbox.element.checked)).toEqual([false, true])
      expect(selectedTableShots(wrapper)).toEqual([
        expect.objectContaining({ shotId: 42 })
      ])
      expect(wrapper.text()).toContain('批量重新分配（1）')
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(getShotPage).toHaveBeenCalledTimes(calls + 2)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it.each(['查询', '分页', '项目', '视图'])('%s 切换立即清空表格选择，响应返回后不恢复旧选择', async (changeType) => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2 })
    getShotPage.mockResolvedValue({ rows: [assignableShotRow], total: 201, hasNext: true })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:task:assign'])
    let resolvePage
    try {
      await shotRowCheckboxes(wrapper)[0].setValue(true)
      await flushPromises()
      expect(wrapper.text()).toContain('批量重新分配（1）')
      getShotPage.mockImplementationOnce(() => new Promise(resolve => { resolvePage = resolve }))
      if (changeType === '查询') {
        await wrapper.find('.shot-filters input').setValue('动力舱')
        await wrapper.find('.shot-filters').findAllComponents(ElButton).find(button => buttonLabel(button) === '查询').trigger('click')
      } else if (changeType === '分页') {
        await wrapper.find('.shot-pagination .btn-next').trigger('click')
      } else if (changeType === '项目') {
        await setElSelectValue(wrapper.find('.project-context').findComponent(ElSelect), '9')
      } else {
        await wrapper.findAllComponents(ElRadioButton).find(button => buttonLabel(button) === '卡片').find('input[type="radio"]').setValue(true)
      }
      await flushPromises()
      expect(wrapper.text()).not.toContain('批量重新分配')
      if (wrapper.findComponent(ElTable).exists()) {
        expect(selectedTableShots(wrapper)).toEqual([])
      }
      resolvePage({ rows: [{ ...assignableShotRow, projectId: changeType === '项目' ? 9 : 8 }], total: 201, hasNext: true })
      await flushPromises()
      if (changeType === '视图') {
        await wrapper.findAllComponents(ElRadioButton).find(button => buttonLabel(button) === '表格').find('input[type="radio"]').setValue(true)
        await flushPromises()
      }
      expect(shotRowCheckboxes(wrapper)[0].element.checked).toBe(false)
      expect(selectedTableShots(wrapper)).toEqual([])
      expect(wrapper.text()).not.toContain('批量重新分配')
    } finally {
      resolvePage?.({ rows: [], total: 0 })
      wrapper.unmount()
    }
  })

  it('列表自动刷新不会提交未确认的搜索词，查询后沿用当前筛选', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status: 'preparing' }], total: 1 })
    const { wrapper } = await mountView()
    try {
      const form = wrapper.find('.shot-filters')
      await form.find('input').setValue('动力舱')
      const calls = getShotPage.mock.calls.length
      await vi.advanceTimersByTimeAsync(5000)
      expect(getShotPage).toHaveBeenCalledTimes(calls)
      await form.findAllComponents(ElButton).find(button => buttonLabel(button) === '查询').trigger('click')
      await flushPromises()
      getShotPage.mockResolvedValue({ rows: [shotRow], total: 1 })
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(getShotPage).toHaveBeenCalledTimes(calls + 2)
      expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ keyword: '动力舱', pageNum: 1 }), expect.anything())
      expect(form.find('input').element.value).toBe('动力舱')
      expect(findTag(wrapper, '制作中')).toBeDefined()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('列表自动刷新在开始加载编辑弹窗时即中止，不替换编辑快照', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status: 'not_started' }], total: 1 })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:edit'])
    let resolvePoll
    let resolveDetail
    try {
      getShotPage.mockImplementationOnce(() => new Promise(resolve => { resolvePoll = resolve }))
      await vi.advanceTimersByTimeAsync(5000)
      const signal = getShotPage.mock.lastCall[2].signal
      getShotDetail.mockImplementationOnce(() => new Promise(resolve => { resolveDetail = resolve }))
      await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '编辑').trigger('click')
      expect(signal.aborted).toBe(true)
      resolveDetail({ data: { ...shotDetail(8, 41, '0001', '正在编辑的内容'), status: 'not_started', lockVersion: 3 } })
      await flushPromises()
      const calls = getShotPage.mock.calls.length
      resolvePoll({ rows: [{ ...shotRow, lockVersion: 4 }], total: 1 })
      await vi.advanceTimersByTimeAsync(10000)
      await flushPromises()
      expect(getShotPage).toHaveBeenCalledTimes(calls)
      expect(wrapper.findComponent(ShotFormDialog).props('shot')).toMatchObject({ description: '正在编辑的内容', lockVersion: 3 })
      expect(findTag(wrapper, '待开工')).toBeDefined()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('列表自动刷新切项目再返回时丢弃旧响应，卸载后中止请求', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const project9 = { projectId: 9, projectCode: 'NEW', projectName: '新项目' }
    getProjectPage.mockResolvedValue({ rows: [projectRow, project9], total: 2 })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      ...(Number(projectId) === 8 ? projectRow : project9), projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status: 'preparing' }], total: 1 })
    const { wrapper } = await mountView()
    let resolveOld
    let resolveUnmounted
    try {
      getShotPage.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      await vi.advanceTimersByTimeAsync(1500)
      const oldSignal = getShotPage.mock.lastCall[2].signal
      const projectSelect = wrapper.find('.project-context').findAllComponents(ElSelect)[0]
      await setElSelectValue(projectSelect, '9')
      await flushPromises()
      await setElSelectValue(projectSelect, '8')
      await flushPromises()
      expect(oldSignal.aborted).toBe(true)
      resolveOld({ rows: [{ ...shotRow, description: '迟到的旧项目内容' }], total: 1 })
      await flushPromises()
      expect(wrapper.text()).not.toContain('迟到的旧项目内容')
      expect(findTag(wrapper, '目录准备中')).toBeDefined()
      getShotPage.mockImplementationOnce(() => new Promise(resolve => { resolveUnmounted = resolve }))
      await vi.advanceTimersByTimeAsync(1500)
      const signal = getShotPage.mock.lastCall[2].signal
      wrapper.unmount()
      expect(signal.aborted).toBe(true)
      const calls = getShotPage.mock.calls.length
      resolveUnmounted({ rows: [shotRow], total: 1 })
      await vi.advanceTimersByTimeAsync(10000)
      expect(getShotPage).toHaveBeenCalledTimes(calls)
    } finally {
      if (wrapper.exists()) wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it.each([
    ['table', 'confirm'], ['table', 'cancel'],
    ['card', 'confirm'], ['card', 'cancel'],
    ['storyboard', 'confirm'], ['storyboard', 'cancel']
  ])('%s 视图镜头开工先确认人工核对结果，选择 %s 后按预期处理', async (viewMode, action) => {
    startTask.mockReset()
    startTask.mockResolvedValue({ data: { taskId: 71, taskStatus: 'preparing', lockVersion: 5 } })
    getShotPage.mockResolvedValue({ rows: [{
      ...shotRow, taskId: 71, status: 'not_started', allowedActions: ['task.start'],
      assignee: { userId: 7, userName: '杨景锋', nickName: 'YJF', producerCode: 'YJF' }
    }], total: 1, hasNext: false })
    getShotDetail.mockResolvedValue({ data: { ...shotRow, allowedActions: ['task.start'], task: { taskId: 71, lockVersion: 4, priority: 'normal' } } })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:start'])
    try {
      wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', viewMode)
      await flushPromises()
      const detailCalls = getShotDetail.mock.calls.length
      const button = wrapper.findAllComponents(ElButton).find(item => buttonLabel(item) === '开始任务')
      expect(button).toBeDefined()
      expect(button.props('size')).toBe('small')
      await button.trigger('click')
      await flushPromises()
      expect(getShotDetail).toHaveBeenCalledTimes(detailCalls + 1)
      expect(document.body.textContent).toContain('资产')
      expect(document.body.textContent).toContain('杨景锋')
      await completeTaskStartForm(wrapper, action)
      if (action === 'confirm') {
        expect(startTask).toHaveBeenCalledTimes(1)
        expect(startTask).toHaveBeenCalledWith(71, {
          lockVersion: 4, shotLockVersion: 0, assetsConfirmed: true, ...expectedTaskTimes
        })
      } else {
        expect(startTask).not.toHaveBeenCalled()
      }
    } finally {
      wrapper.unmount()
    }
  })

  it.each(['platform', 'backend', 'creator'])('缺少 %s 开工授权时不显示镜头开始按钮', async missing => {
    getShotPage.mockResolvedValue({ rows: [{
      ...shotRow, taskId: 71, status: 'not_started',
      allowedActions: missing === 'backend' ? [] : ['task.start']
    }], total: 1, hasNext: false })
    if (missing === 'creator') getProjectDetail.mockResolvedValue({ data: {
      ...projectRow, projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'creator'
    } })
    const { wrapper } = await mountView(missing === 'platform'
      ? ['shotgrid:shot:list'] : ['shotgrid:shot:list', 'shotgrid:task:start'])
    try {
      expect(wrapper.findAllComponents(ElButton).map(buttonLabel)).not.toContain('开始任务')
    } finally {
      wrapper.unmount()
    }
  })

  it('开工确认防重复点击，切走并返回同一项目后旧确认不得提交', async () => {
    startTask.mockReset()
    const project9 = { projectId: 9, projectCode: 'NEW', projectName: '新项目' }
    getProjectPage.mockResolvedValue({ rows: [projectRow, project9], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      ...(Number(projectId) === 8 ? projectRow : project9),
      projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    getShotPage.mockImplementation(projectId => Promise.resolve({ rows: [{
      ...shotRow, projectId: Number(projectId), taskId: 71, status: 'not_started', allowedActions: ['task.start']
    }], total: 1, hasNext: false }))
    getShotDetail.mockResolvedValue({ data: { ...shotRow, allowedActions: ['task.start'], task: { taskId: 71, lockVersion: 4 } } })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:start'])
    try {
      const button = wrapper.findAllComponents(ElButton).find(item => buttonLabel(item) === '开始任务')
      await button.trigger('click')
      await button.trigger('click')
      await flushPromises()
      expect(getShotDetail).toHaveBeenCalledTimes(1)
      const oldDialog = wrapper.findComponent({ name: 'TaskStartDialog' })
      expect(oldDialog.exists()).toBe(true)
      const projectSelect = wrapper.find('.project-context').findAllComponents(ElSelect)[0]
      await setElSelectValue(projectSelect, '9')
      await flushPromises()
      await setElSelectValue(projectSelect, '8')
      await flushPromises()
      expect(wrapper.findComponent({ name: 'TaskStartDialog' }).exists()).toBe(false)
      oldDialog.vm.$emit('started', { data: { taskStatus: 'preparing' } })
      await flushPromises()
      expect(startTask).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('旧项目开工请求完成后不刷新或覆盖新项目镜头', async () => {
    startTask.mockReset()
    let resolveStart
    startTask.mockImplementation(() => new Promise(resolve => { resolveStart = resolve }))
    const project9 = { projectId: 9, projectCode: 'NEW', projectName: '新项目' }
    getProjectPage.mockResolvedValue({ rows: [projectRow, project9], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      ...(Number(projectId) === 8 ? projectRow : project9),
      projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    getShotPage.mockImplementation(projectId => Promise.resolve({ rows: [{
      ...shotRow, projectId: Number(projectId), taskId: 71, status: 'not_started',
      description: Number(projectId) === 9 ? '新项目镜头' : '原项目镜头', allowedActions: ['task.start']
    }], total: 1, hasNext: false }))
    getShotDetail.mockResolvedValue({ data: { ...shotRow, allowedActions: ['task.start'], task: { taskId: 71, lockVersion: 4 } } })
    const { wrapper } = await mountView(['shotgrid:shot:list', 'shotgrid:shot:query', 'shotgrid:task:start'])
    try {
      const button = wrapper.findAllComponents(ElButton).find(item => buttonLabel(item) === '开始任务')
      await button.trigger('click')
      await flushPromises()
      await completeTaskStartForm(wrapper)
      expect(button.props('disabled')).toBe(true)
      await button.trigger('click')
      expect(startTask).toHaveBeenCalledTimes(1)
      await setElSelectValue(wrapper.find('.project-context').findAllComponents(ElSelect)[0], '9')
      await flushPromises()
      const calls = getShotPage.mock.calls.length
      resolveStart({ data: { taskId: 71, taskStatus: 'preparing', lockVersion: 5 } })
      await flushPromises()
      expect(getShotPage).toHaveBeenCalledTimes(calls)
      expect(wrapper.text()).toContain('新项目镜头')
      expect(wrapper.text()).not.toContain('原项目镜头')
    } finally {
      wrapper.unmount()
    }
  })

  it('在项目范围内展示同一真实结果的三种视图与写入入口', async () => {
    const { wrapper } = await mountView()
    const projectForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('project-context'))
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('shot-filters'))
    expect(projectForm.props('model')).toMatchObject({ projectId: '8', scope: '' })
    expect(projectForm.props('rules')).toHaveProperty('projectId')
    expect(projectForm.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual(['projectId'])
    expect(filterForm.props('model')).toMatchObject({ keyword: '', episodeId: '', sceneId: '', shotStatus: '', assigneeUserId: '' })
    expect(filterForm.props('rules')).toMatchObject({
      keyword: expect.any(Array),
      episodeId: expect.any(Array),
      sceneId: expect.any(Array),
      shotStatus: expect.any(Array),
      assigneeUserId: expect.any(Array)
    })
    expect(filterForm.findAllComponents(ElFormItem)).toHaveLength(6)
    const queryButton = filterForm.findAllComponents(ElButton).find(button => buttonLabel(button) === '查询')
    expect(queryButton.props('nativeType')).toBe('button')
    getShotPage.mockClear()
    await queryButton.trigger('click')
    await flushPromises()
    expect(getShotPage).toHaveBeenCalledWith(8, expect.objectContaining({ pageNum: 1 }), expect.anything())
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')
    expect(wrapper.find('.shot-identity strong').text()).toBe('EP001 / 001 / 0001')
    expect(wrapper.find('.shot-identity small').text()).toBe('本场第 1 镜 · 3.5 秒')
    expect(wrapper.text()).toContain('镜头缓慢推进动力舱')
    expect(wrapper.text()).toContain('台词 / 对白')
    expect(wrapper.text()).toContain('动力系统恢复了吗？')
    expect(wrapper.text()).toContain('设备低频轰鸣声')
    expect(wrapper.text()).toContain('冷蓝色调')
    expect(wrapper.text()).toContain('保持画面压迫感')
    expect(wrapper.find('.shot-table-wrap').text()).toContain('杨景锋')
    const tableColumns = wrapper.findAllComponents(ElTableColumn)
    const rightFixedColumns = tableColumns.filter(column => column.props('fixed') === 'right')
    expect(rightFixedColumns.map(column => column.props('label'))).toEqual(['时间状态', '制作人', '状态', '操作'])
    expect(tableColumns.slice(-3).map(column => column.props('label'))).toEqual(['制作人', '状态', '操作'])
    expect(wrapper.text()).toContain('导入 Excel')
    expect(wrapper.text()).toContain('新建镜头')
    expect(findTag(wrapper, '场景 · 动力舱').props()).toMatchObject({ type: 'primary', size: 'small', effect: 'plain', round: true })
    expect(findTag(wrapper, '制作中').props()).toMatchObject({ type: 'primary', effect: 'light', round: true })
    expect(findTag(wrapper, '制作中').classes()).toContain('shot-status-tag--in_progress')
    expect(wrapper.find('.shot-table-wrap').text()).not.toContain('目录已就绪')
    expect(wrapper.find('.shot-chip').exists()).toBe(false)

    const viewSwitch = wrapper.findComponent(ElRadioGroup)
    viewSwitch.vm.$emit('update:modelValue', 'card')
    await flushPromises()
    expect(wrapper.find('.shot-card').exists()).toBe(true)
    expect(wrapper.find('.shot-card h3').text()).toBe('0001 · 第 1 镜')
    expect(wrapper.find('.shot-card header small').text()).toBe('EP001 / 001')
    viewSwitch.vm.$emit('update:modelValue', 'storyboard')
    await flushPromises()
    expect(wrapper.find('.story-frame').exists()).toBe(true)
    expect(wrapper.find('.story-frame__index').text()).toBe('01')
    expect(wrapper.find('.story-frame strong').text()).toBe('EP001 · 001 · 0001')
    expect(wrapper.find('.story-frame small').text()).toContain('本场第 1 镜 · 3.5 秒')
    wrapper.unmount()
  })

  it('项目存储状态使用统一映射并覆盖迁移中标签', async () => {
    getProjectDetail.mockResolvedValueOnce({ data: {
      ...projectRow,
      projectTypeName: 'AI 影视短片',
      aspectRatio: '16:9',
      projectStatus: 'active',
      storageStatus: 'migrating',
      myProjectRole: 'director'
    } })

    const { wrapper } = await mountView()
    expect(findTag(wrapper, '存储迁移中').props()).toMatchObject({
      type: 'warning',
      size: 'small',
      effect: 'plain',
      round: true
    })
    wrapper.unmount()
  })

  it('单场无附加筛选时通过表格拖拽调用专用场内重排接口', async () => {
    const mutableShot = {
      ...shotRow,
      status: 'unassigned',
      assignee: null,
      storageDirName: null,
      directoryStatus: 'not_created',
      latestVersion: null
    }
    const secondShot = { ...mutableShot, shotId: 42, shotNo: 2, shotCode: '0002', sequencePosition: 2 }
    getShotPage.mockResolvedValue({ rows: [mutableShot, secondShot], total: 2, hasNext: false })
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    expect(wrapper.text()).toContain('请选择具体场次后可排序')
    expect(sortableCreate).not.toHaveBeenCalled()

    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    await flushPromises()

    expect(sortableCreate).toHaveBeenCalled()
    const options = sortableCreate.mock.calls.at(-1)[1]
    expect(options).toMatchObject({
      forceFallback: true,
      fallbackOnBody: true,
      fallbackTolerance: 3
    })
    await options.onEnd({ oldIndex: 0, newIndex: 1 })

    expect(reorderShot).toHaveBeenCalledWith(8, 41, {
      lockVersion: 0,
      sequencePosition: 2
    })
    wrapper.unmount()
  })

  it('历史镜头号不连续时失败关闭排序入口', async () => {
    getShotPage.mockResolvedValue({
      rows: [
        { ...shotRow, status: 'unassigned', shotNo: 2, shotCode: '0002', sequencePosition: 2 },
        { ...shotRow, shotId: 42, status: 'unassigned', shotNo: 4, shotCode: '0004', sequencePosition: 4 }
      ],
      total: 2,
      hasNext: false
    })
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('当前场次镜头号不连续，请先完成历史数据治理后再排序')
    expect(wrapper.find('.shot-drag-handle').exists()).toBe(false)
    expect(sortableCreate).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('移动区间存在冻结目录时不提交重排', async () => {
    const firstShot = {
      ...shotRow,
      status: 'unassigned',
      assignee: null,
      storageDirName: null,
      directoryStatus: 'not_created',
      latestVersion: null
    }
    const frozenShot = {
      ...firstShot,
      shotId: 42,
      shotNo: 2,
      shotCode: '0002',
      sequencePosition: 2,
      storageDirName: '001_0002',
      directoryStatus: 'ready'
    }
    const thirdShot = { ...firstShot, shotId: 43, shotNo: 3, shotCode: '0003', sequencePosition: 3 }
    getShotPage.mockResolvedValue({ rows: [firstShot, frozenShot, thirdShot], total: 3, hasNext: false })
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    await flushPromises()

    const options = sortableCreate.mock.calls.at(-1)[1]
    await options.onEnd({ oldIndex: 0, newIndex: 2 })

    expect(reorderShot).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('0002：该镜头目录已冻结，不能调整顺序')
    expect(wrapper.findAll('.shot-identity').map(row => row.text())).toEqual([
      expect.stringContaining('0001'),
      expect.stringContaining('0002'),
      expect.stringContaining('0003')
    ])
    wrapper.unmount()
  })

  it('具体场次超过一页时先加载整场，再按整场位置拖拽', async () => {
    const sceneShots = Array.from({ length: 25 }, (_value, index) => ({
      ...shotRow,
      shotId: 100 + index,
      shotNo: index + 1,
      shotCode: String(index + 1).padStart(4, '0'),
      sequencePosition: index + 1,
      sortOrder: (index + 1) * 10,
      storageDirName: null,
      directoryStatus: 'not_created',
      status: 'unassigned',
      assignee: null,
      lockVersion: index
    }))
    getShotPage.mockImplementation((_projectId, params) => {
      if (!params.sceneId) return Promise.resolve({ rows: [shotRow], total: 1, hasNext: false })
      if (params.pageSize === 100) return Promise.resolve({ rows: sceneShots, total: 25, hasNext: false })
      return Promise.resolve({ rows: sceneShots.slice(0, 20), total: 25, hasNext: true })
    })
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    await flushPromises()

    expect(wrapper.findAll('.shot-identity')).toHaveLength(25)
    expect(wrapper.findComponent(ElPagination).exists()).toBe(false)
    expect(sortableCreate).toHaveBeenCalled()
    const options = sortableCreate.mock.calls.at(-1)[1]
    await options.onEnd({ oldIndex: 0, newIndex: 24 })

    expect(reorderShot).toHaveBeenCalledWith(8, 100, {
      lockVersion: 0,
      sequencePosition: 25
    })
    wrapper.unmount()
  }, 10_000)

  it('具体场次只保留拖拽排序，不再暴露独立重编号动作', async () => {
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    expect(wrapper.findAllComponents(ElButton).some(button => buttonLabel(button) === '按当前顺序重新编号')).toBe(false)

    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    expect(wrapper.findAllComponents(ElButton).some(button => buttonLabel(button) === '按当前顺序重新编号')).toBe(false)
    expect(wrapper.text()).toContain('当前场次无需排序')
    wrapper.unmount()
  })

  it('项目管理人可从镜头页新建下一集和当前集下一场', async () => {
    const permissions = [
      'shotgrid:shot:list',
      'shotgrid:episode:add',
      'shotgrid:scene:add',
      'shotgrid:member:list'
    ]
    const { wrapper } = await mountView(permissions)

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建集').trigger('click')
    await flushPromises()
    let hierarchyDialog = wrapper.findComponent(EpisodeSceneCreateDialog)
    expect(hierarchyDialog.props('mode')).toBe('episode')
    expect(hierarchyDialog.findComponent(ElForm).props('model').number).toBe(2)
    await hierarchyDialog.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建集').trigger('click')
    await flushPromises()
    expect(createEpisode).toHaveBeenCalledWith(8, expect.objectContaining({ episodeNo: 2, sortOrder: 20 }))

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建场次').trigger('click')
    await flushPromises()
    hierarchyDialog = wrapper.findComponent(EpisodeSceneCreateDialog)
    expect(hierarchyDialog.props('mode')).toBe('scene')
    expect(hierarchyDialog.findComponent(ElForm).props('model')).toMatchObject({ episodeId: '21', number: 2 })
    await hierarchyDialog.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建场次').trigger('click')
    await flushPromises()
    expect(createScene).toHaveBeenCalledWith(8, 21, expect.objectContaining({ sceneNo: 2, sortOrder: 20 }))
    wrapper.unmount()
  })

  it('从具体场次打开新建镜头时继承当前集场并加载末尾位置', async () => {
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:add',
      'shotgrid:member:list'
    ])
    const filterSelects = wrapper.find('.shot-filters').findAllComponents(ElSelect)

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建镜头').trigger('click')
    await flushPromises()
    await flushPromises()

    const dialog = wrapper.findComponent(ShotFormDialog)
    expect(dialog.props()).toMatchObject({
      initialEpisodeId: '21',
      initialSceneId: '31'
    })
    expect(dialog.findComponent(ElForm).props('model')).toMatchObject({
      episodeId: '21',
      sceneId: '31',
      sequencePosition: 2
    })
    expect(getShotPage).toHaveBeenCalledWith(8, expect.objectContaining({ episodeId: 21, sceneId: 31 }), expect.anything())
    wrapper.unmount()
  })

  it('新建场次允许创建 000 序场并自动使用规范名称', async () => {
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:scene:add',
      'shotgrid:member:list'
    ])

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建场次').trigger('click')
    await flushPromises()
    const hierarchyDialog = wrapper.findComponent(EpisodeSceneCreateDialog)
    const form = hierarchyDialog.findComponent(ElForm)
    form.props('model').number = 0
    await flushPromises()

    expect(form.props('model').name).toBe('序')
    await hierarchyDialog.findAllComponents(ElButton).find(button => buttonLabel(button) === '新建场次').trigger('click')
    await flushPromises()

    expect(createScene).toHaveBeenCalledWith(8, 21, expect.objectContaining({
      sceneNo: 0,
      sceneName: '序'
    }))
    wrapper.unmount()
  })

  it('镜头下拉筛选 change 后立即查询，并在切换集时清空旧场次', async () => {
    const { wrapper } = await mountView()
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('shot-filters'))
    const filterSelects = filterForm.findAllComponents({ name: 'ElSelect' })
    getShotPage.mockClear()
    getScenePage.mockClear()

    await setElSelectValue(filterSelects[0], '21')
    await flushPromises()
    expect(getScenePage).toHaveBeenLastCalledWith(8, 21, expect.anything(), expect.anything())
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ episodeId: '21', sceneId: undefined, pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[1], '31')
    await flushPromises()
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ episodeId: '21', sceneId: '31', pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[2], 'in_progress')
    await flushPromises()
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ shotStatus: 'in_progress', pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[3], '7')
    await flushPromises()
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ assigneeUserId: '7', pageNum: 1 }), expect.anything())

    await setElSelectValue(filterSelects[0], '')
    await flushPromises()
    expect(filterForm.props('model')).toMatchObject({ episodeId: '', sceneId: '' })
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ episodeId: undefined, sceneId: undefined, pageNum: 1 }), expect.anything())
    wrapper.unmount()
  })

  it('通过 Element Plus Form 重置全部筛选并重新查询第一页', async () => {
    const { wrapper } = await mountView()
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('shot-filters'))
    await filterForm.find('input[aria-label="搜索镜头"]').setValue('动力舱')
    const filterSelects = filterForm.findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], '21')
    await setElSelectValue(filterSelects[2], 'in_progress')
    await setElSelectValue(filterSelects[3], '7')
    await flushPromises()
    getShotPage.mockClear()

    await filterForm.findAllComponents(ElButton).find(button => buttonLabel(button) === '重置').trigger('click')
    await flushPromises()

    expect(filterForm.props('model')).toMatchObject({ keyword: '', episodeId: '', sceneId: '', shotStatus: '', assigneeUserId: '', pageNum: 1 })
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({
      keyword: undefined,
      episodeId: undefined,
      sceneId: undefined,
      shotStatus: undefined,
      assigneeUserId: undefined,
      pageNum: 1
    }), expect.anything())
    wrapper.unmount()
  })

  it('点击详情在当前列表右侧打开可销毁的镜头详情抽屉', async () => {
    const { wrapper, router } = await mountView(['shotgrid:shot:list'])

    await wrapper.findAll('button').find(button => buttonLabel(button) === '详情').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/shots')
    expect(document.body.textContent).toContain('镜头详情 · 0001')
    expect(document.body.textContent).toContain('制作信息')
    const productionSection = document.body.querySelector('.shot-overview .shot-overview__production')
    expect(productionSection).not.toBeNull()
    expect(productionSection.textContent).toContain('制作内容')
    expect(productionSection.textContent).toContain('镜头缓慢推进动力舱')
    expect(document.body.querySelector('.shot-hero__main').textContent).not.toContain('镜头缓慢推进动力舱')
    expect(document.body.querySelector('.detail-grid .shot-overview__production')).toBeNull()
    expect(getShotDetail).toHaveBeenCalledWith(8, 41, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })

  it('未开始镜头可勾选、编辑和批量删除，已开始镜头禁止编辑和删除', async () => {
    const notStartedShot = { ...shotRow, status: 'not_started' }
    getShotPage.mockResolvedValue({ rows: [notStartedShot], total: 1, hasNext: false })
    getShotDetail.mockResolvedValue({ data: shotDetail(8, 41, '0001', '镜头缓慢推进动力舱') })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:shot:archive'
    ])

    const checkbox = shotRowCheckboxes(wrapper)[0]
    expect(checkbox.element.disabled).toBe(false)
    expect(wrapper.findAll('button').map(buttonLabel)).toContain('编辑')
    expect(wrapper.findAll('button').map(buttonLabel)).toContain('删除')
    await checkbox.setValue(true)
    await flushPromises()
    let resolveDelete
    batchDeleteShots.mockImplementationOnce(() => new Promise(resolve => { resolveDelete = resolve }))
    await wrapper.findAll('button').find(button => button.text().includes('批量删除')).trigger('click')
    await flushPromises()
    expect(batchDeleteShots).toHaveBeenCalledWith(8, [{ shotId: 41, lockVersion: 0 }])
    expect(shotRowCheckboxes(wrapper)[0].element.disabled).toBe(true)
    await setShotHeaderSelection(wrapper, false)
    expect(selectedTableShots(wrapper).map(row => row.shotId)).toEqual([41])
    expect(batchDeleteShots).toHaveBeenCalledTimes(1)
    resolveDelete({ data: { deletedShotIds: [41], deletedCount: 1 } })
    await flushPromises()
    expect(selectedTableShots(wrapper)).toEqual([])

    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status: 'in_progress' }], total: 1, hasNext: false })
    await wrapper.find('button[aria-label="刷新镜头"]').trigger('click')
    await flushPromises()
    expect(shotRowCheckboxes(wrapper)[0].element.disabled).toBe(true)
    expect(wrapper.findAll('button').map(buttonLabel)).not.toContain('编辑')
    confirmSpy.mockRestore()
    wrapper.unmount()
  })

  it('可将当前页选中的镜头批量分配给项目制作人', async () => {
    getShotPage.mockResolvedValue({ rows: [assignableShotRow], total: 1 })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:task:assign'
    ])

    await shotRowCheckboxes(wrapper)[0].setValue(true)
    await flushPromises()
    const batchAssignButton = wrapper.findAll('button').find(button => button.text().includes('批量重新分配'))
    expect(batchAssignButton.element.disabled).toBe(false)
    expect(wrapper.find('[aria-label="批量分配制作人"]').exists()).toBe(false)
    await batchAssignButton.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('其中包含已分配镜头')
    const batchAssignForm = wrapper.findAllComponents(ElForm).find(form => form.attributes('aria-label') === '镜头批量分配表单')
    expect(batchAssignForm.props('rules')).toHaveProperty('assigneeUserId')
    const confirmButton = [...document.body.querySelectorAll('button')]
      .find(button => button.textContent.includes('确认重新分配'))
    confirmButton.click()
    await flushPromises()
    expect(batchAssignShotTasks).not.toHaveBeenCalled()

    await setElSelectValue(batchAssignForm.findComponent(ElSelect), '7')
    let resolveAssignment
    batchAssignShotTasks.mockImplementationOnce(() => new Promise(resolve => { resolveAssignment = resolve }))
    confirmButton.click()
    await flushPromises()

    expect(batchAssignShotTasks).toHaveBeenCalledWith(8, 7, [
      { shotId: 41, taskLockVersion: 4 }
    ])
    expect(shotRowCheckboxes(wrapper)[0].element.disabled).toBe(true)
    await setShotHeaderSelection(wrapper, false)
    expect(selectedTableShots(wrapper).map(row => row.shotId)).toEqual([41])
    expect(batchAssignShotTasks).toHaveBeenCalledTimes(1)
    resolveAssignment({ data: { assignedShotIds: [41], assignedCount: 1 } })
    await flushPromises()
    expect(selectedTableShots(wrapper)).toEqual([])
    confirmSpy.mockRestore()
    wrapper.unmount()
  })

  it('服务端 403 不会伪装成空镜头列表', async () => {
    getShotPage.mockRejectedValue({ httpStatus: 403, message: '不是项目成员' })
    const { wrapper } = await mountView(['shotgrid:shot:list'])
    expect(wrapper.text()).toContain('没有镜头访问权限')
    expect(wrapper.text()).toContain('不是项目成员')
    expect(wrapper.text()).not.toContain('当前筛选没有镜头')
    wrapper.unmount()
  })

  it('项目切换会中止并丢弃旧项目导入后的集选项刷新结果', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      projectId,
      projectCode: projectId === 8 ? 'LCFR' : 'NEW',
      projectName: projectId === 8 ? '罗刹夫人' : '新项目',
      projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    let project8EpisodeCalls = 0
    let resolveStaleRefresh
    getEpisodePage.mockImplementation(projectId => {
      if (projectId === 8) {
        project8EpisodeCalls += 1
        if (project8EpisodeCalls === 1) return Promise.resolve({ rows: [{ episodeId: 21, episodeCode: 'EP001' }], total: 1, hasNext: false })
        return new Promise(resolve => { resolveStaleRefresh = resolve })
      }
      return Promise.resolve({ rows: [{ episodeId: 91, episodeCode: 'EP002' }], total: 1, hasNext: false })
    })
    const { wrapper } = await mountView()
    await wrapper.findAll('button').find(button => button.text().includes('导入 Excel')).trigger('click')
    await flushPromises()
    const importDialog = wrapper.findComponent(ShotImportDialog)
    importDialog.vm.$emit('imported', { createdShots: 1 }, {
      projectId: 8,
      operationGeneration: importDialog.props('operationGeneration')
    })
    await flushPromises()

    await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '9')
    await flushPromises()
    resolveStaleRefresh({ rows: [{ episodeId: 999, episodeCode: 'EP999' }], total: 1, hasNext: false })
    await flushPromises()

    const episodeLabels = wrapper.find('.shot-filters').findComponent({ name: 'ElSelect' }).findAllComponents({ name: 'ElOption' }).map(option => option.props('label'))
    expect(episodeLabels).toContain('EP002 ')
    expect(episodeLabels).not.toContain('EP999 ')
    wrapper.unmount()
  })

  it('项目切换会取消尚在路由同步阶段的旧上下文请求', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      projectId,
      projectCode: projectId === 8 ? 'LCFR' : 'NEW',
      projectName: projectId === 8 ? '罗刹夫人' : '新项目',
      projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    getEpisodePage.mockImplementation(projectId => Promise.resolve({
      rows: [{ episodeId: projectId === 8 ? 21 : 91, episodeCode: projectId === 8 ? 'EP001' : 'EP002' }],
      total: 1,
      hasNext: false
    }))
    let releaseProject8Navigation
    const { wrapper } = await mountView(undefined, router => {
      const originalReplace = router.replace.bind(router)
      vi.spyOn(router, 'replace').mockImplementation(location => {
        if (String(location.query?.projectId) === '8') {
          return new Promise(resolve => { releaseProject8Navigation = resolve })
        }
        return originalReplace(location)
      })
    })

    await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '9')
    await flushPromises()
    releaseProject8Navigation()
    await flushPromises()

    expect(getProjectDetail).not.toHaveBeenCalledWith(8, expect.anything())
    expect(getProjectDetail).toHaveBeenCalledWith(9, expect.anything())
    expect(wrapper.find('.shot-filters').findComponent({ name: 'ElSelect' }).findAllComponents({ name: 'ElOption' }).map(option => option.props('label'))).toContain('EP002 ')
    wrapper.unmount()
  })

  it('项目切换会销毁绑定弹窗，并忽略旧创建与导入完成事件', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      projectId,
      projectCode: projectId === 8 ? 'LCFR' : 'NEW',
      projectName: projectId === 8 ? '罗刹夫人' : '新项目',
      projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    previewShotImport.mockResolvedValue({ data: {
      batchId: 6,
      importToken: 'old-project-token',
      expiresAt: '2026-08-11T14:00:00',
      summary: { totalRows: 1, validRows: 1, warningRows: 0, errorRows: 0, distinctEpisodes: 1, distinctScenes: 1, distinctShots: 1 },
      workbookWarnings: [],
      rows: [{ sheetName: 'EP001', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { sceneCode: '001', shotCode: '0001', durationMs: 3000, description: '旧项目镜头', assetRequirements: [] } }]
    } })
    const { wrapper } = await mountView()

    await wrapper.findAll('button').find(button => button.text().includes('新建镜头')).trigger('click')
    const oldCreateDialog = wrapper.findComponent(ShotFormDialog).vm
    const oldCreateGeneration = oldCreateDialog.$props.operationGeneration
    expect(document.body.querySelector('.shot-form')).not.toBeNull()
    await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '9')
    await flushPromises()
    expect(document.body.querySelector('.shot-form')).toBeNull()
    const callsAfterCreateSwitch = getShotPage.mock.calls.length
    oldCreateDialog.$emit('saved', { projectId: 8, shotId: 42 }, {
      projectId: 8,
      shotId: null,
      operationGeneration: oldCreateGeneration
    })
    await flushPromises()
    expect(getShotPage).toHaveBeenCalledTimes(callsAfterCreateSwitch)

    await wrapper.findAll('button').find(button => button.text().includes('导入 Excel')).trigger('click')
    await flushPromises()
    const oldImportDialog = wrapper.findComponent(ShotImportDialog).vm
    const oldImportGeneration = oldImportDialog.$props.operationGeneration
    const fileInput = document.body.querySelector('.import-flow input[type="file"]')
    const file = new File(['xlsx'], '旧项目镜头.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(fileInput, 'files', { configurable: true, value: [file] })
    fileInput.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    Array.from(document.body.querySelectorAll('.import-flow button'))
      .find(button => button.textContent.includes('预览导入内容'))
      .click()
    await flushPromises()
    expect(previewShotImport).toHaveBeenCalledWith(9, file, expect.anything())
    expect(document.body.textContent).toContain('旧项目镜头')
    expect(document.body.textContent).toContain('确认导入 1 条')

    await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '8')
    await flushPromises()
    expect(document.body.querySelector('.import-flow')).toBeNull()
    expect(document.body.textContent).not.toContain('旧项目镜头')
    expect(document.body.textContent).not.toContain('确认导入 1 条')
    const callsAfterImportSwitch = getShotPage.mock.calls.length
    oldImportDialog.$emit('imported', { createdShots: 1 }, {
      projectId: 9,
      operationGeneration: oldImportGeneration
    })
    await flushPromises()
    expect(getShotPage).toHaveBeenCalledTimes(callsAfterImportSwitch)
    expect(commitShotImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('返回同一项目重开弹窗后旧创建与导入事件不能关闭新实例或刷新', async () => {
    getProjectPage.mockResolvedValue({ rows: [projectRow, { projectId: 9, projectCode: 'NEW', projectName: '新项目' }], total: 2, hasNext: false })
    getProjectDetail.mockImplementation(projectId => Promise.resolve({ data: {
      projectId,
      projectCode: projectId === 8 ? 'LCFR' : 'NEW',
      projectName: projectId === 8 ? '罗刹夫人' : '新项目',
      projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director'
    } }))
    const { wrapper } = await mountView()
    const switchProject = async projectId => {
      await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), String(projectId))
      await flushPromises()
    }

    await wrapper.findAll('button').find(button => button.text().includes('新建镜头')).trigger('click')
    const oldCreateDialog = wrapper.findComponent(ShotFormDialog)
    const oldCreateGeneration = oldCreateDialog.props('operationGeneration')
    await switchProject(9)
    await switchProject(8)
    await wrapper.findAll('button').find(button => button.text().includes('新建镜头')).trigger('click')
    const newCreateDialog = wrapper.findComponent(ShotFormDialog)
    const newCreateGeneration = newCreateDialog.props('operationGeneration')
    expect(newCreateGeneration).not.toBe(oldCreateGeneration)
    const createRefreshCalls = getShotPage.mock.calls.length
    oldCreateDialog.vm.$emit('saved', { projectId: 8, shotId: 42 }, {
      projectId: 8,
      shotId: null,
      operationGeneration: oldCreateGeneration
    })
    await flushPromises()
    expect(wrapper.findComponent(ShotFormDialog).exists()).toBe(true)
    expect(wrapper.findComponent(ShotFormDialog).props('operationGeneration')).toBe(newCreateGeneration)
    expect(getShotPage).toHaveBeenCalledTimes(createRefreshCalls)
    newCreateDialog.vm.$emit('close')
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('导入 Excel')).trigger('click')
    const oldImportDialog = wrapper.findComponent(ShotImportDialog)
    const oldImportGeneration = oldImportDialog.props('operationGeneration')
    await switchProject(9)
    await switchProject(8)
    await wrapper.findAll('button').find(button => button.text().includes('导入 Excel')).trigger('click')
    const newImportDialog = wrapper.findComponent(ShotImportDialog)
    const newImportGeneration = newImportDialog.props('operationGeneration')
    expect(newImportGeneration).not.toBe(oldImportGeneration)
    const importRefreshCalls = getShotPage.mock.calls.length
    oldImportDialog.vm.$emit('imported', { createdShots: 1 }, {
      projectId: 8,
      operationGeneration: oldImportGeneration
    })
    await flushPromises()
    expect(wrapper.findComponent(ShotImportDialog).exists()).toBe(true)
    expect(wrapper.findComponent(ShotImportDialog).props('operationGeneration')).toBe(newImportGeneration)
    expect(getShotPage).toHaveBeenCalledTimes(importRefreshCalls)
    wrapper.unmount()
  })
})

describe('镜头 Element Plus 表单契约', () => {
  beforeEach(() => {
    getScenePage.mockResolvedValue({ rows: [{ sceneId: 31, sceneCode: '001', sceneName: '动力舱' }], total: 1, hasNext: false })
    getShotPage.mockReset()
    getShotPage.mockResolvedValue({
      rows: [{ ...shotRow, status: 'unassigned', assignee: null, storageDirName: null, directoryStatus: 'not_created' }],
      total: 1,
      hasNext: false
    })
    createShot.mockReset()
    createShot.mockResolvedValue({ data: { ...shotRow, shotId: 45, shotCode: '0005' } })
    updateShot.mockReset()
    assignShotTask.mockReset()
    assignShotTask.mockResolvedValue({ data: { taskId: 71 } })
  })

  it('新建镜头由按钮点击触发 Form 校验，失败时拦截请求，通过后提交并可重置', async () => {
    const wrapper = mount(ShotFormDialog, {
      props: {
        projectId: 8,
        operationGeneration: 1,
        episodes: [{ episodeId: 21, episodeCode: 'EP001', episodeName: '第一集' }]
      },
      global: { components: formComponents }
    })
    const form = wrapper.findComponent(ElForm)
    const formItems = form.findAllComponents(ElFormItem)
    const formItem = prop => formItems.find(item => item.props('prop') === prop)
    const submitButton = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '创建镜头')

    expect(form.props('model')).toMatchObject({ episodeId: '', sceneId: '', sequencePosition: null, durationSeconds: 0 })
    expect(form.props('rules')).toMatchObject({
      episodeId: expect.any(Array),
      sceneId: expect.any(Array),
      sequencePosition: expect.any(Array),
      durationSeconds: expect.any(Array),
      description: expect.any(Array)
    })
    expect(formItems.every(item => Boolean(item.props('prop')))).toBe(true)
    expect(submitButton.props('nativeType')).toBe('button')

    await submitButton.trigger('click')
    await flushPromises()
    expect(createShot).not.toHaveBeenCalled()

    await setElSelectValue(formItem('episodeId').findComponent(ElSelect), '21')
    await flushPromises()
    expect(getShotPage).toHaveBeenLastCalledWith(8, expect.objectContaining({ episodeId: 21, sceneId: 31 }), expect.anything())
    await setElSelectValue(formItem('sequencePosition').findComponent(ElSelect), 1)
    formItem('durationSeconds').findComponent(ElInputNumber).vm.$emit('update:modelValue', 1.25)
    formItem('description').findComponent(ElInput).vm.$emit('update:modelValue', '  动力舱推进镜头  ')
    await flushPromises()
    await submitButton.trigger('click')
    await flushPromises()

    expect(createShot).toHaveBeenCalledWith(8, expect.objectContaining({
      sceneId: 31,
      durationMs: 1250,
      description: '动力舱推进镜头',
      sequencePosition: 1,
      assetIds: []
    }))
    const createPayload = createShot.mock.calls[0][1]
    expect(createPayload).not.toHaveProperty('shotNo')
    expect(createPayload).not.toHaveProperty('assigneeUserId')
    expect(createPayload).not.toHaveProperty('taskDescription')
    expect(wrapper.text()).toContain('创建后状态：未分配')
    expect(wrapper.emitted('saved')).toHaveLength(1)

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '取消').trigger('click')
    await flushPromises()
    expect(form.props('model')).toMatchObject({ episodeId: '', sceneId: '', sequencePosition: null, durationSeconds: 0, description: '' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('历史镜头号不连续时禁止新建并清空场内位置', async () => {
    getShotPage.mockResolvedValue({
      rows: [
        { ...shotRow, status: 'unassigned', shotNo: 2, shotCode: '0002', sequencePosition: 2 },
        { ...shotRow, shotId: 42, status: 'unassigned', shotNo: 4, shotCode: '0004', sequencePosition: 4 }
      ],
      total: 2,
      hasNext: false
    })
    const wrapper = mount(ShotFormDialog, {
      props: {
        projectId: 8,
        operationGeneration: 2,
        episodes: [{ episodeId: 21, episodeCode: 'EP001', episodeName: '第一集' }],
        initialEpisodeId: '21',
        initialSceneId: '31'
      },
      global: { components: formComponents }
    })
    await flushPromises()
    await flushPromises()

    const form = wrapper.findComponent(ElForm)
    const submitButton = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '创建镜头')
    expect(form.props('model').sequencePosition).toBeNull()
    expect(wrapper.text()).toContain('当前场次镜头号不连续，请先完成历史数据治理后再新建镜头')
    expect(submitButton.props('disabled')).toBe(true)
    wrapper.unmount()
  })

  it('新建镜头只展示不会推动冻结目录的安全插入位置', async () => {
    getShotPage.mockResolvedValue({
      rows: [
        { ...shotRow, status: 'unassigned', shotNo: 1, shotCode: '0001', sequencePosition: 1 },
        { ...shotRow, shotId: 42, status: 'unassigned', assignee: null, shotNo: 2, shotCode: '0002', sequencePosition: 2, storageDirName: null, directoryStatus: 'not_created' }
      ],
      total: 2,
      hasNext: false
    })
    const wrapper = mount(ShotFormDialog, {
      props: {
        projectId: 8,
        operationGeneration: 3,
        episodes: [{ episodeId: 21, episodeCode: 'EP001', episodeName: '第一集' }],
        initialEpisodeId: '21',
        initialSceneId: '31'
      },
      global: { components: formComponents }
    })
    await flushPromises()
    await flushPromises()

    const sequenceField = wrapper.findAllComponents(ElFormItem).find(item => item.props('prop') === 'sequencePosition')
    const values = sequenceField.findAllComponents(ElOption).map(option => option.props('value'))
    expect(values).toEqual([2, 3])
    expect(sequenceField.findAllComponents(ElOption).map(option => option.props('label'))).toEqual([
      expect.stringContaining('0002'),
      expect.stringContaining('0003')
    ])
    expect(wrapper.findComponent(ElForm).props('model').sequencePosition).toBe(3)
    wrapper.unmount()
  })

  it('镜头任务分配由按钮点击触发 Form 校验，并保留加载与重置契约', async () => {
    const wrapper = mount(ShotAssignDialog, {
      props: {
        projectId: 8,
        operationGeneration: 2,
        shot: { ...shotRow, task: null },
        members: [{ userId: 7, nickName: '杨景锋', projectRole: 'creator' }]
      },
      global: { components: formComponents }
    })
    const form = wrapper.findComponent(ElForm)
    const formItems = form.findAllComponents(ElFormItem)
    const formItem = prop => formItems.find(item => item.props('prop') === prop)
    const submitButton = wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '创建并分配任务')

    expect(form.props('rules')).toMatchObject({ assigneeUserId: expect.any(Array) })
    expect(formItems.map(item => item.props('prop'))).toEqual(['assigneeUserId'])
    expect(wrapper.find('textarea').exists()).toBe(false)
    const productionInfo = wrapper.find('.assign-form__production')
    expect(productionInfo.text()).toContain('完整制作信息')
    expect(productionInfo.text()).toContain(shotRow.description)
    expect(productionInfo.text()).toContain(shotRow.shotSize)
    expect(productionInfo.text()).toContain(shotRow.cameraPosition)
    expect(productionInfo.text()).toContain(shotRow.cameraMovement)
    expect(productionInfo.text()).toContain(shotRow.focalLength)
    expect(productionInfo.text()).toContain(shotRow.dialogue)
    expect(productionInfo.text()).toContain(shotRow.soundEffect)
    expect(productionInfo.text()).toContain(shotRow.colorReference)
    expect(productionInfo.text()).toContain(shotRow.remark)
    expect(submitButton.props('nativeType')).toBe('button')

    await submitButton.trigger('click')
    await flushPromises()
    expect(assignShotTask).not.toHaveBeenCalled()

    await setElSelectValue(formItem('assigneeUserId').findComponent(ElSelect), '7')
    await flushPromises()
    await submitButton.trigger('click')
    await flushPromises()

    expect(assignShotTask).toHaveBeenCalledWith(8, 41, {
      assigneeUserId: 7
    })
    expect(wrapper.emitted('assigned')).toHaveLength(1)

    await wrapper.findAllComponents(ElButton).find(button => buttonLabel(button) === '取消').trigger('click')
    await flushPromises()
    expect(form.props('model')).toMatchObject({ assigneeUserId: '' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('镜头任务改派仍完整展示只读制作信息，并只保留制作人字段', () => {
    const wrapper = mount(ShotAssignDialog, {
      props: {
        projectId: 8,
        operationGeneration: 4,
        shot: {
          ...assignableShotRow,
          task: {
            assignee: { userId: 7, nickName: '杨景锋' },
            priority: 'high',
            dueDate: '2026-09-01',
            lockVersion: 3
          }
        },
        members: [{ userId: 7, nickName: '杨景锋', projectRole: 'creator' }]
      },
      global: { components: formComponents }
    })

    expect(wrapper.findAllComponents(ElFormItem).map(item => item.props('prop'))).toEqual(['assigneeUserId'])
    const productionInfo = wrapper.find('.assign-form__production')
    expect(productionInfo.text()).toContain(shotRow.description)
    expect(productionInfo.text()).toContain(shotRow.soundEffect)
    expect(productionInfo.text()).toContain(shotRow.colorReference)
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('镜头详情跨项目请求隔离', () => {
  beforeEach(() => {
    getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 21, episodeCode: 'EP001' }], total: 1, hasNext: false })
    getScenePage.mockResolvedValue({ rows: [{ sceneId: 31, sceneCode: '001' }], total: 1, hasNext: false })
    listShotAssignees.mockResolvedValue({ rows: [{ userId: 7, userName: '杨景锋', nickName: 'YJF', projectRole: 'creator', producerCode: 'YJF' }], total: 1, hasNext: false })
  })

  it.each([
    [{ expectedStartTime: '2099-09-01T09:30:00', expectedEndTime: '2099-09-04T18:00:00', dueDate: '2099-09-04' }, ['2099/09/01 09:30', '2099/09/04 18:00', '时间：正常']],
    [{ dueDate: '2000-09-04' }, ['原截止日期：2000-09-04', '时间：已延期']],
    [{}, ['时间：未设置时间']]
  ])('镜头详情显示预期时间范围并兼容历史日期 %#', async (timeFields, expectedTexts) => {
    getShotDetail.mockResolvedValueOnce({ data: {
      ...shotDetail(8, 41, '0001', '动力舱推进镜头'),
      task: { assignee: { userId: 7, userName: '杨景锋' }, taskStatus: 'in_progress', priority: 'normal', ...timeFields }
    } })
    const { wrapper } = await mountDetailView()
    try {
      expect(wrapper.text()).toContain('预期制作时间')
      const reminder = wrapper.find('[aria-label="时间提醒"]')
      for (const text of expectedTexts) expect(reminder.text()).toContain(text)
      expect(reminder.find('.task-time-reminder__range').exists()).toBe(Boolean(timeFields.expectedStartTime))
    } finally { wrapper.unmount() }
  })

  it('镜头详情的状态、目录、优先级、版本和关联资产使用 ElTag 动态类型', async () => {
    getShotDetail.mockResolvedValueOnce({ data: {
      ...shotDetail(8, 41, '0001', '动力舱推进镜头'),
      status: 'revision',
      directoryStatus: 'failed',
      task: {
        assignee: { userId: 7, nickName: 'YJF' },
        taskStatus: 'pending_review',
        priority: 'urgent',
        dueDate: '2026-09-01',
        lockVersion: 3
      },
      latestVersion: { versionNumber: 'V002', businessFileName: 'LCFR_0001_V002.mp4', status: 'rejected' },
      assets: [
        { assetId: 2, assetName: '动力舱', assetType: 'Environment' },
        { assetId: 3, assetName: '女主', assetType: 'Character' },
        { assetId: 4, assetName: '手电筒', assetType: 'Prop' }
      ]
    } })

    const { wrapper } = await mountDetailView()
    expect(findTag(wrapper, '修改中').props()).toMatchObject({ type: 'danger', effect: 'light', round: true })
    expect(findTag(wrapper, '目录处理异常').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
    expect(findTag(wrapper, '待审核').props()).toMatchObject({ type: 'warning', effect: 'light', round: true })
    expect(findTag(wrapper, '紧急').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
    expect(findTag(wrapper, '已退回').props()).toMatchObject({ type: 'danger', effect: 'light', round: true })
    expect(findTag(wrapper, '场景 · 动力舱').props()).toMatchObject({ type: 'primary', effect: 'plain', round: true })
    expect(findTag(wrapper, '角色 · 女主').props()).toMatchObject({ type: 'warning', effect: 'plain', round: true })
    expect(findTag(wrapper, '道具 · 手电筒').props()).toMatchObject({ type: 'success', effect: 'plain', round: true })
    expect(wrapper.find('.task-person').text()).toContain('杨景锋')
    expect(wrapper.find('.status-chip').exists()).toBe(false)
    wrapper.unmount()
  })

  it('快速切换项目和镜头时立即清理旧详情并丢弃过期响应', async () => {
    let resolveProject9
    getShotDetail.mockImplementation((projectId, _shotId) => {
      if (projectId === 8) return Promise.resolve({ data: shotDetail(8, 41, '0001', '旧项目镜头') })
      if (projectId === 9) return new Promise(resolve => { resolveProject9 = resolve })
      return Promise.resolve({ data: shotDetail(10, 61, '0003', '当前项目镜头') })
    })
    const { wrapper, router } = await mountDetailView()
    expect(wrapper.text()).toContain('旧项目镜头')

    await wrapper.findAll('button').find(button => button.text().includes('编辑镜头')).trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.shot-form')).not.toBeNull()

    await router.push('/projects/9/shots/51')
    await flushPromises()
    expect(wrapper.find('.detail-loading').attributes('aria-busy')).toBe('true')
    expect(wrapper.text()).not.toContain('旧项目镜头')
    expect(document.body.querySelector('.shot-form')).toBeNull()
    expect(wrapper.text()).not.toContain('编辑镜头')

    await router.push('/projects/10/shots/61')
    await flushPromises()
    expect(wrapper.text()).toContain('当前项目镜头')

    resolveProject9({ data: shotDetail(9, 51, '0002', '过期项目镜头') })
    await flushPromises()
    expect(wrapper.text()).toContain('当前项目镜头')
    expect(wrapper.text()).not.toContain('过期项目镜头')
    wrapper.unmount()
  })

  it('旧镜头分配完成事件不会刷新或覆盖新路由上下文', async () => {
    getShotDetail.mockImplementation((projectId, shotId) => Promise.resolve({ data: shotDetail(
      projectId,
      shotId,
      projectId === 8 ? '0001' : '0002',
      projectId === 8 ? '旧镜头' : '当前镜头'
    ) }))
    const { wrapper, router } = await mountDetailView()
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    const oldAssignDialog = wrapper.findComponent(ShotAssignDialog).vm
    const oldAssignGeneration = oldAssignDialog.$props.operationGeneration

    await router.push('/projects/9/shots/51')
    await flushPromises()
    expect(wrapper.text()).toContain('当前镜头')
    const callsAfterRouteSwitch = getShotDetail.mock.calls.length

    oldAssignDialog.$emit(
      'assigned',
      { projectId: 8, taskId: 71 },
      { projectId: 8, shotId: 41, operationGeneration: oldAssignGeneration, wasReassign: false }
    )
    await flushPromises()
    expect(getShotDetail).toHaveBeenCalledTimes(callsAfterRouteSwitch)
    expect(wrapper.text()).toContain('当前镜头')
    expect(wrapper.text()).not.toContain('旧镜头')
    wrapper.unmount()
  })

  it('返回同一镜头重开分配弹窗后旧完成事件不能关闭新实例或刷新', async () => {
    getShotDetail.mockImplementation((targetProjectId, targetShotId) => Promise.resolve({ data: shotDetail(
      targetProjectId,
      targetShotId,
      targetProjectId === 8 ? '0001' : '0002',
      targetProjectId === 8 ? '同一目标镜头' : '中转镜头'
    ) }))
    const { wrapper, router } = await mountDetailView()
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    const oldAssignDialog = wrapper.findComponent(ShotAssignDialog)
    const oldAssignGeneration = oldAssignDialog.props('operationGeneration')

    await router.push('/projects/9/shots/51')
    await flushPromises()
    await router.push('/projects/8/shots/41')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('分配任务')).trigger('click')
    const newAssignDialog = wrapper.findComponent(ShotAssignDialog)
    const newAssignGeneration = newAssignDialog.props('operationGeneration')
    expect(newAssignGeneration).not.toBe(oldAssignGeneration)
    const detailRefreshCalls = getShotDetail.mock.calls.length

    oldAssignDialog.vm.$emit(
      'assigned',
      { projectId: 8, taskId: 71 },
      { projectId: 8, shotId: 41, operationGeneration: oldAssignGeneration, wasReassign: false }
    )
    await flushPromises()
    expect(wrapper.findComponent(ShotAssignDialog).exists()).toBe(true)
    expect(wrapper.findComponent(ShotAssignDialog).props('operationGeneration')).toBe(newAssignGeneration)
    expect(getShotDetail).toHaveBeenCalledTimes(detailRefreshCalls)
    expect(wrapper.text()).toContain('同一目标镜头')
    wrapper.unmount()
  })
})
