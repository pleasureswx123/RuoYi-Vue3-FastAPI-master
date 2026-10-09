<script setup>
import { createIdempotencyState } from '@/utils/idempotency'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getProjectDetail } from '@/api/shot-grid/projects'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { useSessionStore } from '@/store/modules/session'
import { canScheduleAssetItem } from '../assetItemActions'
import { memberUserName } from '../assetPresentation'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  contextKey: { type: String, required: true },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed', 'busy-change'])
const session = useSessionStore()
const task = ref(null)
const visible = ref(false)
const busy = ref(false)
const error = ref(null)
const draft = computed(() => task.value ? { expectedStartTime: task.value.currentStart, expectedEndTime: task.value.currentEnd } : null)
let generation = 0
let controller
let key = ''
let disposed = false
const permitted = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)

function reset() {
  generation += 1
  controller?.abort()
  visible.value = false
  task.value = null
  error.value = null
  busy.value = false
}
watch(() => props.contextKey, reset)
watch(busy, value => emit('busy-change', value))
onBeforeUnmount(() => { disposed = true; reset() })

async function open(parent, row) {
  if (busy.value || disposed || Number(parent?.projectId) !== props.projectId || !permitted('shotgrid:asset:query') || !permitted('shotgrid:task:schedule')) return
  reset()
  const current = generation
  controller = new AbortController()
  const signal = controller.signal
  busy.value = true
  try {
    // 点击时重读项目范围、分项与任务版本，排期不依赖开工权限。
    const [assetResponse, projectResponse] = await Promise.all([
      getAssetDetail(props.projectId, parent.assetId, { signal }), getProjectDetail(props.projectId, { signal })
    ])
    if (disposed || signal.aborted || current !== generation) return
    const asset = assetResponse.data
    const project = projectResponse.data
    const item = asset?.items?.find(value => Number(value.assetItemId) === Number(row.assetItemId))
    const manager = project?.myProjectRole === 'director' || permitted('shotgrid:project:all') || session.permissions.includes('*:*:*')
    if (Number(project?.projectId) !== props.projectId || Number(asset?.assetId) !== Number(parent.assetId) ||
      !canScheduleAssetItem(asset, item, manager && !['completed', 'archived'].includes(project?.projectStatus))) {
      ElMessage.warning('分项状态或排期权限已变化，请刷新后核对。')
      emit('changed', { projectId: props.projectId, assetId: parent.assetId })
      return
    }
    task.value = {
      ...item.task, projectId: props.projectId, assetId: asset.assetId, assetItemId: item.assetItemId,
      assignee: {
        userId: item.task.assigneeUserId,
        userName: memberUserName(props.members.find(member => Number(member.userId) === Number(item.task.assigneeUserId))
          || { userId: item.task.assigneeUserId, nickName: item.task.assigneeName })
      },
      taskKind: 'asset_image', target: { targetKind: 'asset_item', targetId: item.assetItemId, parentId: asset.assetId, name: `${asset.assetName} · ${item.productionItem}` },
      currentStart: item.task.expectedStartTime, currentEnd: item.task.expectedEndTime
    }
    key = createIdempotencyState(`asset-schedule:${item.task.taskId}`).forPayload({ taskId: item.task.taskId })
    error.value = null
    visible.value = true
  } catch (failure) {
    if (!disposed && !signal.aborted && current === generation) ElMessage.error(failure?.message || '分项排期加载失败，请重试')
  } finally {
    if (current === generation) busy.value = false
  }
}

async function save(command) {
  if (busy.value || !visible.value || !task.value || error.value?.status === 409) return
  const current = generation
  const snapshot = task.value
  busy.value = true
  try {
    await updateTaskSchedule(snapshot.taskId, { ...command, lockVersion: snapshot.lockVersion }, key)
    if (disposed || current !== generation) return
    visible.value = false
    ElMessage.success(snapshot.taskStatus === 'not_started' ? '排期已保存；任务仍需管理人员确认开工。' : '排期已更新，制作状态不变。')
    emit('changed', { projectId: snapshot.projectId, assetId: snapshot.assetId, assetItemId: snapshot.assetItemId })
  } catch (failure) {
    if (disposed || current !== generation) return
    const status = Number(failure?.httpStatus || failure?.status)
    error.value = { ...failure, status, message: status === 409 ? '任务已变化，请关闭窗口、刷新并重新打开排期。' : failure?.message || '排期保存失败，请重试' }
  } finally {
    if (current === generation) busy.value = false
  }
}
defineExpose({ open })
</script>

<template>
  <ScheduleEditDialog v-model:visible="visible" :task="task" :draft="draft" :saving="busy" :error="error" @save-request="save" @cancel="reset" />
</template>
