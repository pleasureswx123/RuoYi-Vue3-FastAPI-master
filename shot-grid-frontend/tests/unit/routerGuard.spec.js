import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentUser } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { installRouterGuard } from '@/router/guard'
import { setToken } from '@/utils/auth'
import { useSessionStore } from '@/store/modules/session'

// 路由用例不验证进度动画，隔离其延迟计时器，避免环境销毁后访问 document。
vi.mock('nprogress', () => ({ default: { configure: vi.fn(), start: vi.fn(), done: vi.fn() } }))

vi.mock('@/api/platform/auth', () => ({
  getCaptcha: vi.fn(),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn()
}))
vi.mock('@/api/shot-grid/navigation', () => ({ getShotGridNavigation: vi.fn() }))
vi.mock('@/utils/request', () => ({ setSessionExpiredHandler: vi.fn() }))

const component = { template: '<div />' }
const routes = [
  { path: '/projects', name: 'projects', component, meta: { routeKey: 'projects' } },
  { path: '/login', name: 'login', component, meta: { public: true } },
  { path: '/service-unavailable', name: 'service-unavailable', component, meta: { public: true } },
  { path: '/forbidden', name: 'forbidden', component, meta: { public: true } },
  { path: '/', name: 'root', component },
  { path: '/workbench', name: 'workbench', component, meta: { routeKey: 'workbench' } },
  { path: '/shots', name: 'shots', component, meta: { routeKey: 'shots' } }
]

function createGuardedRouter() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  installRouterGuard(router, createPinia())
  return router
}

describe('独立业务端路由守卫', () => {
  it('取消导航不提前切换项目或清空原上下文', async () => {
    setToken('test-session')
    const pinia = createPinia()
    const router = createRouter({ history: createMemoryHistory(), routes })
    installRouterGuard(router, pinia)
    await router.push('/workbench?projectId=8')
    const session = useSessionStore(pinia)
    expect(session.activeProjectId).toBe('8')
    const remove = router.beforeResolve(() => false)
    await router.push('/workbench?projectId=9')
    expect(session.activeProjectId).toBe('8')
    await router.push('/projects')
    expect(session.activeProjectId).toBe('8')
    remove()
    await router.push('/workbench?projectId=9')
    expect(session.activeProjectId).toBe('9')
  })
  it('纯制作人默认进入本人任务，不需要先选项目，仍拒绝未授权模块', async () => {
    setToken('token-creator')
    getCurrentUser.mockResolvedValue({ user: { userId: 100 }, roles: ['shotgrid_creator'], permissions: ['shotgrid:task:list'] })
    getShotGridNavigation.mockResolvedValue({ data: [{ routeKey: 'workbench', path: '/workbench' }, { routeKey: 'projects', path: '/projects' }] })
    const router = createGuardedRouter()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('workbench')
    await router.push('/shots')
    expect(router.currentRoute.value.name).toBe('forbidden')
  })
  it('同时承担管理职责的制作账号仍先选择项目', async () => {
    setToken('token-manager')
    getCurrentUser.mockResolvedValue({ user: { userId: 100 }, roles: ['shotgrid_creator', 'shotgrid_director'], permissions: [] })
    const router = createGuardedRouter()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('projects')
  })
  beforeEach(() => {
    getCurrentUser.mockResolvedValue({
      user: { userId: 1, userName: 'director' },
      roles: [],
      permissions: []
    })
    getShotGridNavigation.mockResolvedValue({
      data: [{ routeKey: 'projects', title: '项目', path: '/projects', orderNum: 2 }, { routeKey: 'workbench', title: '工作台', path: '/workbench', icon: 'dashboard', orderNum: 1 }]
    })
  })

  it('匿名访问保留站内 redirect 后进入登录页', async () => {
    const router = createGuardedRouter()

    await router.push('/shots?status=doing')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/shots?status=doing')
  })

  it('根路径跳到首个授权模块，已知但无权的模块进入 403', async () => {
    setToken('token-1')
    const router = createGuardedRouter()

    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/projects')

    await router.push('/shots')
    expect(router.currentRoute.value.name).toBe('forbidden')
  })

  it('身份或导航服务失败时不伪装成空菜单', async () => {
    setToken('token-1')
    getCurrentUser.mockRejectedValueOnce({ status: 503 })
    const router = createGuardedRouter()

    await router.push('/workbench')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('service-unavailable')
  })

  it('导航权限不足时进入 403 而不是服务异常页', async () => {
    setToken('token-1')
    getShotGridNavigation.mockRejectedValue({ status: 403 })
    const router = createGuardedRouter()

    await router.push('/workbench')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('forbidden')
    expect(getShotGridNavigation).toHaveBeenCalledTimes(1)
  })
})


it('未选项目不能进入跨项目工作台，深链带项目可恢复上下文', async () => {
  setToken('token-1')
  getCurrentUser.mockResolvedValue({ user: { userId: 1 }, roles: [], permissions: [] })
  getShotGridNavigation.mockResolvedValue({ data: [
    { routeKey: 'projects', path: '/projects' }, { routeKey: 'workbench', path: '/workbench' }
  ] })
  const router = createGuardedRouter()
  await router.push('/workbench')
  expect(router.currentRoute.value.name).toBe('projects')
  await router.push('/workbench?projectId=12')
  expect(router.currentRoute.value.name).toBe('workbench')
  await router.push('/projects')
  await router.push('/workbench')
  expect(router.currentRoute.value.name).toBe('projects')
})
