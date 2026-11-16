import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElCheckbox, ElDialog, ElTable } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShotTaskFeedbackDialog from '@/components/version/ShotTaskFeedbackDialog.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { getVersionReviewContext, submitBatchFeedback, appendVersionIssue, uploadReviewReferenceFile } from '@/api/shot-grid/reviews'

vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
vi.mock('@/api/shot-grid/reviews', () => ({ getVersionReviewContext: vi.fn(), submitBatchFeedback: vi.fn(), appendVersionIssue: vi.fn(), uploadReviewReferenceFile: vi.fn() }))
const targets = [1, 2, 3].map(id => ({ taskId: id, shotId: id + 10, versionId: id + 20, label: `EP001 / 00${id} / 0001 · V001` }))
const task = id => ({ taskId: id, project: { projectId: 8 }, taskKind: 'shot_video', taskStatus: id === 2 ? 'revision' : 'pending_review', target: { shotId: id + 10 }, latestVersion: { versionId: id + 20 }, allowedActions: ['task.feedback'] })
const context = id => ({ currentVersion: { versionId: id, versionStatus: id === 22 ? 'rejected' : 'pending_review', lockVersion: 4 }, canAppendIssues: true, carriedIssues: [], currentVersionDrafts: [], currentVersionIssues: [] })
let wrapper
const button = label => wrapper.findAllComponents(ElButton).find(item => item.text() === label)
async function click(label) { await button(label).trigger('click'); await flushPromises() }
async function open(rows = targets.slice(0, 2), valid) {
  wrapper = mount(ShotTaskFeedbackDialog, { attachTo: document.body, global: { stubs: { teleport: true, ReviewReferenceFiles: true } } })
  wrapper.vm.open(8, rows, valid)
  await flushPromises()
}
const common = () => wrapper.get('textarea[placeholder^="例如"]')
const rows = () => wrapper.getComponent(ElTable).props('data')
beforeEach(() => {
  vi.clearAllMocks()
  getTaskDetail.mockImplementation(id => Promise.resolve({ data: task(id) }))
  getVersionReviewContext.mockImplementation(id => Promise.resolve({ data: context(id) }))
  submitBatchFeedback.mockReset().mockResolvedValue({ data: {} })
  appendVersionIssue.mockReset().mockResolvedValue({ data: {} })
  uploadReviewReferenceFile.mockReset().mockResolvedValue({ fileId: '11111111-1111-4111-8111-111111111111' })
})
afterEach(() => { wrapper?.unmount(); wrapper = null })
describe('镜头任务直接反馈', () => {
  it('已通过镜头可直接反馈，与待审核镜头混选按各自状态发送', async () => {
    getTaskDetail.mockImplementation(id => Promise.resolve({ data: { ...task(id), taskStatus: id === 2 ? 'completed' : 'pending_review' } }))
    getVersionReviewContext.mockImplementation(id => Promise.resolve({ data: { ...context(id), currentVersion: { ...context(id).currentVersion, versionStatus: id === 22 ? 'final' : 'pending_review' }, canAppendIssues: false } }))
    await open()
    await common().setValue('统一人物衣服')
    await click('确认发送反馈')
    expect(submitBatchFeedback).toHaveBeenCalledTimes(1)
    expect(appendVersionIssue).toHaveBeenCalledWith(22, { issueScope: 'version', content: '统一人物衣服', referenceFileIds: [], lockVersion: 4 })
    expect(rows().map(row => row.result)).toEqual(['已发送', '已发送'])
  })
  it('跨场次混选：共同意见加逐镜头补充，分别退回和追加；上传附件只执行一次', async () => {
    await open()
    expect(wrapper.text()).toContain('EP001 / 001 / 0001')
    expect(wrapper.text()).toContain('EP001 / 002 / 0001')
    await common().setValue('  统一灯光  ')
    await wrapper.findAll('textarea')[2].setValue('第二场人物偏暗')
    wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['ref'], '参考.pdf') })
    await click('确认发送反馈')
    expect(uploadReviewReferenceFile).toHaveBeenCalledTimes(1)
    expect(submitBatchFeedback).toHaveBeenCalledWith(8, { action: 'reject', content: '统一灯光', referenceFileIds: ['11111111-1111-4111-8111-111111111111'], items: [{ versionId: 21, lockVersion: 4, drafts: [], issueVerifications: [] }] })
    expect(appendVersionIssue).toHaveBeenCalledWith(22, { issueScope: 'version', content: '统一灯光\n\n第二场人物偏暗', referenceFileIds: ['11111111-1111-4111-8111-111111111111'], lockVersion: 4 })
    expect(rows().map(row => row.result)).toEqual(['已发送', '已发送'])
    await click('关闭并刷新')
    expect(wrapper.emitted('closed')[0][0]).toMatchObject({ projectId: 8, changed: true })
  })
  it('空白反馈校验失败，重置清空输入和错误，填写后可提交', async () => {
    await open([targets[0]])
    await click('确认发送反馈')
    expect(submitBatchFeedback).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(wrapper.text()).toContain('请填写共同反馈或这颗镜头的反馈'))
    await common().setValue('临时意见')
    await click('重置')
    expect(common().element.value).toBe('')
    await vi.waitFor(() => expect(wrapper.text()).not.toContain('请填写共同反馈或这颗镜头的反馈'))
    await common().setValue('服装保持一致')
    await click('确认发送反馈')
    expect(submitBatchFeedback).toHaveBeenCalledTimes(1)
  })
  it('历史问题必须逐条确认，原有草稿必须确认后才随反馈发布', async () => {
    getVersionReviewContext.mockResolvedValue({ data: { ...context(21), carriedIssues: [{ issueId: 80, content: '人物太暗', currentVersionResponse: { responseText: '已调整曝光' } }], currentVersionDrafts: [{ draftId: 90, lockVersion: 2, content: '草稿意见' }] } })
    await open([targets[0]])
    expect(wrapper.text()).toContain('已调整曝光')
    await common().setValue('其他场次也需统一')
    await click('确认发送反馈')
    expect(submitBatchFeedback).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(wrapper.text()).toContain('请选择复核结论'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('请确认已有草稿'))
    await wrapper.get('input[value="still_present"]').setValue(true)
    await click('确认发送反馈')
    await vi.waitFor(() => expect(wrapper.text()).toContain('请填写修改原因'))
    await wrapper.findAll('textarea')[2].setValue('脸部仍然太暗')
    await wrapper.getComponent(ElCheckbox).setValue(true)
    await click('确认发送反馈')
    expect(submitBatchFeedback.mock.calls[0][1].items[0]).toEqual({ versionId: 21, lockVersion: 4, drafts: [{ draftId: 90, lockVersion: 2 }], issueVerifications: [{ issueId: 80, result: 'still_present', comment: '脸部仍然太暗' }] })
  })
  it.each(['project', 'shot', 'version', 'permission', 'completed'])('重新核对 %s 不匹配时禁止发送', async boundary => {
    const value = task(1)
    if (boundary === 'project') value.project.projectId = 9
    if (boundary === 'shot') value.target.shotId = 99
    if (boundary === 'version') value.latestVersion.versionId = 99
    if (boundary === 'permission') value.allowedActions = []
    if (boundary === 'completed') value.taskStatus = 'completed'
    getTaskDetail.mockResolvedValue({ data: value })
    await open([targets[0]])
    expect(wrapper.text()).toContain('归属或版本已变化')
    expect(button('确认发送反馈').props('disabled')).toBe(true)
    expect(submitBatchFeedback).not.toHaveBeenCalled()
  })
  it('发送中禁用重复提交和关闭；中途失败停止，保留前项成功并显示未知结果', async () => {
    let resolve
    submitBatchFeedback.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    appendVersionIssue.mockRejectedValueOnce(new Error('网络中断'))
    await open(targets)
    await common().setValue('调整动作衔接')
    await click('确认发送反馈')
    expect(button('确认发送反馈').props('loading')).toBe(true)
    expect(button('取消').props('disabled')).toBe(true)
    wrapper.getComponent(ElDialog).props('beforeClose')()
    expect(wrapper.emitted('closed')).toBeUndefined()
    await click('确认发送反馈')
    expect(submitBatchFeedback).toHaveBeenCalledTimes(1)
    resolve({ data: {} }); await flushPromises()
    expect(rows().map(row => row.result)).toEqual(['已发送', '结果未知，请刷新核对，勿重复发送', '未执行'])
    expect(button('确认发送反馈')).toBeUndefined()
    expect(wrapper.text()).toContain('已发送 1 颗，未完成 2 颗')
    await click('关闭并刷新')
    expect(wrapper.emitted('closed')[0][0]).toMatchObject({ completedShotIds: [11], changed: true, uncertain: true })
  })
  it('项目切换与迟到请求均不能提交到新上下文', async () => {
    let valid = true
    await open([targets[0]], () => valid)
    await common().setValue('不要写到其他项目')
    valid = false
    await click('确认发送反馈')
    expect(wrapper.text()).toContain('当前项目或镜头已变化')
    expect(submitBatchFeedback).not.toHaveBeenCalled()
  })
  it('附件上传失败保留正文并允许重试，上传完成前不发送反馈', async () => {
    uploadReviewReferenceFile.mockRejectedValueOnce(new Error('附件上传失败'))
    await open([targets[0]])
    await common().setValue('参照附件修改')
    wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['ref'], '参考.pdf') })
    await click('确认发送反馈')
    expect(submitBatchFeedback).not.toHaveBeenCalled()
    expect(common().element.value).toBe('参照附件修改')
    expect(wrapper.text()).toContain('附件上传失败')
    await click('确认发送反馈')
    expect(submitBatchFeedback).toHaveBeenCalledTimes(1)
  })
  it('关闭时取消目标读取，迟到响应不会重新打开表单', async () => {
    let resolve
    getTaskDetail.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    await open([targets[0]])
    const signal = getTaskDetail.mock.calls[0][1].signal
    await click('取消')
    expect(signal.aborted).toBe(true)
    resolve({ data: task(1) }); await flushPromises()
    expect(wrapper.getComponent(ElDialog).props('modelValue')).toBe(false)
    expect(submitBatchFeedback).not.toHaveBeenCalled()
  })
})
