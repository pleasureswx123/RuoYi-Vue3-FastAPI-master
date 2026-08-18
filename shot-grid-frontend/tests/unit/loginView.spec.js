import { ElButton, ElForm, ElFormItem, ElIcon, ElInput } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import { useSessionStore } from '@/store/modules/session'
import LoginView from '@/views/login/LoginView.vue'

describe('独立业务端登录页', () => {
  async function mountLoginView() {
    const pinia = createPinia()
    setActivePinia(pinia)
    const session = useSessionStore()
    session.loadCaptcha = vi.fn(async () => undefined)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/login', component: LoginView }]
    })
    await router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginView, {
      global: {
        plugins: [pinia, router],
        components: { ElButton, ElForm, ElFormItem, ElIcon, ElInput }
      }
    })
    return { wrapper, session }
  }

  it('密码字段始终使用 password 类型且不持久化密码', async () => {
    const { wrapper } = await mountLoginView()
    const passwordInput = wrapper.find('input[autocomplete="current-password"]')

    expect(passwordInput.exists()).toBe(true)
    expect(passwordInput.attributes('type')).toBe('password')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)

    wrapper.unmount()
  })

  it('身份初始化失败后也立即清空页面内的明文密码', async () => {
    const { wrapper, session } = await mountLoginView()
    session.captcha.enabled = false
    session.signIn = vi.fn(async () => {
      throw new Error('身份服务不可用')
    })
    const usernameInput = wrapper.find('input[autocomplete="username"]')
    const passwordInput = wrapper.find('input[autocomplete="current-password"]')
    await usernameInput.setValue('creator')
    await passwordInput.setValue('plain-password')

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '进入工作区').trigger('click')
    await flushPromises()

    expect(session.signIn).toHaveBeenCalledOnce()
    expect(passwordInput.element.value).toBe('')
    wrapper.unmount()
  })
})
