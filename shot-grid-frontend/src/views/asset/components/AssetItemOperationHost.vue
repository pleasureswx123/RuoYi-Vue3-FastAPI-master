<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { useSessionStore } from '@/store/modules/session'
import AssetAssignDialog from './AssetAssignDialog.vue'
import AssetItemFormDialog from './AssetItemFormDialog.vue'
import AssetItemDeleteDialog from './AssetItemDeleteDialog.vue'
import { canAssetItemAction } from '../assetItemActions'
import { memberUserName } from '../assetPresentation'
import { useAssetItemStart } from '../useAssetItemStart'
import TaskStartDialog from '@/views/task/components/TaskStartDialog.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  contextKey: { type: String, required: true },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed', 'busy-change'])
const session = useSessionStore()
const asset = ref(null)
const context = ref(null)
const loading = ref(false)
let generation = 0
let controller
let disposed = false
const hasPermission = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const { startDialog, closeStartDialog, finishStartDialog, failStartDialog, startingOperation, confirmStartItem, invalidateStart } = useAssetItemStart({
  getAsset: () => asset.value, getContextKey: () => props.contextKey, isLoading: () => loading.value,
  hasPermission,
  assigneeName: task => memberUserName(props.members.find(member => Number(member.userId) === Number(task.assigneeUserId)) || { userId: task.assigneeUserId, nickName: task.assigneeName }),
  refresh: refreshAfterConflict,
  onStarted: operation => emit('changed', operation)
})
const busy = computed(() => loading.value || Boolean(context.value) || Boolean(startingOperation.value))
watch(busy, value => emit('busy-change', value), { immediate: true })

function reset() {
  generation += 1
  controller?.abort()
  invalidateStart()
  context.value = null
  asset.value = null
  loading.value = false
}
watch(() => props.contextKey, reset)
onBeforeUnmount(() => { disposed = true; reset() })

async function run(action, parent, row) {
  if (busy.value || disposed || Number(parent?.projectId) !== props.projectId || !hasPermission('shotgrid:asset:query') ||
    !canAssetItemAction(parent, row, action, hasPermission)) return
  const operationGeneration = ++generation
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  try {
    // 点击后重读完整详情，使用当前分项动作和锁版本，不能直接提交树表缓存。
    const response = await getAssetDetail(props.projectId, parent.assetId, { signal })
    if (disposed || signal.aborted || generation !== operationGeneration) return
    const currentAsset = response.data
    const item = currentAsset?.items?.find(candidate => Number(candidate.assetItemId) === Number(row.assetItemId))
    if (Number(currentAsset?.projectId) !== props.projectId || Number(currentAsset?.assetId) !== Number(parent.assetId) ||
      !canAssetItemAction(currentAsset, item, action, hasPermission)) {
      ElMessage.warning('分项状态或权限已变化，请核对刷新后的操作。')
      emit('changed', { projectId: props.projectId, assetId: parent.assetId })
      return
    }
    asset.value = currentAsset
    loading.value = false
    if (action === 'task.start') await confirmStartItem(item)
    else context.value = Object.freeze({
      action, projectId: props.projectId, assetId: Number(parent.assetId), assetItemId: Number(item.assetItemId), operationGeneration,
      asset: Object.freeze({ ...currentAsset }), item: Object.freeze({ ...item, task: item.task ? Object.freeze({ ...item.task }) : null })
    })
  } catch (error) {
    if (!disposed && !signal.aborted && generation === operationGeneration) ElMessage.error(error?.message || '分项操作加载失败，请重试')
  } finally {
    if (generation === operationGeneration) loading.value = false
  }
}

function completed(_result, operation) {
  if (disposed || !context.value || context.value.operationGeneration !== operation?.operationGeneration ||
    context.value.projectId !== Number(operation.projectId) || context.value.assetId !== Number(operation.assetId) ||
    context.value.assetItemId !== Number(operation.assetItemId)) return
  const action = context.value.action
  context.value = null
  ElMessage.success(action === 'assetItem.delete' ? '制作分项已删除' : action === 'assetItem.edit' ? '制作分项已更新' : '分项任务分配已更新')
  emit('changed', operation)
}

function refreshAfterConflict() {
  const target = { projectId: props.projectId, assetId: asset.value?.assetId }
  reset()
  emit('changed', target)
}
defineExpose({ run })
</script>

<template>
  <TaskStartDialog v-if="startDialog" :context="startDialog" @close="closeStartDialog" @started="finishStartDialog" @failed="failStartDialog" />
  <AssetItemFormDialog v-if="context?.action === 'assetItem.edit'" :key="context.operationGeneration" :project-id="context.projectId" :operation-generation="context.operationGeneration" :asset="context.asset" :item="context.item" @close="context = null" @saved="completed" @refresh="refreshAfterConflict" />
  <AssetAssignDialog v-if="context?.action === 'task.assign'" :key="context.operationGeneration" :project-id="context.projectId" :operation-generation="context.operationGeneration" :asset="context.asset" :item="context.item" :members="members" @close="context = null" @assigned="completed" @refresh="refreshAfterConflict" />
  <AssetItemDeleteDialog v-if="context?.action === 'assetItem.delete'" :key="context.operationGeneration" :project-id="context.projectId" :operation-generation="context.operationGeneration" :asset="context.asset" :item="context.item" @close="context = null" @deleted="completed" @refresh="refreshAfterConflict" />
</template>
