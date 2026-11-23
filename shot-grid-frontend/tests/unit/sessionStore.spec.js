import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElButton, ElDatePicker, ElSelect } from 'element-plus'
import AppLayout from '@/layout/AppLayout.vue'
import { getEpisodePage, getScenePage, listShotAssignees } from '@/api/shot-grid/shots'
import { getProjectDetail } from '@/api/shot-grid/projects'
import { createPinia, setActivePinia } from 'pinia'
import Cookies from 'js-cookie'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCaptcha, getCurrentUser, login, logout } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { useSessionStore } from '@/store/modules/session'
import { ApiError } from '@/utils/apiError'
import { setToken } from '@/utils/auth'

vi.mock('@/api/platform/auth', () => ({
  getCaptcha: vi.fn(),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn()
}))
vi.mock('@/components/search/GlobalSearchDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/api/shot-grid/shots', () => ({ getEpisodePage: vi.fn(), getScenePage: vi.fn(), listShotAssignees: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({ getProjectDetail: vi.fn() }))
vi.mock('@/api/shot-grid/navigation', () => ({ getShotGridNavigation: vi.fn() }))

const navigation = [
  { routeKey: 'workbench', title: '工作台', path: '/workbench', icon: 'dashboard', orderNum: 1 },
  { routeKey: 'projects', title: '项目', path: '/projects', icon: 'project', orderNum: 2 }
]

describe('独立业务端会话状态', () => {
  it('镜头浏览记忆只属于当前项目和会话，切项目及退出时清空', () => {
    const session = useSessionStore()
    session.selectProject(8)
    session.shotBrowseState = { projectId: 8, shotId: 41 }
    session.selectProject(8)
    expect(session.shotBrowseState.shotId).toBe(41)
    session.selectProject(9)
    expect(session.shotBrowseState).toBeNull()
    session.shotBrowseState = { projectId: 9 }
    session.clearLocalSession()
    expect(session.shotBrowseState).toBeNull()
  })
  beforeEach(() => {
    setActivePinia(createPinia())
    login.mockResolvedValue({ code: 200, token: 'token-1' })
    getCurrentUser.mockResolvedValue({
      code: 200,
      user: {
        userId: 7,
        userName: 'creator',
        nickName: '制作人',
        password: 'must-never-enter-the-store',
        phonenumber: '13800000000',
        dept: { deptId: 2, deptName: '策划部', ancestors: '0,1' }
      },
      roles: ['creator'],
      permissions: ['shotgrid:project:list']
    })
    getShotGridNavigation.mockResolvedValue({ code: 200, data: navigation })
    logout.mockResolvedValue({ code: 200 })
  })

  it('登录后只保存安全用户投影并只初始化一次', async () => {
    const session = useSessionStore()

    await session.signIn({ username: ' creator ', password: 'secret', code: '1234' })
    await Promise.all([session.bootstrap(), session.bootstrap()])

    expect(session.user).toEqual({
      userId: 7,
      userName: 'creator',
      nickName: '制作人',
      avatar: '',
      dept: { deptId: 2, deptName: '策划部' }
    })
    expect(session.user.password).toBeUndefined()
    expect(session.user.phonenumber).toBeUndefined()
    expect(session.displayName).toBe('creator')
    expect(getCurrentUser).toHaveBeenCalledTimes(1)
    expect(getShotGridNavigation).toHaveBeenCalledTimes(1)
  })

  it.each([[true, true], [true, false], [false, true]])('按桌面环境 %s 和记忆选择 %s 设置会话期限', async (desktop, remember) => {
    vi.stubGlobal('__SHOTGRID_DESKTOP__', desktop)
    try {
      const exp = Math.floor(Date.now() / 1000) + 3600
      const token = 'test.' + btoa(JSON.stringify({ exp })) + '.test'
      login.mockResolvedValueOnce({ token })
      const write = vi.spyOn(Cookies, 'set')
      const session = useSessionStore()
      await session.signIn({ username: 'creator', password: 'secret', remember })
      expect(write).toHaveBeenCalledWith('Admin-Token', token, expect.objectContaining({
        expires: desktop && remember ? new Date(exp * 1000) : undefined
      }))
      expect(login.mock.calls[0][0]).not.toHaveProperty('remember')
      await session.signOut()
      expect(Cookies.get('Admin-Token')).toBeUndefined()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('退出接口失败也清理本地登录态', async () => {
    const session = useSessionStore()
    await session.signIn({ username: 'creator', password: 'secret' })
    logout.mockRejectedValueOnce(new Error('服务端退出失败'))

    await expect(session.signOut()).rejects.toThrow('服务端退出失败')
    expect(session.token).toBe('')
    expect(session.user).toBeNull()
  })

  it('加载验证码时保留后端开关', async () => {
    getCaptcha.mockResolvedValue({ captchaEnabled: false, img: '', uuid: '' })
    const session = useSessionStore()

    await session.loadCaptcha()

    expect(session.captcha).toMatchObject({ enabled: false, image: '', uuid: '' })
  })

  it('用户响应缺少有效 userId 时失败关闭并清理会话', async () => {
    getCurrentUser.mockResolvedValueOnce({ user: null, roles: [], permissions: [] })
    const session = useSessionStore()

    await expect(session.signIn({ username: 'creator', password: 'secret' })).rejects.toMatchObject({
      status: 401,
      errorKey: 'SG_CURRENT_USER_INVALID'
    })
    expect(session.token).toBe('')
    expect(session.status).toBe('anonymous')
  })

  it('初始化失败只缓存不含 Authorization 的安全错误摘要', async () => {
    setToken('token-1')
    getCurrentUser.mockRejectedValueOnce(
      new ApiError('服务异常', {
        status: 503,
        code: 503,
        errorKey: 'SG_SERVICE_UNAVAILABLE',
        response: { config: { headers: { Authorization: 'Bearer secret-token' } } }
      })
    )
    const session = useSessionStore()

    await expect(session.bootstrap()).rejects.toMatchObject({ status: 503 })

    expect(session.bootstrapError).toEqual({
      status: 503,
      httpStatus: null,
      code: 503,
      errorKey: 'SG_SERVICE_UNAVAILABLE',
      message: '服务异常'
    })
    expect(JSON.stringify(session.bootstrapError)).not.toContain('secret-token')
  })
})


describe('项目工作区上下文', () => {
  it('精简布局只用于纯制作账号，管理权限或管理角色仍保留原界面', () => {
    const session = useSessionStore()
    session.roles = ['shotgrid_creator']
    expect(session.isCreatorWorkspace).toBe(true)
    session.selectProject(8)
    Object.assign(session.workspaceFilters, { assigneeUserId: '1', productionFrom: '2026-11-02' })
    expect(session.workbenchParams()).toEqual({ projectId: '8' })
    session.permissions = ['shotgrid:version:review']
    expect(session.isCreatorWorkspace).toBe(false)
    expect(session.workbenchParams()).toMatchObject({ projectId: '8', assigneeUserId: '1', productionFrom: '2026-11-02' })
    session.permissions = []
    session.roles.push('shotgrid_director')
    expect(session.isCreatorWorkspace).toBe(false)
  })
  beforeEach(() => setActivePinia(createPinia()))
  it('切换项目与退出登录清空全部筛选，同项目导航保留筛选', () => {
    const session = useSessionStore()
    session.selectProject(7)
    session.workspaceFilters.sceneId = '12'
    session.workspaceFilters.assigneeUserId = '3'
    session.selectProject('7')
    expect(session.workspaceFilters.sceneId).toBe('12')
    session.selectProject(8)
    expect(Object.values(session.workspaceFilters).every(value => value === '')).toBe(true)
    session.clearLocalSession()
    expect(session.activeProjectId).toBe('')
  })
  it('只请求已选项目，迟到响应不进入新项目上下文', async () => {
    const session = useSessionStore()
    session.selectProject(7)
    let complete
    getProjectDetail.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const pending = session.loadWorkspaceProjects()
    expect(getProjectDetail).toHaveBeenLastCalledWith('7', {})
    session.selectProject(8)
    complete({ data: { projectId: 7 } })
    expect(await pending).toEqual([])
  })
})


it('侧边栏场次、分类与制作筛选按实际组件事件生效，校验失败不应用', async () => {
  let assetMounts = 0
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.permissions = ['*:*:*']
  session.navigation = [{ routeKey: 'projects' }, { routeKey: 'shots' }, { routeKey: 'assets' }]
  session.selectProject(7)
  getProjectDetail.mockResolvedValue({ data: { projectId: 7, projectName: '测试项目' } })
  getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 2, episodeName: '第一集' }], total: 1 })
  getScenePage.mockResolvedValue({ rows: [{ sceneId: 4, sceneNo: 1, sceneName: '开场' }], total: 1 })
  listShotAssignees.mockResolvedValue({ rows: [{ userId: 3, userName: '制作人甲' }], total: 1 })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/shots', name: 'shots', component: { template: '<div />' }, meta: { routeKey: 'shots' } },
    { path: '/assets', name: 'assets', component: { created: () => { assetMounts++ }, template: '<div />' }, meta: { routeKey: 'assets' } }
  ] })
  await router.push('/shots?projectId=7')
  const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  const button = label => wrapper.findAllComponents(ElButton).find(item => item.text() === label)
  expect(wrapper.text()).toContain('测试项目')
  wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', '3')
  wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2026-11-02', '2026-11-01'])
  await button('应用筛选').trigger('click')
  await flushPromises()
  expect(session.workspaceFilters.assigneeUserId).toBe('')
  await vi.waitFor(() => expect(wrapper.text()).toContain('请选择有效的制作周期'))
  wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2026-11-01', '2026-11-02'])
  await button('应用筛选').trigger('click')
  await flushPromises()
  expect(session.productionParams()).toMatchObject({ projectId: '7', assigneeUserId: '3', productionFrom: '2026-11-01', productionTo: '2026-11-02' })
  expect(button('应用筛选').props('loading')).toBe(false)
  await button('重置').trigger('click')
  await flushPromises()
  expect(session.workspaceFilters.productionFrom).toBe('')
  expect(session.workspaceFilters.assigneeUserId).toBe('')
  const headings = () => wrapper.findAll('.el-sub-menu__title')
  await headings().find(item => item.text().includes('镜头管理')).trigger('click')
  await flushPromises()
  await headings().find(item => item.text().includes('第一集')).trigger('click')
  await flushPromises()
  await wrapper.findAll('.el-menu-item').find(item => item.text().includes('开场')).trigger('click')
  await flushPromises()
  expect(session.workspaceFilters).toMatchObject({ episodeId: '2', sceneId: '4' })
  await headings().find(item => item.text().includes('资产库管理')).trigger('click')
  await flushPromises()
  await wrapper.findAll('.el-menu-item').find(item => item.text() === '道具').trigger('click')
  await flushPromises()
  expect(session.workspaceFilters.assetType).toBe('Prop')
  expect(router.currentRoute.value.query.projectId).toBe('7')
  expect(assetMounts).toBe(1)
  session.workspaceFilters.assigneeUserId = '3'
  await flushPromises()
  expect(assetMounts).toBe(1)
  session.selectProject(8)
  await flushPromises()
  expect(assetMounts).toBe(2)
  wrapper.unmount()
})


