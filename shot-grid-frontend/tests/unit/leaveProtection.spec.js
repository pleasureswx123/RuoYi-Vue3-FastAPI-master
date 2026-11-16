import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { useLeaveProtection } from '@/composables/useLeaveProtection'

describe('草稿离开保护', () => {
  it('取消切项目和切模块保留页面，确认后离开；刷新提示随草稿与卸载清理', async () => {
    const dirty = ref(true)
    const confirm = vi.fn().mockResolvedValue(false)
    const page = defineComponent({ setup() { useLeaveProtection(confirm, () => dirty.value) }, template: '<div>草稿</div>' })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/shots', component: page }, { path: '/assets', component: { template: '<div>资产</div>' } }
    ] })
    await router.push('/shots?projectId=1')
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router] } })
    await flushPromises()
    try {
      const unload = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(unload); expect(unload.defaultPrevented).toBe(true)
      await router.push('/shots?projectId=2'); expect(router.currentRoute.value.query.projectId).toBe('1')
      await router.push('/assets'); expect(wrapper.text()).toBe('草稿')
      confirm.mockResolvedValue(true)
      await router.push('/assets'); await flushPromises(); expect(wrapper.text()).toBe('资产')
      const cleanUnload = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(cleanUnload); expect(cleanUnload.defaultPrevented).toBe(false)
    } finally { wrapper.unmount() }
  })
})
