import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentUser } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { installRouterGuard } from '@/router/guard'
import { setToken } from '@/utils/auth'

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
  beforeEach(() => {
    getCurrentUser.mockResolvedValue({
      user: { userId: 1, userName: 'director' },
      roles: [],
      permissions: []
    })
    getShotGridNavigation.mockResolvedValue({
      data: [{ routeKey: 'workbench', title: '工作台', path: '/workbench', icon: 'dashboard', orderNum: 1 }]
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
    expect(router.currentRoute.value.path).toBe('/workbench')

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
