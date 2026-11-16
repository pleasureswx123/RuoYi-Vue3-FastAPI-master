import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElForm, ElInput } from 'element-plus'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import IssueCommentThread from '@/components/review/IssueCommentThread.vue'
import { getIssueComments, addIssueComment } from '@/api/shot-grid/reviews'
vi.mock('@/api/shot-grid/reviews', () => ({ getIssueComments: vi.fn(), addIssueComment: vi.fn() }))
const row = { commentId: 1, projectId: 8, noteId: 51, authorId: 7, authorName: '制作人', content: '调整完成', createTime: '2026-10-30T10:00:00' }
const button = (wrapper, label) => wrapper.findAllComponents(ElButton).find(item => item.text() === label)
async function setup(props = {}) {
  const wrapper = mount(IssueCommentThread, { props: { projectId: 8, versionId: 2, issueId: 51, canComment: true, ...props } })
  await button(wrapper, '查看 / 添加评论').trigger('click'); await flushPromises()
  return wrapper
}
describe('反馈评论', () => {
  beforeEach(() => {
    getIssueComments.mockResolvedValue({ data: { rows: [row], hasNext: false } })
    addIssueComment.mockResolvedValue({ data: { ...row, commentId: 2, content: '新的评论' } })
  })
  it('显示持久化记录，空白校验失败，正确提交后清空表单并显示记录', async () => {
    const wrapper = await setup()
    try {
      expect(wrapper.text()).toContain('调整完成')
      await button(wrapper, '发送评论').trigger('click'); await flushPromises()
      expect(addIssueComment).not.toHaveBeenCalled()
      await wrapper.findComponent(ElInput).setValue('  新的评论  ')
      await button(wrapper, '发送评论').trigger('click'); await flushPromises()
      expect(addIssueComment).toHaveBeenCalledWith(2, 51, expect.objectContaining({ content: '新的评论', requestId: expect.any(String) }), expect.anything())
      expect(wrapper.findComponent(ElForm).props('model').content).toBe('')
      expect(wrapper.text()).toContain('新的评论')
    } finally { wrapper.unmount() }
  })
  it('失败保留草稿，同内容重试保留幂等键，发送中阻止重复提交', async () => {
    const wrapper = await setup()
    try {
      addIssueComment.mockRejectedValueOnce(new Error('网络异常'))
      await wrapper.findComponent(ElInput).setValue('重试评论')
      await button(wrapper, '发送评论').trigger('click'); await flushPromises()
      expect(wrapper.findComponent(ElInput).props('modelValue')).toBe('重试评论')
      const key = addIssueComment.mock.calls[0][2].requestId
      let finish
      addIssueComment.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      await button(wrapper, '发送评论').trigger('click'); await flushPromises()
      expect(button(wrapper, '发送评论').props('disabled')).toBe(true)
      expect(addIssueComment.mock.calls[1][2].requestId).toBe(key)
      finish({ data: { ...row, commentId: 3 } }); await flushPromises()
      expect(wrapper.vm.$.exposed.dirty.value).toBe(false)
    } finally { wrapper.unmount() }
  })
  it('权限关闭后只读，拒绝跨反馈响应，切换上下文隔离旧提交', async () => {
    const wrapper = await setup()
    let finish
    addIssueComment.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.findComponent(ElInput).setValue('旧反馈的内容')
    await button(wrapper, '发送评论').trigger('click'); await flushPromises()
    const signal = addIssueComment.mock.calls[0][3].signal
    getIssueComments.mockResolvedValueOnce({ data: { rows: [{ ...row, noteId: 999 }], hasNext: false } })
    await wrapper.setProps({ issueId: 52, canComment: false }); await flushPromises()
    expect(signal.aborted).toBe(true)
    finish({ data: row }); await flushPromises()
    expect(wrapper.text()).toContain('评论归属不匹配')
    expect(wrapper.text()).not.toContain('调整完成')
    expect(wrapper.findComponent(ElForm).exists()).toBe(false)
    wrapper.unmount()
  })
  it('游标加载更早评论保留已有记录', async () => {
    getIssueComments.mockResolvedValueOnce({ data: { rows: [{ ...row, commentId: 3 }], hasNext: true, nextCursor: 3 } })
    const wrapper = await setup()
    await button(wrapper, '更早评论').trigger('click'); await flushPromises()
    expect(getIssueComments).toHaveBeenLastCalledWith(2, 51, { pageSize: 20, beforeId: 3 }, expect.anything())
    expect(wrapper.findAll('.comment-row')).toHaveLength(2)
    wrapper.unmount()
  })
})
