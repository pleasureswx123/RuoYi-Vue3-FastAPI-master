import { flushPromises, mount } from '@vue/test-utils'
import { ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElTag } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ReviewProductionTarget from '@/views/review/components/ReviewProductionTarget.vue'

vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
const target = { targetType: 'asset_item', requirements: '任务要求', asset: { assetName: '舱室', assetDescription: '冷色空间', productionItem: '概念设计' } }
const data = { taskId: 2, project: { projectId: 1 }, projectReferenceDescription: '项目资料内容', projectReferenceFiles: [{ fileId: 'p', originalName: '项目图.png' }], referenceDescription: '制作参考内容', referenceFiles: [{ fileId: 't', originalName: '参考图.png' }] }
function setup(props = {}) {
  return mount(ReviewProductionTarget, { props: { target, taskId: 2, projectId: 1, canReadReferences: true, ...props }, global: {
    components: { ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElTag },
    stubs: { ReviewReferenceFiles: { props: ['files'], template: '<div>{{ files.map(file => file.originalName).join() }}</div>' } }
  } })
}
beforeEach(() => { vi.clearAllMocks(); getTaskDetail.mockResolvedValue({ data }) })
describe('审核依据资料表格', () => {
  it('展示三组信息与对应附件，沿用任务详情鉴权接口', async () => {
    const wrapper = setup()
    await flushPromises()
    expect(wrapper.findAllComponents(ElDescriptions)).toHaveLength(3)
    for (const text of ['项目资料内容', '项目图.png', '冷色空间', '任务要求', '制作参考内容', '参考图.png']) expect(wrapper.text()).toContain(text)
    expect(getTaskDetail).toHaveBeenCalledWith(2, { signal: expect.any(AbortSignal) })
    wrapper.unmount()
  })
  it('无权限不请求；加载失败显示重试而非空资料', async () => {
    const wrapper = setup({ canReadReferences: false })
    expect(getTaskDetail).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无权限')
    getTaskDetail.mockRejectedValueOnce({ httpStatus: 500 })
    await wrapper.setProps({ canReadReferences: true })
    await flushPromises()
    expect(wrapper.text()).toContain('资料加载失败')
    expect(wrapper.text()).not.toContain('暂无参考附件')
    await wrapper.getComponent(ElButton).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('项目资料内容')
    wrapper.unmount()
  })
  it('切换任务后丢弃旧请求，拒绝错误项目的资料', async () => {
    let finish
    getTaskDetail.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const wrapper = setup()
    getTaskDetail.mockResolvedValueOnce({ data: { ...data, taskId: 3, project: { projectId: 99 } } })
    await wrapper.setProps({ taskId: 3 })
    await flushPromises()
    finish({ data })
    await flushPromises()
    expect(wrapper.text()).toContain('资料加载失败')
    expect(wrapper.text()).not.toContain('项目资料内容')
    wrapper.unmount()
  })
})
