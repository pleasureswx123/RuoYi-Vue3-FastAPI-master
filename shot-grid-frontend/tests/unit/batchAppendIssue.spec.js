import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElForm } from 'element-plus'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import BatchAppendIssueDialog from '@/components/version/BatchAppendIssueDialog.vue'
import { appendVersionIssue, getVersionReviewContext, uploadReviewReferenceFile } from '@/api/shot-grid/reviews'
vi.mock('@/api/shot-grid/reviews', () => ({ uploadReviewReferenceFile: vi.fn(), appendVersionIssue: vi.fn(), getVersionReviewContext: vi.fn() }))

const targets = [31, 32, 33].map(versionId => ({ versionId, label: `镜头 ${versionId} · V001` }))
async function open(validateContext = () => true) {
  const wrapper = mount(BatchAppendIssueDialog, {
    props: { context: { projectId: 8, targets, validateContext } },
    global: { stubs: { teleport: true } }
  })
  await flushPromises()
  return wrapper
}
const button = (wrapper, text) => wrapper.findAllComponents(ElButton).find(item => item.text().startsWith(text))
async function send(wrapper) {
  await button(wrapper, '追加并发送').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  uploadReviewReferenceFile.mockReset().mockResolvedValue({ fileId: '11111111-1111-4111-8111-111111111111' })
  getVersionReviewContext.mockReset().mockImplementation(versionId => Promise.resolve({ data: {
    canAppendIssues: true, currentVersion: { versionId, versionStatus: 'rejected', lockVersion: versionId + 1 }
  } }))
  appendVersionIssue.mockReset().mockResolvedValue({ data: { issueId: 99 } })
})

