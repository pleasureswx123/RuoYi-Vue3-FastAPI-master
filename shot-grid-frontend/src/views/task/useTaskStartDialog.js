import { onBeforeUnmount, shallowRef } from 'vue'

// 保留调用方的目标/版本快照；关闭、换项目或卸载时结束旧确认。
export function useTaskStartDialog() {
  const startDialog = shallowRef(null)
  let pending
  function settle(error, result) {
    const current = pending
    pending = null
    startDialog.value = null
    if (error) current?.reject(error)
    else current?.resolve(result)
  }
  const closeStartDialog = () => settle('cancel')
  function requestStartDialog(context) {
    closeStartDialog()
    return new Promise((resolve, reject) => {
      pending = { resolve, reject }
      startDialog.value = context
    })
  }
  onBeforeUnmount(closeStartDialog)
  return {
    startDialog, requestStartDialog, closeStartDialog,
    finishStartDialog: result => settle(null, result),
    failStartDialog: error => settle(error)
  }
}
