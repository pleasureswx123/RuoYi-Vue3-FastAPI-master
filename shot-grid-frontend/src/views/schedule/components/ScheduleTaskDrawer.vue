<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getTaskScheduleChanges } from '@/api/shot-grid/schedules'
import { formatTaskDateTime, taskPriorityMeta, taskStatusMeta } from '@/views/task/taskPresentation'
import { scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { tagTypeFromTone } from '@/utils/tag'
import ShotActionButtons from '@/views/shot/components/ShotActionButtons.vue'
import TableActionButton from '@/components/TableActionButton.vue'
import ScheduleMilestones from './ScheduleMilestones.vue'
import { Edit } from '@element-plus/icons-vue'

const props = defineProps({
  visible: Boolean,
  task: { type: Object, default: null },
  canEdit: Boolean,
  position: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  actionLoader: { type: Function, default: null },
  actionFactory: { type: Function, default: null }
})

const emit = defineEmits(['update:visible', 'edit', 'navigate'])
const history = ref([])
const orderedHistory = computed(() => [...history.value].sort((a, b) => new Date(a.createTime) - new Date(b.createTime) || a.scheduleChangeId - b.scheduleChangeId))
const historyLoading = ref(false)
const historyError = ref(null)
let historyController = null
let generation = 0
const actionTarget = ref(null)
const actionLoading = ref(false)
const actionError = ref('')
let actionController = null
let actionGeneration = 0
const actions = computed(() => props.actionFactory?.(actionTarget.value) || [])

async function loadActions() {
  const current = ++actionGeneration
  actionController?.abort()
  actionTarget.value = null
  actionError.value = ''
  actionLoading.value = false
  if (!props.visible || !props.task || !props.actionLoader) return
  const controller = new AbortController()
  actionController = controller
  actionLoading.value = true
  try {
    const target = await props.actionLoader(props.task, { signal: controller.signal })
    if (current === actionGeneration) actionTarget.value = target
  } catch (error) {
    if (current === actionGeneration && !controller.signal.aborted) actionError.value = error?.message || '操作权限加载失败'
  } finally {
    if (current === actionGeneration) actionLoading.value = false
  }
}
watch(() => [props.visible, props.task?.projectId, props.task?.taskId, props.task?.lockVersion], loadActions, { immediate: true })

const drawerVisible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value)
})

async function loadHistory() {
  const currentGeneration = ++generation
  historyController?.abort()
  historyController = null
  history.value = []
  historyError.value = null
  historyLoading.value = false
  if (!props.visible || !props.task?.taskId) return
  const controller = new AbortController()
  historyController = controller
  historyLoading.value = true
  try {
    const response = await getTaskScheduleChanges(
      props.task.taskId,
      { pageNum: 1, pageSize: 20 },
      { signal: controller.signal }
    )
    if (currentGeneration !== generation) return
    history.value = Array.isArray(response?.rows) ? response.rows : Array.isArray(response?.data?.rows) ? response.data.rows : []
  } catch (error) {
    if (currentGeneration === generation && error?.code !== 'ERR_CANCELED') {
      historyError.value = error
    }
  } finally {
    if (currentGeneration === generation) historyLoading.value = false
  }
}

