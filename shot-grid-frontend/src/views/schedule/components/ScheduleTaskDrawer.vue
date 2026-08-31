<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getTaskScheduleChanges } from '@/api/shot-grid/schedules'
import { formatTaskDateTime, taskPriorityMeta, taskStatusMeta } from '@/views/task/taskPresentation'
import { scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({
  visible: Boolean,
  task: { type: Object, default: null },
  canEdit: Boolean
})

const emit = defineEmits(['update:visible', 'edit'])
const history = ref([])
const historyLoading = ref(false)
const historyError = ref(null)
let historyController = null
let generation = 0

const conflictDetails = computed(() => {
  const currentStart = props.task?.currentStart
  const currentEnd = props.task?.currentEnd
  return (props.task?.conflicts || []).map(conflict => {
    const currentStartTime = Date.parse(currentStart)
    const currentEndTime = Date.parse(currentEnd)
    const conflictStartTime = Date.parse(conflict.startTime)
    const conflictEndTime = Date.parse(conflict.endTime)
    const validRange = [currentStartTime, currentEndTime, conflictStartTime, conflictEndTime].every(Number.isFinite)
    return {
      ...conflict,
      overlapStart: validRange && currentStartTime >= conflictStartTime ? currentStart : conflict.startTime,
      overlapEnd: validRange && currentEndTime <= conflictEndTime ? currentEnd : conflict.endTime
    }
  })
})

const drawerVisible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value)
})

async function loadHistory() {
  historyController?.abort()
  historyController = null
  history.value = []
  historyError.value = null
  if (!props.visible || !props.task?.taskId) return
  const currentGeneration = ++generation
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

watch(() => [props.visible, props.task?.taskId], loadHistory, { immediate: true })
onBeforeUnmount(() => {
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
    size="560px"
    append-to-body
    destroy-on-close
  >
    <div v-if="task" class="schedule-task-detail">
      <div class="schedule-task-detail__tags">
        <el-tag :type="tagTypeFromTone(taskStatusMeta(task.taskStatus).tone)" effect="light" round>{{ taskStatusMeta(task.taskStatus).label }}</el-tag>
        <el-tag :type="tagTypeFromTone(taskPriorityMeta(task.priority).tone)" effect="plain" round>{{ taskPriorityMeta(task.priority).label }}优先级</el-tag>
        <el-tag v-if="task.conflicts?.length" type="warning" effect="plain" round>{{ task.conflicts.length }} 项重叠</el-tag>
      </div>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="负责人">{{ task.assignee?.userName || task.assignee?.nickName || '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前开始">{{ formatTaskDateTime(task.currentStart) }}</el-descriptions-item>
        <el-descriptions-item label="当前结束">{{ formatTaskDateTime(task.currentEnd) }}</el-descriptions-item>
        <el-descriptions-item label="首版基线">{{ formatTaskDateTime(task.baselineStart) }} 至 {{ formatTaskDateTime(task.baselineEnd) }}</el-descriptions-item>
        <el-descriptions-item label="任务版本">{{ task.lockVersion }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="task.conflicts?.length"
        class="schedule-task-conflict"
        type="warning"
        :closable="false"
        show-icon
        :title="`发现 ${task.conflicts.length} 项人员排期重叠`"
      >
        <template #default>
          <ul class="schedule-task-conflict__list">
            <li v-for="conflict in conflictDetails" :key="conflict.taskId" :data-conflict-task-id="conflict.taskId">
              <strong>{{ conflict.targetName }}</strong>
              <span>
                冲突任务：
                <time :datetime="conflict.startTime">{{ formatTaskDateTime(conflict.startTime) }}</time>
                至
                <time :datetime="conflict.endTime">{{ formatTaskDateTime(conflict.endTime) }}</time>
              </span>
              <span>
                重叠时段：
                <time :datetime="conflict.overlapStart">{{ formatTaskDateTime(conflict.overlapStart) }}</time>
                至
                <time :datetime="conflict.overlapEnd">{{ formatTaskDateTime(conflict.overlapEnd) }}</time>
              </span>
            </li>
          </ul>
          <p class="schedule-task-conflict__action">可调整当前排期，或在保存时确认保留重叠。</p>
        </template>
      </el-alert>
      <div class="schedule-task-detail__heading">
        <div><p class="sg-eyebrow">HISTORY</p><h3>最近排期变更</h3></div>
        <el-button v-if="canEdit" type="primary" @click="emit('edit', task)">调整排期</el-button>
      </div>
      <el-skeleton v-if="historyLoading" animated :rows="4" />
      <el-alert v-else-if="historyError" type="error" :closable="false" title="排期历史加载失败" description="请稍后重试，不会将失败显示为空历史。" show-icon />
      <el-timeline v-else-if="history.length">
        <el-timeline-item v-for="item in history" :key="item.scheduleChangeId" :timestamp="formatTaskDateTime(item.createTime)" placement="top">
          <strong>{{ item.operator?.userName || '未知操作人' }} · {{ item.changeReason }}</strong>
          <p>{{ formatTaskDateTime(item.toStartTime) }} 至 {{ formatTaskDateTime(item.toEndTime) }}</p>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else :image-size="52" description="暂无可证明的排期变更历史" />
    </div>
  </el-drawer>
</template>

<style scoped>
.schedule-task-detail { display: grid; gap: 18px; }
.schedule-task-detail__tags,.schedule-task-detail__heading { display: flex; gap: 8px; align-items: center; }
.schedule-task-detail__heading { justify-content: space-between; }
.schedule-task-detail__heading h3,.schedule-task-detail__heading p { margin: 0; }
.schedule-task-detail__heading h3 { margin-top: 4px; }
.schedule-task-detail :deep(.el-descriptions__body),.schedule-task-detail :deep(.el-descriptions__cell) { background: var(--sg-surface-raised)!important; border-color: var(--sg-border)!important; }
.schedule-task-detail :deep(.el-timeline-item__content) p { margin: 6px 0 0; color: var(--sg-text-muted); font-size: 11px; }
.schedule-task-conflict__action { margin: 0; }
.schedule-task-conflict__list { display: grid; gap: 10px; margin: 10px 0; padding: 0; list-style: none; }
.schedule-task-conflict__list li { display: grid; gap: 3px; }
.schedule-task-conflict__list strong { color: var(--sg-text); }
.schedule-task-conflict__list span { color: var(--sg-text-muted); font-size: 12px; line-height: 1.55; }
.schedule-task-conflict__action { font-weight: 600; }
</style>
