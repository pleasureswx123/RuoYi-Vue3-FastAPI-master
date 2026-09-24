import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { showWorkflowSuccess } from '@/utils/workflowSuccess'

describe('业务操作成功提示', () => {
  beforeEach(() => vi.restoreAllMocks())

  it.each([
    ['submitted', '版本提交成功', '接下来由审核人'],
    ['appended', '候选追加成功', '当前审核轮次'],
    ['rejected', '已退回修改', '当前修改负责人'],
    ['approvedPublishing', '审核通过', '发布结果请查看交付状态'],
    ['deferred', '已暂缓本轮审核', '尚未通过或退回'],
    ['issueAppended', '修改意见已发送', '补充问题已加入']
  ])('%s 明确结果与下一步', async (kind, title, nextStep) => {
    const alert = vi.spyOn(ElMessageBox, 'alert').mockResolvedValue('confirm')
    await showWorkflowSuccess(kind)
    expect(alert).toHaveBeenCalledWith(expect.stringContaining(nextStep), title,
      expect.objectContaining({ type: 'success', confirmButtonText: '知道了', closeOnClickModal: false }))
  })

  it('关闭结果提示不变成业务失败', async () => {
    vi.spyOn(ElMessageBox, 'alert').mockRejectedValue('close')
    await expect(showWorkflowSuccess('submitted')).resolves.toBe(false)
  })
})
