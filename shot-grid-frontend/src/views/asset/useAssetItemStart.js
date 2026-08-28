import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useTaskStartDialog } from '@/views/task/useTaskStartDialog'
import { canAssetItemAction } from './assetItemActions'

// 列表和详情共用同一份确认、三份锁版本及迟到响应门禁。
export function useAssetItemStart({ getAsset, getContextKey, isLoading, hasPermission, assigneeName, refresh, onStarted }) {
  const dialog = useTaskStartDialog()
  const startingOperation = ref(null)
  const startDisabled = computed(() => isLoading() || Boolean(startingOperation.value))
  let generation = 0
  let disposed = false

  function invalidateStart() { generation += 1; dialog.closeStartDialog() }
  watch(getContextKey, invalidateStart)
  onBeforeUnmount(() => { disposed = true; invalidateStart() })

  function itemCanStart(item) {
    const asset = getAsset()
    return canAssetItemAction(asset, item, 'task.start', hasPermission) &&
      Number.isSafeInteger(Number(item.task?.taskId)) && Number(item.task.taskId) > 0 &&
      [item.task?.lockVersion, asset.lockVersion, item.lockVersion].every(value => Number.isSafeInteger(Number(value)) && Number(value) >= 0)
  }

  function isCurrent(operation) {
    const asset = getAsset()
    return !disposed && startingOperation.value === operation && generation === operation.generation &&
      Number(asset?.projectId) === operation.projectId && Number(asset?.assetId) === operation.assetId
  }

  async function confirmStartItem(item) {
    if (!itemCanStart(item) || startDisabled.value) return
    const asset = getAsset()
    const operation = Object.freeze({
      projectId: Number(asset.projectId), assetId: Number(asset.assetId), assetItemId: Number(item.assetItemId),
      taskId: Number(item.task.taskId), lockVersion: Number(item.task.lockVersion),
      assetLockVersion: Number(asset.lockVersion), assetItemLockVersion: Number(item.lockVersion), generation
    })
    startingOperation.value = operation
    try {
      const response = await dialog.requestStartDialog({
        name: `${asset.assetName} · ${item.productionItem}`, assigneeName: assigneeName(item.task),
        asset: { ...asset }, item: { ...item }, task: { ...item.task }, taskId: operation.taskId,
        command: {
          lockVersion: operation.lockVersion, assetLockVersion: operation.assetLockVersion,
          assetItemLockVersion: operation.assetItemLockVersion, startConfirmed: true
        },
        validateContext: () => {
          const current = getAsset()?.items?.find(candidate => Number(candidate.assetItemId) === operation.assetItemId)
          return isCurrent(operation) && itemCanStart(current) && Number(current.task.taskId) === operation.taskId &&
            Number(current.task.lockVersion) === operation.lockVersion && Number(getAsset().lockVersion) === operation.assetLockVersion &&
            Number(current.lockVersion) === operation.assetItemLockVersion
        }
      })
      if (!isCurrent(operation)) {
        if (!disposed) ElMessage.success('原制作分项已确认开工，请返回原资产查看。')
        return
      }
      ElMessage.success(response.data?.taskStatus === 'preparing' ? '已确认开工，正在准备制作目录' : '已确认开工，负责人可以开始制作')
      await onStarted(operation)
    } catch (error) {
      if (error === 'cancel' || error === 'close' || !isCurrent(operation)) return
      ElMessage.error(error?.message || '确认开工失败，请刷新后重试')
      if (Number(error?.httpStatus || error?.status) === 409) await refresh()
    } finally {
      if (startingOperation.value === operation) startingOperation.value = null
    }
  }

  return { ...dialog, startingOperation, startDisabled, itemCanStart, confirmStartItem, invalidateStart }
}