it('制作侧边栏提供项目镜头与资产入口，提交记录点击携带 tab，项目入口保留', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.roles = ['shotgrid_creator']
  session.permissions = ['shotgrid:task:list', 'shotgrid:version:list']
  session.navigation = ['projects', 'workbench', 'shots', 'assets', 'reviews', 'files'].map(routeKey => ({ routeKey }))
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/workbench', name: 'workbench', component: { template: '<div />' }, meta: { routeKey: 'workbench' } },
    { path: '/projects', name: 'projects', component: { template: '<div />' } }
  ] })
  await router.push('/workbench')
  const wrapper = mount(AppLayout, { global: { plugins: [pinia, router] } })
  await flushPromises()
  expect(wrapper.findAll('.el-menu-item').map(item => item.text())).toEqual(['我的任务', '镜头管理', '资产库管理', '提交记录'])
  expect(wrapper.find('[aria-label="制作筛选"]').exists()).toBe(false)
  await wrapper.findAll('.el-menu-item').find(item => item.text() === '提交记录').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.tab).toBe('submissions')
  expect(wrapper.find('h1').text()).toBe('提交记录')
  await wrapper.get('[aria-label="切换项目"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('projects')
  expect(session.navigation).toHaveLength(6)
  session.navigation = [{ routeKey: 'workbench' }]
  await flushPromises()
  expect(wrapper.findAll('.el-menu-item').map(item => item.text())).toEqual(['我的任务', '提交记录'])
  wrapper.unmount()
})

