import { ElButton, ElCard, ElDatePicker, ElDialog, ElDrawer, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElMessageBox, ElOption, ElPagination, ElRadioButton, ElRadioGroup, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectDetail, getProjectMembers, getProjectPage } from '@/api/shot-grid/projects'
import {
  batchAssignShotTasks,
  batchDeleteShots,
  commitShotImport,
  createShot,
  getEpisodePage,
  getScenePage,
  getShotDetail,
  getShotPage,
  listShotAssignees,
  previewShotImport,
  assignShotTask,
  updateShot
} from '@/api/shot-grid/shots'
import { useSessionStore } from '@/store/modules/session'
import { setElSelectValue } from '../helpers/elementPlus'
import ShotDetailView from '@/views/shot/ShotDetailView.vue'
import ShotListView from '@/views/shot/ShotListView.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  getProjectDetail: vi.fn(),
  getProjectMembers: vi.fn(),
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/shots', () => ({
  archiveShot: vi.fn(),
  assignShotTask: vi.fn(),
  batchAssignShotTasks: vi.fn(),
  batchDeleteShots: vi.fn(),
  commitShotImport: vi.fn(),
  createShot: vi.fn(),
  downloadProtectedThumbnail: vi.fn(),
  getEpisodePage: vi.fn(),
  getScenePage: vi.fn(),
  getShotDetail: vi.fn(),
  getShotPage: vi.fn(),
  listShotAssignees: vi.fn(),
  previewShotImport: vi.fn(),
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
  shotCode: 'S001',
  storageDirName: 'S001',
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
  status: 'in_progress',
  assignee: { userId: 7, nickName: 'YJF', producerCode: 'YJF' },
  thumbnail: null,
  latestVersion: null,
  latestFeedback: null,
  assetCount: 1,
  lockVersion: 0,
  taskLockVersion: 4
}

const formComponents = { ElButton, ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElOption, ElSelect }

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
  const wrapper = mount(ShotDetailView, { global: { plugins: [router], components: { ...formComponents, ElTag } } })
  await flushPromises()
  return { wrapper, router }
}

function findTag(wrapper, text) {
  return wrapper.findAllComponents(ElTag).find(tag => tag.text() === text)
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
    createBy: 'director',
    createTime: '2026-08-11T10:00:00',
    updateBy: 'director',
    updateTime: '2026-08-11T10:00:00',
    allowedActions: ['shot.edit', 'shot.archive', 'task.assign']
  }
}

