import { shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import { detailNavigationKey } from '@/composables/useDetailNavigation'
import { useSessionStore } from '@/store/modules/session'
import TaskDetailView from '@/views/task/TaskDetailView.vue'
import VersionDetailView from '@/views/version/VersionDetailView.vue'
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn(() => new Promise(() => {})), updateTask: vi.fn() }))
vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn(() => new Promise(() => {})) }))
vi.mock('@/api/shot-grid/reviews', () => ({ getTaskIssues: vi.fn().mockResolvedValue({ data: [] }) }))
const localOpen = vi.fn()
const drawer = { name: 'RelatedDetailDrawer', methods: { open: localOpen }, template: '<div />' }
beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()); useSessionStore().permissions = ['*:*:*'] })
const entries = [
  ['镜头及资产任务', TaskDetailView, { targetTaskId: 31 }, 'handleReopened'],
  ['版本详情', VersionDetailView, { targetVersionId: 41 }, 'reopened']
]
it.each(entries)('%s 在父抽屉内切换审核，不关闭父抽屉或另开一层', async (_name, component, props, handler) => {
  const parentOpen = vi.fn(() => true)
  const wrapper = shallowMount(component, { props: { ...props, embedded: true }, global: { provide: { [detailNavigationKey]: parentOpen }, stubs: { RelatedDetailDrawer: drawer } } })
  wrapper.vm[handler]({ autoReviewListId: 87 })
  await flushPromises()
  expect(parentOpen).toHaveBeenCalledWith('/reviews/87')
  expect(localOpen).not.toHaveBeenCalled()
  expect(wrapper.emitted('completed')).toBeUndefined()
  wrapper.unmount()
})
it.each(entries)('%s 独立页面刷新期间保留审核抽屉实例', async (_name, component, props, handler) => {
  const wrapper = shallowMount(component, { props, global: { stubs: { RelatedDetailDrawer: drawer } } })
  const instance = wrapper.findComponent(drawer).vm
  wrapper.vm[handler]({ autoReviewListId: 87 })
  await flushPromises()
  expect(localOpen).toHaveBeenCalledWith('/reviews/87')
  expect(wrapper.findComponent(drawer).vm).toBe(instance)
  expect(wrapper.emitted('completed')).toBeUndefined()
  wrapper.unmount()
})