it('制作人员按已选项目浏览全部镜头和资产，并可筛选场次与分类', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.roles = ['shotgrid_creator']
  session.user = { userId: 100 }
  session.permissions = ['shotgrid:shot:list', 'shotgrid:asset:list', 'shotgrid:episode:list', 'shotgrid:scene:list']
  session.navigation = ['workbench', 'shots', 'assets'].map(routeKey => ({ routeKey }))
  session.selectProject(7)
  getProjectDetail.mockResolvedValue({ data: { projectId: 7, projectName: '制作项目' } })
  getEpisodePage.mockResolvedValue({ rows: [{ episodeId: 2, episodeName: '第一集' }], total: 1 })
  getScenePage.mockResolvedValue({ rows: [{ sceneId: 4, sceneNo: 1, sceneName: '开场' }], total: 1 })
  const router = createRouter({ history: createMemoryHistory(), routes: ['workbench', 'shots', 'assets'].map(name => ({
    path: `/${name}`, name, component: { template: '<div />' }, meta: { routeKey: name }
  })) })
  await router.push('/workbench?projectId=7')
  const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  const menu = text => wrapper.findAll('.el-menu-item').find(item => item.text() === text)
  const heading = text => wrapper.findAll('.el-sub-menu__title').find(item => item.text().includes(text))
  await heading('镜头管理').trigger('click')
  await flushPromises()
  await menu('全部镜头').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.fullPath).toBe('/shots?projectId=7')
  expect(session.workspaceFilters).toMatchObject({ assigneeUserId: '', episodeId: '', sceneId: '' })
  await heading('第一集').trigger('click')
  await flushPromises()
  await menu('场 1 · 开场').trigger('click')
  await flushPromises()
  expect(session.workspaceFilters).toMatchObject({ episodeId: '2', sceneId: '4', assigneeUserId: '' })
  await heading('资产库管理').trigger('click')
  await flushPromises()
  await menu('角色').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.fullPath).toBe('/assets?projectId=7')
  expect(session.workspaceFilters.assetType).toBe('Character')
  await menu('全部资产').trigger('click')
  await flushPromises()
  expect(session.workspaceFilters).toMatchObject({ assetType: '', assigneeUserId: '' })
  expect(session.workbenchParams()).toEqual({ projectId: '7' })
  expect(session.permissions).not.toContain('shotgrid:task:assign')
  wrapper.unmount()
})
