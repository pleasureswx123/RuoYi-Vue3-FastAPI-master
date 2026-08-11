import { ElButton, ElIcon } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import ForbiddenView from '@/views/error/ForbiddenView.vue'
import ServiceUnavailableView from '@/views/error/ServiceUnavailableView.vue'
import { useSessionStore } from '@/store/modules/session'

const routes = [
  { path: '/login', component: { template: '<div>login</div>' } },
  { path: '/forbidden', component: ForbiddenView },
  { path: '/service-unavailable', component: ServiceUnavailableView }
]

async function mountErrorView(component, path) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.signOut = vi.fn(async () => session.clearLocalSession())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [pinia, router], components: { ElButton, ElIcon } }
  })
  return { router, session, wrapper }
}

describe('错误页会话恢复出口', () => {
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