describe('批量追加发送问题', () => {
  it('参考资料只上传一次，所有追加请求都携带同一组文件ID', async () => {
    const wrapper = await open()
    try {
      const input = wrapper.get('.issue-reference-compose input[type="file"]')
      Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['ref'], '参考.pdf')] })
      await input.trigger('change')
      await wrapper.get('textarea').setValue('参考附件调整')
      await send(wrapper)
      expect(uploadReviewReferenceFile).toHaveBeenCalledTimes(1)
      expect(appendVersionIssue).toHaveBeenCalledTimes(3)
      for (const [, payload] of appendVersionIssue.mock.calls) expect(payload.referenceFileIds).toEqual(['11111111-1111-4111-8111-111111111111'])
      expect(wrapper.getComponent(ReviewReferenceInput).props('disabled')).toBe(true)
    } finally { wrapper.unmount() }
  })
  it('上传失败不追加问题，附件保留可重试；重置会清空文件', async () => {
    uploadReviewReferenceFile.mockRejectedValueOnce(new Error('上传失败'))
    const wrapper = await open()
    try {
      wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['ref'], '参考.pdf') })
      await wrapper.get('textarea').setValue('参考附件调整')
      await send(wrapper)
      expect(appendVersionIssue).not.toHaveBeenCalled()
      expect(button(wrapper, '追加并发送').props('disabled')).toBe(false)
      expect(wrapper.getComponent(ReviewReferenceInput).props('files')).toHaveLength(1)
      await button(wrapper, '重置').trigger('click')
      expect(wrapper.getComponent(ReviewReferenceInput).props('files')).toEqual([])
    } finally { wrapper.unmount() }
  })
  it('上传期间任务上下文失效，不把资料追加到旧任务', async () => {
    let valid = true
    let finishUpload
    uploadReviewReferenceFile.mockImplementation(() => new Promise(resolve => { finishUpload = resolve }))
    const wrapper = await open(() => valid)
    try {
      wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['ref'], '参考.pdf') })
      await wrapper.get('textarea').setValue('参考附件调整')
      await send(wrapper)
      valid = false
      finishUpload({ fileId: '11111111-1111-4111-8111-111111111111' })
      await flushPromises()
      expect(appendVersionIssue).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('校验空白和超长问题，重置清空，按冻结锁号逐项发送共同整版问题', async () => {
    const wrapper = await open()
    try {
      await wrapper.get('textarea').setValue('   ')
      await send(wrapper)
      expect(appendVersionIssue).not.toHaveBeenCalled()
      await wrapper.get('textarea').setValue('问题'.repeat(5001))
      await send(wrapper)
      expect(appendVersionIssue).not.toHaveBeenCalled()
      await button(wrapper, '重置').trigger('click')
      await flushPromises()
      expect(wrapper.get('textarea').element.value).toBe('')
      await wrapper.get('textarea').setValue('  请统一修正光线方向  ')
      await send(wrapper)
      expect(appendVersionIssue.mock.calls).toEqual(targets.map(({ versionId }) => [versionId, {
        issueScope: 'version', content: '请统一修正光线方向', referenceFileIds: [], lockVersion: versionId + 1
      }]))
      expect(wrapper.text()).toContain('已发送 3 / 3')
      expect(button(wrapper, '追加并发送')).toBeUndefined()
      expect(wrapper.findComponent(ElForm).props('disabled')).toBe(true)
      await button(wrapper, '关闭并刷新').trigger('click')
      expect(wrapper.emitted('close')).toHaveLength(1)
    } finally { wrapper.unmount() }
  })

  it.each(['window', 'version', 'lock'])('核对 %s 失败时整批不发送', async reason => {
    getVersionReviewContext.mockResolvedValue({ data: {
      canAppendIssues: reason !== 'window', currentVersion: { versionId: reason === 'version' ? 99 : 31,
        versionStatus: 'rejected', lockVersion: reason === 'lock' ? null : 1 }
    } })
    const wrapper = await open()
    try {
      expect(wrapper.text()).toContain('已不能追加问题')
      expect(button(wrapper, '追加并发送')).toBeUndefined()
      expect(appendVersionIssue).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })

  it.each([409, 422, 403, 0])('错误 %s 保留成功结果并按规则停止，不自动换锁重试', async status => {
    appendVersionIssue.mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce({ httpStatus: status, message: '追加窗口已关闭' })
    const wrapper = await open()
    try {
      await wrapper.get('textarea').setValue('追加共同问题')
      await send(wrapper)
      expect(appendVersionIssue).toHaveBeenCalledTimes([409, 422].includes(status) ? 3 : 2)
      expect(wrapper.text()).toContain('已追加并发送')
      expect(wrapper.text()).toContain(status ? '追加窗口已关闭' : '发送结果未知')
      expect(getVersionReviewContext).toHaveBeenCalledTimes(3)
      expect(button(wrapper, '追加并发送')).toBeUndefined()
    } finally { wrapper.unmount() }
  })

  it('验证与发送期间防重复点击；项目变化后停止剩余发送', async () => {
    let resolveSend
    let valid = true
    appendVersionIssue.mockImplementation(() => new Promise(resolve => { resolveSend = resolve }))
    const wrapper = await open(() => valid)
    try {
      await wrapper.get('textarea').setValue('追加共同问题')
      await Promise.all([send(wrapper), send(wrapper)])
      expect(appendVersionIssue).toHaveBeenCalledTimes(1)
      expect(button(wrapper, '追加并发送').props('loading')).toBe(true)
      valid = false
      resolveSend({ data: {} })
      await flushPromises()
      expect(appendVersionIssue).toHaveBeenCalledTimes(1)
      expect(wrapper.text()).toContain('未执行，请刷新后重新选择')
    } finally { wrapper.unmount() }
  })

  it('详情核对途中卸载，不启动剩余读取或写入', async () => {
    let resolveRead
    getVersionReviewContext.mockImplementation(() => new Promise(resolve => { resolveRead = resolve }))
    const wrapper = await open()
    wrapper.unmount()
    resolveRead({ data: {} })
    await flushPromises()
    expect(getVersionReviewContext).toHaveBeenCalledTimes(1)
    expect(getVersionReviewContext.mock.calls[0][1].signal.aborted).toBe(true)
    expect(appendVersionIssue).not.toHaveBeenCalled()
  })

  it('发送途中卸载，迟到完成不继续发送或通知新页面', async () => {
    let resolveSend
    appendVersionIssue.mockImplementation(() => new Promise(resolve => { resolveSend = resolve }))
    const wrapper = await open()
    await wrapper.get('textarea').setValue('追加共同问题')
    await send(wrapper)
    wrapper.unmount()
    resolveSend({ data: {} })
    await flushPromises()
    expect(appendVersionIssue).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
