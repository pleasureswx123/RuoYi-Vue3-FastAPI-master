import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskPreviewThumbnail from '@/views/task/components/TaskPreviewThumbnail.vue'
import { getVersionDetail } from '@/api/shot-grid/versions'

vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn() }))
const thumbnail = { name: 'ReviewCandidateThumbnail', props: ['candidate', 'versionId'], template: '<span>{{ candidate.candidateId }}</span>' }
const render = props => mount(TaskPreviewThumbnail, { props: { taskId: 15, versionId: 1, canPreview: true, ...props }, global: { stubs: { ReviewCandidateThumbnail: thumbnail } } })
describe('本人任务预览', () => {
  beforeEach(() => getVersionDetail.mockReset())
  it('无版本或缺少权限不请求详情', () => {
    const first = render({ versionId: null })
    const second = render({ canPreview: false })
    expect(getVersionDetail).not.toHaveBeenCalled()
    expect(first.text()).toContain('尚未提交')
    expect(second.text()).toContain('无预览权限')
    first.unmount(); second.unmount()
  })
  it('使用服务端选中的候选，拒绝其他任务文件并支持重试', async () => {
    getVersionDetail.mockResolvedValueOnce({ data: { versionId: 1, taskId: 99, files: [] } })
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('预览失败')
    expect(wrapper.findComponent(thumbnail).exists()).toBe(false)
    getVersionDetail.mockResolvedValueOnce({ data: { versionId: 1, taskId: 15, selectedCandidateId: 3, candidates: [{ candidateId: 2 }, { candidateId: 3 }] } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(thumbnail).props('candidate').candidateId).toBe(3)
    wrapper.unmount()
  })
  it('切换任务后取消旧读取，忽略迟到结果', async () => {
    let resolveOld
    getVersionDetail.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = render()
    const signal = getVersionDetail.mock.calls[0][1].signal
    getVersionDetail.mockResolvedValueOnce({ data: { versionId: 2, taskId: 16, candidates: [{ candidateId: 4 }] } })
    await wrapper.setProps({ versionId: 2, taskId: 16 })
    await flushPromises()
    resolveOld({ data: { versionId: 1, taskId: 15, candidates: [{ candidateId: 2 }] } })
    await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(wrapper.findComponent(thumbnail).props('candidate').candidateId).toBe(4)
    wrapper.unmount()
  })
})
