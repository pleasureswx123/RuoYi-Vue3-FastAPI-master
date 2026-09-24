import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElMessage } from 'element-plus'
import { describe, it, expect, vi } from 'vitest'
import BatchOverallFeedbackDialog from '@/components/version/BatchOverallFeedbackDialog.vue'
import { rejectBatchWithOverallFeedback } from '@/api/shot-grid/reviews'
vi.mock('@/api/shot-grid/reviews', () => ({ rejectBatchWithOverallFeedback: vi.fn() }))

const shots = [{ shotCode: 'EP001-001-0080', latestVersion: { versionId: 31, versionNumber: 'V001' } }, { shotCode: 'EP001-001-0100', latestVersion: { versionId: 32, versionNumber: 'V002' } }]
async function open() {
  const wrapper = mount(BatchOverallFeedbackDialog, { global: { stubs: { teleport: true } } })
  wrapper.vm.open(8, shots)
  await flushPromises()
  return wrapper
}
function submit(wrapper) {
  return wrapper.findAllComponents(ElButton).find(button => button.text() === '发送意见并退回修改')
}
describe('批量整体反馈并退回', () => {
  it('校验空意见、固定版本快照、发送后关闭并刷新', async () => {
    rejectBatchWithOverallFeedback.mockResolvedValue({ data: [] })
    const wrapper = await open()
    expect(wrapper.text()).toContain('任务将全部变为修改中')
    await submit(wrapper).trigger('click')
    await flushPromises()
    expect(rejectBatchWithOverallFeedback).not.toHaveBeenCalled()
    await wrapper.get('textarea').setValue('统一调整整体色调')
    await submit(wrapper).trigger('click')
    await flushPromises()
    expect(rejectBatchWithOverallFeedback).toHaveBeenCalledWith(8, { versionIds: [31, 32], content: '统一调整整体色调' })
    expect(wrapper.emitted('saved')).toEqual([[{ projectId: 8 }]])
    wrapper.unmount()
  })
  it('失败保留输入且不通知成功，提交期间阻止重复请求', async () => {
    let fail
    rejectBatchWithOverallFeedback.mockImplementation(() => new Promise((resolve, reject) => { fail = reject }))
    const message = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
    const wrapper = await open()
    await wrapper.get('textarea').setValue('统一调整')
    await submit(wrapper).trigger('click')
    await flushPromises()
    expect(submit(wrapper).props('loading')).toBe(true)
    fail({ message: '有上轮问题待复核' })
    await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('统一调整')
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(message).toHaveBeenCalled()
    wrapper.unmount()
    message.mockRestore()
  })
})
