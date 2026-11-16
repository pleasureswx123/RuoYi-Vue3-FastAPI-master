import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShotFeedbackPanel from '@/views/shot/components/ShotFeedbackPanel.vue'
import { getTaskIssues } from '@/api/shot-grid/reviews'

vi.mock('@/api/shot-grid/reviews', () => ({ getTaskIssues: vi.fn() }))
vi.mock('@/composables/useVersionRealtime', () => ({ useVersionRealtime: vi.fn() }))
const issue = { issueId: 51, projectId: 8, originVersionId: 2, content: '调整光照', reviewerName: '审核人', createTime: '2026-10-30T10:00:00', status: 'open' }
const setup = () => mount(ShotFeedbackPanel, {
  props: { projectId: 8, taskId: 3, versionId: 2, canRead: true, canComment: true },
  global: { stubs: { IssueCommentThread: { props: ['projectId', 'versionId', 'issueId', 'canComment'], template: '<div class="comment-thread" />' }, ReviewReferenceFiles: true } }
})

describe('镜头侧栏的版本反馈', () => {
  beforeEach(() => { getTaskIssues.mockReset(); getTaskIssues.mockResolvedValue({ data: [issue, { ...issue, issueId: 52, originVersionId: 1, content: '上一版反馈' }] }) })
  it('只展示所选版本反馈，并将反馈归属和评论权限传入评论区', async () => {
    const wrapper = setup(); await flushPromises()
    expect(wrapper.text()).toContain('调整光照')
    expect(wrapper.text()).not.toContain('上一版反馈')
    const thread = wrapper.findComponent('.comment-thread')
    expect(thread.props()).toMatchObject({ projectId: 8, versionId: 2, issueId: 51, canComment: true })
    await wrapper.setProps({ canComment: false })
    expect(thread.props('canComment')).toBe(false)
    await wrapper.setProps({ versionId: 1 }); await flushPromises()
    expect(wrapper.text()).toContain('上一版反馈')
    expect(wrapper.text()).not.toContain('调整光照')
    wrapper.unmount()
  })
  it('拒绝越界数据，并在失去读取权限时移除反馈', async () => {
    getTaskIssues.mockResolvedValueOnce({ data: [{ ...issue, projectId: 99 }] })
    const wrapper = setup(); await flushPromises()
    expect(wrapper.text()).toContain('反馈归属不匹配')
    expect(wrapper.find('.comment-thread').exists()).toBe(false)
    await wrapper.setProps({ canRead: false }); await flushPromises()
    expect(wrapper.text()).toContain('当前账号没有反馈查看权限')
    expect(getTaskIssues).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('跨版反馈展示制作人处理说明与审核确认，评论始终绑定原问题版本', async () => {
    const response = { responseId: 1, versionId: 2, versionNumber: 'V002', responseText: '已提亮面部', createTime: '2026-10-30T11:00:00' }
    const carried = { ...issue, originVersionId: 1, originVersionNumber: 'V001', pendingVersionId: 1, responses: [response], verifications: [] }
    getTaskIssues.mockResolvedValue({ data: [carried] })
    const wrapper = setup(); await flushPromises()
    expect(wrapper.text()).toContain('已提交修改，待确认')
    expect(wrapper.text()).toContain('已提亮面部')
    expect(wrapper.findComponent('.comment-thread').props('versionId')).toBe(1)
    getTaskIssues.mockResolvedValue({ data: [{ ...carried, pendingVersionId: 2, verifications: [{ verificationId: 2, checkedVersionId: 2, checkedVersionNumber: 'V002', result: 'still_present', comment: '眼部仍偏暗', createTime: '2026-10-30T12:00:00' }] }] })
    await wrapper.setProps({ versionId: 1 }); await flushPromises()
    expect(wrapper.text()).toContain('待修改')
    expect(wrapper.text()).toContain('眼部仍偏暗')
    getTaskIssues.mockResolvedValue({ data: [{ ...carried, status: 'resolved', resolvedInVersionId: 2 }] })
    await wrapper.setProps({ versionId: 2 }); await flushPromises()
    expect(wrapper.text()).toContain('已解决')
    wrapper.unmount()
  })
  it('切换版本后忽略之前的迟到响应', async () => {
    let finish
    getTaskIssues.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = setup()
    const signal = getTaskIssues.mock.calls[0][2].signal
    await wrapper.setProps({ versionId: 1 }); await flushPromises()
    expect(signal.aborted).toBe(true)
    finish({ data: [issue] }); await flushPromises()
    expect(wrapper.text()).toContain('上一版反馈')
    expect(wrapper.text()).not.toContain('调整光照')
    wrapper.unmount()
  })
})
