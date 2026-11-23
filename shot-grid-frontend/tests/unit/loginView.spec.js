import 'fake-indexeddb/auto'
import { ElButton, ElCheckbox, ElForm, ElFormItem, ElIcon, ElInput } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSessionStore } from '@/store/modules/session'
import { rememberedLoginKey, readRememberedLogin } from '@/utils/rememberedLogin'
import LoginView from '@/views/login/LoginView.vue'

describe('独立业务端登录页', () => {
  beforeEach(() => localStorage.clear())

  afterEach(() => vi.unstubAllGlobals())

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
        components: { ElCheckbox, ElButton, ElForm, ElFormItem, ElIcon, ElInput }
      }
    })
    await flushPromises()
    return { wrapper, session }
  }

  it('默认关闭记忆且密码框保持遮蔽', async () => {
    const { wrapper } = await mountLoginView()
    const passwordInput = wrapper.find('input[autocomplete="current-password"]')

    expect(passwordInput.exists()).toBe(true)
    expect(passwordInput.attributes('type')).toBe('password')
    expect(wrapper.get('input[type=checkbox]').element.checked).toBe(false)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)

    wrapper.unmount()
  })

  it.each([
    ['桌面端', true],
    ['Web 端', false]
  ])('%s 首次使用对应默认值，手动切换后无需登录即可记住', async (_name, desktop) => {
    vi.stubGlobal('__SHOTGRID_DESKTOP__', desktop)
    const { wrapper } = await mountLoginView()
    const checkbox = wrapper.get('input[type=checkbox]')
    expect(checkbox.element.checked).toBe(desktop)
    await checkbox.setValue(!desktop)
    wrapper.unmount()
    const next = (await mountLoginView()).wrapper
    expect(next.get('input[type=checkbox]').element.checked).toBe(!desktop)
    expect(localStorage.getItem(rememberedLoginKey)).toBeNull()
    next.unmount()
  })

  it('勾选后仅保存成功登录的凭据，重开时回填，取消后立即忘记', async () => {
    const { wrapper, session } = await mountLoginView()
    session.captcha.enabled = false
    session.signIn = vi.fn().mockRejectedValueOnce(new Error('登录失败')).mockResolvedValue(undefined)
    const account = '测试制作人'
    const password = ' 密码-123! '
    const submit = wrapper.get('button.login-submit')
    await wrapper.get('input[autocomplete=username]').setValue(account)
    await wrapper.get('input[autocomplete=current-password]').setValue(password)
    await wrapper.get('input[type=checkbox]').setValue(true)
    await submit.trigger('click')
    await flushPromises()
    expect(localStorage.getItem(rememberedLoginKey)).toBeNull()
    await wrapper.get('input[autocomplete=current-password]').setValue(password)
    await submit.trigger('click')
    await vi.waitFor(() => expect(session.signIn).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(localStorage.getItem(rememberedLoginKey)).toBeTruthy())
    expect(localStorage.getItem(rememberedLoginKey)).not.toContain(password)
    expect(await readRememberedLogin()).toEqual({ username: account, password })
    wrapper.unmount()
    const next = (await mountLoginView()).wrapper
    await vi.waitFor(() => expect(next.get('input[autocomplete=username]').element.value).toBe(account))
    expect(next.get('input[autocomplete=username]').element.value).toBe(account)
    expect(next.get('input[autocomplete=current-password]').element.value).toBe(password)
    await next.get('input[type=checkbox]').setValue(false)
    expect(localStorage.getItem(rememberedLoginKey)).toBeNull()
    expect(next.get('input[autocomplete=current-password]').element.value).toBe('')
    next.unmount()
    const reopened = (await mountLoginView()).wrapper
    expect(reopened.get('input[autocomplete=username]').element.value).toBe('')
    expect(reopened.get('input[type=checkbox]').element.checked).toBe(false)
    reopened.unmount()
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
