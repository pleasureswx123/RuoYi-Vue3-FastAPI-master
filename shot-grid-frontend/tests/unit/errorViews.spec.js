import { ElButton, ElIcon } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import ForbiddenView from '@/views/error/ForbiddenView.vue'
import ServiceUnavailableView from '@/views/error/ServiceUnavailableView.vue'
import { useSessionStore } from '@/store/modules/session'
import { getCurrentUser } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { installRouterGuard } from '@/router/guard'
import { setToken } from '@/utils/auth'

vi.mock('@/api/platform/auth', () => ({
  getCaptcha: vi.fn(), getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn()
}))
vi.mock('@/api/shot-grid/navigation', () => ({ getShotGridNavigation: vi.fn() }))

const routes = [
  { path: '/', name: 'root', component: { template: '<div>首页</div>' } },
  { path: '/assets', name: 'assets', component: { template: '<div>资产</div>' }, meta: { routeKey: 'assets' } },
  { path: '/login', name: 'login', component: { template: '<div>login</div>' }, meta: { public: true } },
  { path: '/forbidden', name: 'forbidden', component: ForbiddenView, meta: { public: true } },
  { path: '/service-unavailable', name: 'service-unavailable', component: ServiceUnavailableView, meta: { public: true } }
]

async function mountErrorView(component, path, guarded = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.signOut = vi.fn(async () => session.clearLocalSession())
  const router = createRouter({ history: createMemoryHistory(), routes })
  if (guarded) installRouterGuard(router, pinia)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [pinia, router], components: { ElButton, ElIcon } }
  })
  return { router, session, wrapper }
}

describe('错误页会话恢复出口', () => {
  it('服务恢复后重新加载原地址并重新校验账号与导航，不退出登录', async () => {
    setToken('recovery-test-token')
    getCurrentUser.mockRejectedValueOnce({ status: 503 }).mockResolvedValue({
      user: { userId: 1, userName: 'director' }, roles: [], permissions: []
    })
    getShotGridNavigation.mockResolvedValue({ data: [{ routeKey: 'assets', path: '/assets' }] })
    const { router, session, wrapper } = await mountErrorView(ServiceUnavailableView, '/assets?projectId=8', true)
    try {
      expect(router.currentRoute.value.name).toBe('service-unavailable')
      const retry = wrapper.findAllComponents(ElButton).find(button => button.text() === '重新加载')
      await retry.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/assets?projectId=8')
      expect(session.status).toBe('ready')
      expect(session.user.userId).toBe(1)
      expect(session.signOut).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it('重试仍失败时保留原目标，恢复后可再次重试且不会重复提交', async () => {
    setToken('recovery-test-token')
    getCurrentUser.mockRejectedValueOnce({ status: 503 }).mockRejectedValueOnce({ status: 503 })
    const { router, wrapper } = await mountErrorView(ServiceUnavailableView, '/assets?projectId=8', true)
    try {
      const retry = wrapper.findAllComponents(ElButton).find(button => button.text() === '重新加载')
      await retry.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('service-unavailable')
      expect(router.currentRoute.value.query.retry).toBe('/assets?projectId=8')
      expect(retry.props('loading')).toBe(false)
      let completeIdentity
      getCurrentUser.mockImplementationOnce(() => new Promise(resolve => { completeIdentity = resolve }))
      getShotGridNavigation.mockResolvedValue({ data: [{ routeKey: 'assets', path: '/assets' }] })
      await retry.trigger('click')
      await flushPromises()
      expect(retry.props('loading')).toBe(true)
      const calls = getCurrentUser.mock.calls.length
      await retry.trigger('click')
      expect(getCurrentUser).toHaveBeenCalledTimes(calls)
      completeIdentity({ user: { userId: 1, userName: 'director' }, roles: [], permissions: [] })
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/assets?projectId=8')
    } finally { wrapper.unmount() }
  })

  it.each(['https://evil.example/path', '//evil.example/path', '/service-unavailable?retry=/assets', ''])('不跳转到外部地址或异常页自身：%s', async target => {
    const { router, wrapper } = await mountErrorView(ServiceUnavailableView, `/service-unavailable?retry=${encodeURIComponent(target)}`)
    try {
      await wrapper.findAllComponents(ElButton).find(button => button.text() === '重新加载').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/')
    } finally { wrapper.unmount() }
  })

  it('持续 403 时可以清理会话并返回登录页', async () => {
    const { router, session, wrapper } = await mountErrorView(ForbiddenView, '/forbidden')

    await wrapper.findAll('button').find(button => button.text().includes('退出并重新登录')).trigger('click')
    await flushPromises()

    expect(session.signOut).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })

  it('持续 5xx 时可以清理会话并返回登录页', async () => {
    const { router, session, wrapper } = await mountErrorView(ServiceUnavailableView, '/service-unavailable')

    await wrapper.findAll('button').find(button => button.text().includes('退出并重新登录')).trigger('click')
    await flushPromises()

    expect(session.signOut).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })
})
