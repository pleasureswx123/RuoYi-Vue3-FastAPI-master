import { ElMessageBox } from 'element-plus'

const messages = {
  submitted: ['版本提交成功', '作品已提交并进入待审核状态。接下来由审核人检查作品并反馈结果，你可以关闭此窗口，稍后查看审核进度。'],
  appended: ['候选追加成功', '新文件已加入当前审核轮次，审核人会结合本轮文件继续审核。你可以稍后查看审核进度。'],
  rejected: ['已退回修改', '修改意见已提交，任务已交给当前修改负责人。接下来由制作人按意见修改、逐条填写处理说明并提交新版本，再由审核人复核。'],
  approved: ['审核通过', '本轮审核已完成，所选文件已确认为最终版本，制作任务已完成。'],
  approvedPublishing: ['审核通过', '本轮审核已完成，所选文件已确认为最终版本，制作任务已完成。最终文件已进入发布流程，发布结果请查看交付状态。'],
  deferred: ['已暂缓本轮审核', '本次决定已保存，尚未通过或退回制作人。审核人可以稍后返回继续处理。'],
  issueAppended: ['修改意见已发送', '补充问题已加入当前任务，制作人可以查看并处理。接下来由当前修改负责人继续修改并提交新版本。']
}

export function showWorkflowSuccess(kind) {
  const [title, message] = messages[kind]
  // 结果提示不阻塞页面刷新；关闭提示不应被当成业务提交失败。
  return ElMessageBox.alert(message, title, {
    type: 'success',
    confirmButtonText: '知道了',
    closeOnClickModal: false,
    closeOnPressEscape: true,
    showClose: true
  }).then(action => action === 'confirm').catch(() => false)
}
