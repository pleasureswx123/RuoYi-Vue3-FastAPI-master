import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { detailResource } from '@/composables/useDetailNavigation'
import { useSessionStore } from '@/store/modules/session'

vi.mock('@/views/version/VersionDetailView.vue', () => ({ default: { props: { targetVersionId: Number, embedded: Boolean }, template: '<p>版本 {{ targetVersionId }} {{ embedded }}</p>' } }))
vi.mock('@/views/review/ReviewDetailView.vue', () => ({ default: { props: { targetReviewListId: Number, embedded: Boolean }, template: '<p>审核 {{ targetReviewListId }} {{ embedded }}</p>' } }))
vi.mock('@/views/task/TaskDetailView.vue', () => ({ default: { props: { targetTaskId: Number, embedded: Boolean }, template: '<p>任务 {{ targetTaskId }} {{ embedded }}</p>' } }))
function render() {
  return mount(RelatedDetailDrawer, { global: { stubs: {
    ElDrawer: { props: ['modelValue'], emits: ['update:modelValue', 'closed'], template: '<section v-if="modelValue"><slot name="header" /><slot /><button class="close" @click="$emit(\'update:modelValue\', false); $emit(\'closed\')">关闭</button></section>' },
    ElButton: { template: '<button><slot /></button>' },
    ElAlert: { props: ['title'], template: '<p>{{ title }}</p>' }
  } } })
}
beforeEach(() => {
  setActivePinia(createPinia())
  useSessionStore().permissions = ['*:*:*']
})
describe('镜头关联详情抽屉', () => {
  it('仅接管合法的任务、版本、审核详情导航', () => {
    expect(detailResource({ name: 'version-detail', params: { versionId: 29 } })).toEqual({ type: 'version', id: 29 })
    expect(detailResource('/reviews/87')).toEqual({ type: 'review', id: 87 })
    expect(detailResource('/tasks/69#version-workspace')).toEqual({ type: 'task', id: 69 })
    expect(detailResource('/shots')).toBeNull()
    expect(detailResource('/versions/0')).toBeNull()
  })
  it('传递明确实体 ID，可返回上一层，关闭后清空上下文', async () => {
    const wrapper = render()
    wrapper.vm.open('/versions/29')
    await flushPromises()
    expect(wrapper.text()).toContain('版本 29 true')
    wrapper.vm.open('/reviews/87')
    await flushPromises()
    expect(wrapper.text()).toContain('审核 87 true')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('版本 29 true')
    await wrapper.find('.close').trigger('click')
    wrapper.vm.open('/tasks/69')
    await flushPromises()
    expect(wrapper.text()).toContain('任务 69 true')
    expect(wrapper.text()).not.toContain('返回上一层详情')
    wrapper.unmount()
  })
  it('缺少详情权限时显示明确提示，不挂载详情', async () => {
    useSessionStore().permissions = []
    const wrapper = render()
    wrapper.vm.open('/tasks/69')
    await flushPromises()
    expect(wrapper.text()).toContain('没有此详情的查看权限')
    expect(wrapper.text()).not.toContain('任务 69')
    wrapper.unmount()
  })
})