describe('镜头管理真实列表页', () => {
  beforeEach(() => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
    getProjectDetail.mockResolvedValue({ data: { ...projectRow, projectTypeName: 'AI 影视短片', aspectRatio: '16:9', projectStatus: 'active', storageStatus: 'ready', myProjectRole: 'director' } })
    getProjectMembers.mockResolvedValue({ rows: [{ userId: 7, userName: '杨景锋', nickName: 'YJF', projectRole: 'creator', producerCode: 'YJF' }] })
    getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 21, episodeCode: 'EP001', episodeName: '第一集' }], total: 1, hasNext: false })
    getScenePage.mockResolvedValue({ rows: [{ sceneId: 31, sceneCode: '001', sceneName: '动力舱' }], total: 1, hasNext: false })
    listShotAssignees.mockResolvedValue({ rows: [{ userId: 7, userName: '杨景锋', nickName: 'YJF', projectRole: 'creator', producerCode: 'YJF' }], total: 1, hasNext: false })
    getShotPage.mockResolvedValue({ rows: [shotRow], total: 1, hasNext: false })
    getShotDetail.mockResolvedValue({ data: shotDetail(8, 41, 'S001', '镜头缓慢推进动力舱') })
    batchAssignShotTasks.mockResolvedValue({ data: { assignedShotIds: [41], assignedCount: 1 } })
    batchDeleteShots.mockResolvedValue({ data: { deletedShotIds: [41], deletedCount: 1 } })
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
    const queryButton = filterForm.findAllComponents(ElButton).find(button => button.text() === '查询')
    expect(queryButton.props('nativeType')).toBe('button')
    getShotPage.mockClear()
    await queryButton.trigger('click')
    await flushPromises()
    expect(getShotPage).toHaveBeenCalledWith(8, expect.objectContaining({ pageNum: 1 }), expect.anything())
    expect(wrapper.text()).toContain('LCFR · 罗刹夫人')
    expect(wrapper.text()).toContain('EP001 / 001 / S001')
    expect(wrapper.text()).toContain('镜头缓慢推进动力舱')
    expect(wrapper.text()).toContain('台词 / 对白')
    expect(wrapper.text()).toContain('动力系统恢复了吗？')
    expect(wrapper.text()).toContain('设备低频轰鸣声')
    expect(wrapper.text()).toContain('冷蓝色调')
    expect(wrapper.text()).toContain('保持画面压迫感')
    expect(wrapper.find('.shot-table-wrap').text()).toContain('杨景锋')
    expect(wrapper.text()).toContain('导入 Excel')
    expect(wrapper.text()).toContain('新建镜头')
    expect(findTag(wrapper, '场景 · 动力舱').props()).toMatchObject({ type: 'primary', size: 'small', effect: 'plain', round: true })
    expect(findTag(wrapper, '制作中').props()).toMatchObject({ type: 'warning', effect: 'light', round: true })
    expect(findTag(wrapper, '目录就绪').props()).toMatchObject({ type: 'success', effect: 'plain', round: true })
    expect(wrapper.find('.shot-chip').exists()).toBe(false)

    const viewSwitch = wrapper.findComponent(ElRadioGroup)
    viewSwitch.vm.$emit('update:modelValue', 'card')
    await flushPromises()
    expect(wrapper.find('.shot-card').exists()).toBe(true)
    viewSwitch.vm.$emit('update:modelValue', 'storyboard')
    await flushPromises()
    expect(wrapper.find('.story-frame').exists()).toBe(true)
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

    await filterForm.findAllComponents(ElButton).find(button => button.text() === '重置').trigger('click')
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

    await wrapper.findAll('button').find(button => button.text() === '详情').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/shots')
    expect(document.body.textContent).toContain('镜头详情 · S001')
    expect(document.body.textContent).toContain('制作信息')
    expect(getShotDetail).toHaveBeenCalledWith(8, 41, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })

  it('未开始镜头可勾选、编辑和批量删除，已开始镜头禁止删除', async () => {
    const notStartedShot = { ...shotRow, status: 'not_started' }
    getShotPage.mockResolvedValue({ rows: [notStartedShot], total: 1, hasNext: false })
    getShotDetail.mockResolvedValue({ data: shotDetail(8, 41, 'S001', '镜头缓慢推进动力舱') })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:shot:edit',
      'shotgrid:shot:archive'
    ])

    const checkbox = wrapper.findAllComponents({ name: 'ElCheckbox' }).find(item => item.attributes('aria-label') === '选择 S001')
    expect(checkbox.props('disabled')).toBe(false)
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).toContain('删除')
    checkbox.vm.$emit('change', true)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('批量删除')).trigger('click')
    await flushPromises()
    expect(batchDeleteShots).toHaveBeenCalledWith(8, [{ shotId: 41, lockVersion: 0 }])

    getShotPage.mockResolvedValue({ rows: [{ ...shotRow, status: 'in_progress' }], total: 1, hasNext: false })
    await wrapper.find('button[aria-label="刷新镜头"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAllComponents({ name: 'ElCheckbox' }).find(item => item.attributes('aria-label') === '选择 S001').props('disabled')).toBe(true)
    confirmSpy.mockRestore()
    wrapper.unmount()
  })

  it('可将当前页选中的镜头批量分配给项目制作人', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const { wrapper } = await mountView([
      'shotgrid:shot:list',
      'shotgrid:task:assign'
    ])

    wrapper.findAllComponents({ name: 'ElCheckbox' }).find(item => item.attributes('aria-label') === '选择 S001').vm.$emit('change', true)
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
    confirmButton.click()
    await flushPromises()

    expect(batchAssignShotTasks).toHaveBeenCalledWith(8, 7, [
      { shotId: 41, taskLockVersion: 4 }
    ])
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
      rows: [{ sheetName: 'EP001', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { sceneCode: '001', shotCode: 'S001', durationMs: 3000, description: '旧项目镜头', assetRequirements: [] } }]
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
    const oldImportDialog = wrapper.findComponent(ShotImportDialog).vm
    const oldImportGeneration = oldImportDialog.$props.operationGeneration
    const fileInput = document.body.querySelector('.import-flow input[type="file"]')
    const file = new File(['xlsx'], '旧项目镜头.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(fileInput, 'files', { configurable: true, value: [file] })
    fileInput.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    Array.from(document.body.querySelectorAll('.import-flow button'))
      .find(button => button.textContent.includes('检查文件'))
      .click()
    await flushPromises()
    expect(previewShotImport).toHaveBeenCalledWith(9, file, expect.anything())
    expect(document.body.textContent).toContain('旧项目镜头')
    expect(document.body.textContent).toContain('正式导入 1 行')

    await setElSelectValue(wrapper.find('.project-context').findComponent({ name: 'ElSelect' }), '8')
    await flushPromises()
    expect(document.body.querySelector('.import-flow')).toBeNull()
    expect(document.body.textContent).not.toContain('旧项目镜头')
    expect(document.body.textContent).not.toContain('正式导入 1 行')
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
    createShot.mockReset()
    createShot.mockResolvedValue({ data: { ...shotRow, shotId: 45, shotCode: 'S005' } })
    updateShot.mockReset()
    assignShotTask.mockReset()
    assignShotTask.mockResolvedValue({ data: { taskId: 71 } })
  })

  it('新建镜头由按钮点击触发 Form 校验，失败时拦截请求，通过后提交并可重置', async () => {
    const wrapper = mount(ShotFormDialog, {
      props: {
        projectId: 8,
        operationGeneration: 1,
        episodes: [{ episodeId: 21, episodeCode: 'EP001', episodeName: '第一集' }],
        members: [{ userId: 7, nickName: '杨景锋', projectRole: 'creator' }]
      },
      global: { components: formComponents }
    })
    const form = wrapper.findComponent(ElForm)
    const formItems = form.findAllComponents(ElFormItem)
    const formItem = prop => formItems.find(item => item.props('prop') === prop)
    const submitButton = wrapper.findAllComponents(ElButton).find(button => button.text() === '创建镜头')

    expect(form.props('model')).toMatchObject({ episodeId: '', sceneId: '', shotNo: null, sortOrder: 0, durationSeconds: 0 })
    expect(form.props('rules')).toMatchObject({
      episodeId: expect.any(Array),
      sceneId: expect.any(Array),
      shotNo: expect.any(Array),
      sortOrder: expect.any(Array),
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
    formItem('shotNo').findComponent(ElInputNumber).vm.$emit('update:modelValue', 5)
    formItem('sortOrder').findComponent(ElInputNumber).vm.$emit('update:modelValue', 2)
    formItem('durationSeconds').findComponent(ElInputNumber).vm.$emit('update:modelValue', 1.25)
    formItem('description').findComponent(ElInput).vm.$emit('update:modelValue', '  动力舱推进镜头  ')
    await flushPromises()
    await submitButton.trigger('click')
    await flushPromises()

    expect(createShot).toHaveBeenCalledWith(8, expect.objectContaining({
      sceneId: 31,
      shotNo: 5,
      durationMs: 1250,
      description: '动力舱推进镜头',
      sortOrder: 2,
      assetIds: []
    }))
    expect(wrapper.emitted('saved')).toHaveLength(1)

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '取消').trigger('click')
    await flushPromises()
    expect(form.props('model')).toMatchObject({ episodeId: '', sceneId: '', shotNo: null, sortOrder: 0, durationSeconds: 0, description: '' })
    expect(wrapper.emitted('close')).toHaveLength(1)
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
    const submitButton = wrapper.findAllComponents(ElButton).find(button => button.text() === '创建并分配任务')

    expect(form.props('rules')).toMatchObject({ assigneeUserId: expect.any(Array), priority: expect.any(Array), dueDate: expect.any(Array) })
    expect(formItems.map(item => item.props('prop'))).toEqual(['assigneeUserId', 'priority', 'dueDate', 'taskDescription'])
    expect(submitButton.props('nativeType')).toBe('button')

    await submitButton.trigger('click')
    await flushPromises()
    expect(assignShotTask).not.toHaveBeenCalled()

    await setElSelectValue(formItem('assigneeUserId').findComponent(ElSelect), '7')
    formItem('dueDate').findComponent(ElDatePicker).vm.$emit('update:modelValue', '2026-09-01')
    formItem('taskDescription').findComponent(ElInput).vm.$emit('update:modelValue', '完成镜头视频制作')
    await flushPromises()
    await submitButton.trigger('click')
    await flushPromises()

    expect(assignShotTask).toHaveBeenCalledWith(8, 41, {
      assigneeUserId: 7,
      taskDescription: '完成镜头视频制作',
      priority: 'normal',
      dueDate: '2026-09-01'
    })
    expect(wrapper.emitted('assigned')).toHaveLength(1)

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '取消').trigger('click')
    await flushPromises()
    expect(form.props('model')).toMatchObject({ assigneeUserId: '', dueDate: '', priority: 'normal' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
})

describe('镜头详情跨项目请求隔离', () => {
  beforeEach(() => {
    getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 21, episodeCode: 'EP001' }], total: 1, hasNext: false })
    getScenePage.mockResolvedValue({ rows: [{ sceneId: 31, sceneCode: '001' }], total: 1, hasNext: false })
    listShotAssignees.mockResolvedValue({ rows: [{ userId: 7, userName: '杨景锋', nickName: 'YJF', projectRole: 'creator', producerCode: 'YJF' }], total: 1, hasNext: false })
  })

  it('镜头详情的状态、目录、优先级、版本和关联资产使用 ElTag 动态类型', async () => {
    getShotDetail.mockResolvedValueOnce({ data: {
      ...shotDetail(8, 41, 'S001', '动力舱推进镜头'),
      status: 'revision',
      directoryStatus: 'failed',
      task: {
        assignee: { userId: 7, nickName: 'YJF' },
        taskStatus: 'pending_review',
        priority: 'urgent',
        dueDate: '2026-09-01',
        lockVersion: 3
      },
      latestVersion: { versionNumber: 'V002', businessFileName: 'LCFR_S001_V002.mp4', status: 'rejected' },
      assets: [
        { assetId: 2, assetName: '动力舱', assetType: 'Environment' },
        { assetId: 3, assetName: '女主', assetType: 'Character' },
        { assetId: 4, assetName: '手电筒', assetType: 'Prop' }
      ]
    } })

    const { wrapper } = await mountDetailView()
    expect(findTag(wrapper, '修改中').props()).toMatchObject({ type: 'danger', effect: 'light', round: true })
    expect(findTag(wrapper, '目录失败').props()).toMatchObject({ type: 'danger', effect: 'plain', round: true })
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
      if (projectId === 8) return Promise.resolve({ data: shotDetail(8, 41, 'S001', '旧项目镜头') })
      if (projectId === 9) return new Promise(resolve => { resolveProject9 = resolve })
      return Promise.resolve({ data: shotDetail(10, 61, 'S003', '当前项目镜头') })
    })
    const { wrapper, router } = await mountDetailView()
    expect(wrapper.text()).toContain('旧项目镜头')

    await wrapper.findAll('button').find(button => button.text().includes('编辑镜头')).trigger('click')
    expect(document.body.querySelector('.shot-form')).not.toBeNull()

    await router.push('/projects/9/shots/51')
    await flushPromises()
    expect(wrapper.text()).toContain('正在加载镜头详情')
    expect(wrapper.text()).not.toContain('旧项目镜头')
    expect(document.body.querySelector('.shot-form')).toBeNull()
    expect(wrapper.text()).not.toContain('编辑镜头')

    await router.push('/projects/10/shots/61')
    await flushPromises()
    expect(wrapper.text()).toContain('当前项目镜头')

    resolveProject9({ data: shotDetail(9, 51, 'S002', '过期项目镜头') })
    await flushPromises()
    expect(wrapper.text()).toContain('当前项目镜头')
    expect(wrapper.text()).not.toContain('过期项目镜头')
    wrapper.unmount()
  })

  it('旧镜头分配完成事件不会刷新或覆盖新路由上下文', async () => {
    getShotDetail.mockImplementation((projectId, shotId) => Promise.resolve({ data: shotDetail(
      projectId,
      shotId,
      projectId === 8 ? 'S001' : 'S002',
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
      targetProjectId === 8 ? 'S001' : 'S002',
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
