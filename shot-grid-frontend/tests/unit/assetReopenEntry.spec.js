import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssetReviewEntry from '@/views/asset/components/AssetReviewEntry.vue'
import { useSessionStore } from '@/store/modules/session'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getVersionDetail } from '@/api/shot-grid/versions'
vi.mock('@/api/shot-grid/assets', () => ({ getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn() }))
const { openDrawer } = vi.hoisted(() => ({ openDrawer: vi.fn() }))
vi.mock('@/components/RelatedDetailDrawer.vue', () => ({ default: { template: '<div />', setup: (_, { expose }) => { expose({ open: openDrawer }); return {} } } }))
beforeEach(() => {
  setActivePinia(createPinia()); vi.clearAllMocks()
  useSessionStore().permissions = ['*:*:*']
  getAssetDetail.mockResolvedValue({ data: { projectId: 7, assetId: 8, items: [
    { assetItemId: 1, allowedActions: ['task.review'], task: { taskId: 11, taskStatus: 'pending_review' }, latestVersion: { versionId: 21 } },
    { assetItemId: 2, allowedActions: ['task.reopenReview'], task: { taskId: 12, taskStatus: 'completed' }, latestVersion: { versionId: 22 } }
  ] } })
  getVersionDetail.mockImplementation(id => Promise.resolve({ data: { taskId: id - 10, autoReviewList: { reviewListId: id + 10 } } }))
})
describe('资产审核入口按模式选择分项', () => {
  it.each([['review', 21, 31], ['reopen', 22, 32]])('%s 只打开对应状态的分项', async (mode, versionId, reviewId) => {
    const wrapper = mount(AssetReviewEntry, { props: { projectId: 7 }, global: { stubs: { ProjectDrawer: true } } })
    try {
      await wrapper.vm.open({ projectId: 7, assetId: 8 }, null, mode); await flushPromises()
      expect(getVersionDetail).toHaveBeenCalledTimes(1)
      expect(getVersionDetail).toHaveBeenCalledWith(versionId, expect.any(Object))
      expect(openDrawer).toHaveBeenCalledWith(`/reviews/${reviewId}`)
    } finally { wrapper.unmount() }
  })
})