watch(() => [props.visible, props.task?.taskId, props.task?.lockVersion], loadHistory, { immediate: true })
onBeforeUnmount(() => {
  actionGeneration += 1
  actionController?.abort()
  generation += 1
  historyController?.abort()
})
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    class="sg-detail-drawer schedule-task-drawer"
    modal-class="sg-detail-drawer-mask"
    header-class="sg-detail-drawer__header"
    body-class="sg-detail-drawer__body"
    :title="task ? `排期详情 · ${scheduleTaskLabel(task)}` : '排期详情'"
    direction="rtl"
    size="min(1040px, 95vw)"
    append-to-body
    destroy-on-close
  >
    <div v-if="task" class="schedule-task-detail">
      <div v-if="total" class="schedule-task-detail__navigation">
        <el-button size="small" :disabled="position <= 1" @click="emit('navigate', -1)">上一项</el-button>
        <span>{{ position || '—' }} / {{ total }}</span>
        <el-button size="small" :disabled="!position || position >= total" @click="emit('navigate', 1)">下一项</el-button>
      </div>
      <div class="schedule-task-detail__tags">
        <el-tag :type="tagTypeFromTone(taskStatusMeta(task).tone)" effect="light" round>{{ taskStatusMeta(task).label }}</el-tag>
        <el-tag :type="tagTypeFromTone(taskPriorityMeta(task.priority).tone)" effect="plain" round>{{ taskPriorityMeta(task.priority).label }}优先级</el-tag>
      </div>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="负责人">{{ task.assignee?.userName || task.assignee?.nickName || '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前开始">{{ formatTaskDateTime(task.currentStart) }}</el-descriptions-item>
        <el-descriptions-item label="当前结束">{{ formatTaskDateTime(task.currentEnd) }}</el-descriptions-item>
        <el-descriptions-item label="最初排期">{{ formatTaskDateTime(task.baselineStart) }} 至 {{ formatTaskDateTime(task.baselineEnd) }}</el-descriptions-item>
        <el-descriptions-item label="任务版本">{{ task.lockVersion }}</el-descriptions-item>
      </el-descriptions>

      <div class="schedule-task-detail__timelines">
      <ScheduleMilestones :task="task" :active="visible" />
      <section>
      <div class="schedule-task-detail__heading">
        <h4>最近排期变更</h4>
      </div>
      <el-skeleton v-if="historyLoading" animated :rows="4" />
      <el-alert v-else-if="historyError" type="error" :closable="false" title="排期历史加载失败" description="请稍后重试，不会将失败显示为空历史。" show-icon />
      <el-timeline v-else-if="history.length" mode="alternate">
        <el-timeline-item v-for="(item, index) in orderedHistory" :key="item.scheduleChangeId" :type="index === orderedHistory.length - 1 ? 'warning' : 'success'" hollow :timestamp="formatTaskDateTime(item.createTime)" placement="top">
          <strong class="schedule-change-summary">{{ item.operator?.userName || '未知操作人' }} · {{ item.changeReason }}</strong>
          <el-tooltip :content="`原 ${item.fromStartTime ? formatTaskDateTime(item.fromStartTime) : '未排期'} 至 ${item.fromEndTime ? formatTaskDateTime(item.fromEndTime) : '未排期'}`" placement="top">
            <p class="schedule-change-range">原 {{ item.fromStartTime ? formatTaskDateTime(item.fromStartTime) : '未排期' }} 至 {{ item.fromEndTime ? formatTaskDateTime(item.fromEndTime) : '未排期' }}</p>
          </el-tooltip>
          <el-tooltip :content="`新 ${formatTaskDateTime(item.toStartTime)} 至 ${formatTaskDateTime(item.toEndTime)}`" placement="top">
            <p class="schedule-change-range">新 {{ formatTaskDateTime(item.toStartTime) }} 至 {{ formatTaskDateTime(item.toEndTime) }}</p>
          </el-tooltip>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else :image-size="52" description="暂无可证明的排期变更历史" />
      </section>
      </div>
    </div>
    <template v-if="actionLoader || canEdit" #footer>
      <div class="schedule-task-actions">
        <span v-if="actionLoading" role="status">正在加载可用操作…</span>
        <el-alert v-else-if="actionError" type="error" :title="actionError" :closable="false">
          <el-button link type="primary" @click="loadActions">重试</el-button>
        </el-alert>
        <ShotActionButtons v-else-if="actions.length" :actions="actions" />
        <TableActionButton v-if="canEdit" element-palette :round="false" label="调整排期" type="warning" :icon="Edit" @click="emit('edit', task)" />
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.schedule-task-detail { display: grid; gap: 18px; }
.schedule-change-range { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.schedule-change-summary { font-size: 12px; line-height: 20px; }
.schedule-task-detail__navigation { display: flex; justify-content: space-between; align-items: center; color: var(--sg-text-muted); font-size: 12px; }
.schedule-task-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; text-align: left; }
.schedule-task-actions > span { color: var(--sg-text-muted); font-size: 12px; }
.schedule-task-detail__tags,.schedule-task-detail__heading { display: flex; gap: 8px; align-items: center; }
.schedule-task-detail__heading { justify-content: space-between; }
.schedule-task-detail__heading h4 { margin: 0; font-size: 14px; font-weight: 600; line-height: 20px; }
.schedule-task-detail :deep(.el-descriptions__body),.schedule-task-detail :deep(.el-descriptions__cell) { background: var(--sg-surface-raised)!important; border-color: var(--sg-border)!important; }
.schedule-task-detail :deep(.el-timeline-item__content) p { margin: 6px 0 0; color: var(--sg-text-muted); font-size: 11px; }
.schedule-task-detail__timelines { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 24px; align-items: start; }
.schedule-task-detail__timelines > section {
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 16px;
  background: var(--sg-surface-raised);
  border: 1px solid var(--sg-border);
  border-radius: 12px;
}
.schedule-task-detail__timelines .schedule-task-detail__heading { margin-bottom: 16px; }
@media (max-width: 700px) { .schedule-task-detail__timelines { grid-template-columns: 1fr; } }
</style>
