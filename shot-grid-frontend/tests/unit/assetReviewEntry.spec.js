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
it('单分项直接打开真实自动审核单，不把版本ID作为审核单ID', async () => { await open(); expect(openReview).toHaveBeenCalledWith('/reviews/99') })
it('多个待审核分项先选择，不自动打开审核单', async () => { getAssetDetail.mockResolvedValue({ data: { ...asset, items: [item, { ...item, assetItemId: 12 }] } }); await open(); expect(openReview).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('选择分项审核') })
it('版本与任务不匹配时阻止跳转', async () => { getVersionDetail.mockResolvedValue({ data: { taskId: 21, autoReviewList: { reviewListId: 99 } } }); await open(); expect(openReview).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('审核版本与任务不匹配') })
it('没有审核单查看权限时不加载业务数据', async () => { useSessionStore().permissions = ['shotgrid:asset:query']; await open(); expect(getAssetDetail).not.toHaveBeenCalled(); expect(openReview).not.toHaveBeenCalled() })
