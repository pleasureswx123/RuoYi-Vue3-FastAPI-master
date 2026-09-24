import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getReviewActions, getTaskIssues } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import VersionReviewSummary from '@/components/version/VersionReviewSummary.vue'

const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/shot-grid/reviews', () => ({ getReviewActions: vi.fn(), getTaskIssues: vi.fn() }))
const version = { versionId: 29, taskId: 69, versionStatus: 'revision', autoReviewList: { reviewListId: 87, reviewListName: '镜头制作 V001 审核单' } }
function render() {
  return mount(VersionReviewSummary, { props: { version }, global: { stubs: {
    ElTag: { template: '<span><slot /></span>' },
    ElButton: { template: '<button><slot /></button>' }
  } } })
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  useSessionStore().permissions = ['shotgrid:reviewList:query', 'shotgrid:note:list']
  getReviewActions.mockResolvedValue({ rows: [{ actionType: 'reject', reviewerName: '审核人甲', reason: '调整光线' }] })
  getTaskIssues.mockResolvedValue({ data: [{ originVersionId: 29 }, { originVersionId: 30 }] })
})
describe('版本审核摘要', () => {
  it('仅统计本版正式意见并使用真实关联审核单导航', async () => {
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('1 条修改意见')
    expect(wrapper.text()).toContain('调整光线')
    await wrapper.find('button').trigger('click')
    expect(push).toHaveBeenCalledWith('/reviews/87')
    wrapper.unmount()
  })
  it('无意见权限不查询，不伪造零条，失败可以重试', async () => {
    useSessionStore().permissions = []
    getReviewActions.mockRejectedValue(new Error('失败'))
    const wrapper = render()
    await flushPromises()
    expect(getTaskIssues).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('0 条修改意见')
    expect(wrapper.text()).not.toContain('查看审核详情')
    expect(wrapper.text()).toContain('加载失败')
    wrapper.unmount()
  })
  it('版本切换隔离迟到的旧审核记录', async () => {
    let resolveOld
    getReviewActions.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    const wrapper = render()
    await wrapper.setProps({ version: { ...version, versionId: 30, versionStatus: 'pending_review' } })
    await flushPromises()
    resolveOld({ rows: [{ actionType: 'reject', reason: '过期结果' }] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('过期结果')
    expect(wrapper.text()).toContain('等待审核人确认')
    wrapper.unmount()
  })
})
