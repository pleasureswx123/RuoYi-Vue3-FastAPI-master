import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getVersionDetail } from '@/api/shot-grid/versions'
import AssetReviewEntry from '@/views/asset/components/AssetReviewEntry.vue'
const openReview = vi.hoisted(() => vi.fn())
vi.mock('@/api/shot-grid/assets', () => ({ getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn() }))
vi.mock('@/components/RelatedDetailDrawer.vue', () => ({ default: { setup(_p, { expose }) { expose({ open: openReview }) }, template: '<div />' } }))
const asset = { projectId: 6, assetId: 10 }
const item = { assetItemId: 11, productionItem: '概念设计', allowedActions: ['task.review'], task: { taskId: 20, taskStatus: 'pending_review' }, latestVersion: { versionId: 30 } }
let wrapper
beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()); useSessionStore().permissions = ['shotgrid:asset:query', 'shotgrid:version:query', 'shotgrid:reviewList:query', 'shotgrid:version:review']; getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item] } }); getVersionDetail.mockResolvedValue({ data: { taskId: 20, autoReviewList: { reviewListId: 99 } } }) })
afterEach(() => wrapper?.unmount())
async function open() { wrapper = mount(AssetReviewEntry, { props: { projectId: 6 }, global: { stubs: { teleport: true } } }); await wrapper.vm.open(asset); await flushPromises() }

it('指定重审分项加载期间不创建选择抽屉，只打开一次审核详情', async () => {
  let resolveAsset, resolveVersion
  getAssetDetail.mockImplementation(() => new Promise(resolve => { resolveAsset = resolve }))
  getVersionDetail.mockImplementation(() => new Promise(resolve => { resolveVersion = resolve }))
  wrapper = mount(AssetReviewEntry, { props: { projectId: 6 }, global: { stubs: { teleport: true } } })
  const pending = wrapper.vm.open(asset, 11, 'reopen')
  await flushPromises()
  expect(wrapper.findComponent({ name: 'ProjectDrawer' }).exists()).toBe(false)
  resolveAsset({ data: { ...asset, items: [{ ...item, allowedActions: ['task.reopenReview'], task: { taskId: 20, taskStatus: 'completed' } }] } })
  await flushPromises()
  expect(wrapper.findComponent({ name: 'ProjectDrawer' }).exists()).toBe(false)
  await wrapper.vm.open(asset, 11, 'reopen')
  expect(getAssetDetail).toHaveBeenCalledTimes(1)
  resolveVersion({ data: { taskId: 20, autoReviewList: { reviewListId: 99 } } })
  await pending
  await flushPromises()
  expect(openReview).toHaveBeenCalledTimes(1)
  expect(wrapper.findComponent({ name: 'ProjectDrawer' }).exists()).toBe(false)
})
it('单目标加载失败仍展示可关闭的错误提示', async () => {
  getAssetDetail.mockRejectedValue(new Error('分项加载失败'))
  await open()
  expect(wrapper.text()).toContain('分项加载失败')
  expect(openReview).not.toHaveBeenCalled()
})
