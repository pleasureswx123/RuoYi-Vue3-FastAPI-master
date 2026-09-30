<script setup>
import { computed } from 'vue'
import { Gantt } from '@svar-ui/vue-gantt'
import '@svar-ui/vue-gantt/all.css'

import { useThemeStore } from '@/store/modules/theme'
import {
  ganttColumns,
  ganttChangedRange,
  ganttScaleFor,
  rangeChangeRequest,
  toGanttTasks
} from '@/views/schedule/adapters/svarGanttAdapter'
import ScheduleGanttTaskTemplate from '@/views/schedule/components/ScheduleGanttTaskTemplate.vue'
import ScheduleGanttDateCell from '@/views/schedule/components/ScheduleGanttDateCell.vue'

const props = defineProps({
  selectedTaskId: { type: Number, default: null },
  resetToken: { type: Number, default: 0 },
  rows: { type: Array, default: () => [] },
  scale: { type: String, default: 'day' },
  groupBy: { type: String, default: 'assignee' },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  showBaseline: { type: Boolean, default: true },
  editable: Boolean
})

const emit = defineEmits(['range-change-request', 'change-rejected', 'task-click'])
const themeStore = useThemeStore()

// SVAR 会从完整边框字符串中截取第一个十六进制颜色交给 Canvas，不能传 CSS 变量或透明色。
const GANTT_CANVAS_GRID_COLOR = {
  light: '#d7dbde',
  dark: '#30353d'
}

const ganttTasks = computed(() => {
  // 取消草稿时重新提供服务端日期，清除组件内部的拖动坐标缓存。
  void props.resetToken
  return toGanttTasks(props.rows, {
  editable: props.editable,
  groupBy: props.groupBy
}).map(task => ({
  ...task,
  showAssignee: props.groupBy !== 'assignee',
  showBaseline: props.showBaseline
}))
})
const columnConfig = computed(() => ganttColumns().map(column => column.id === 'start'
  ? { ...column, cell: ScheduleGanttDateCell }
  : column))
const ganttRuntimeStyle = computed(() => {
  const gridColor = GANTT_CANVAS_GRID_COLOR[themeStore.mode] || GANTT_CANVAS_GRID_COLOR.light
  return {
    '--wx-gantt-border': `1px solid ${gridColor}`,
    '--wx-gantt-border-color': gridColor,
    '--wx-grid-body-row-border': 'var(--wx-gantt-border)',
    '--wx-grid-body-cell-border': 'var(--wx-gantt-border)',
    '--wx-table-cell-border': 'var(--wx-gantt-border)',
    '--wx-table-header-border': 'var(--wx-gantt-border)',
    '--wx-table-header-cell-border': 'var(--wx-gantt-border)',
    '--wx-timescale-border': 'var(--wx-gantt-border)',
    '--wx-gantt-select-color': 'var(--sg-accent-soft)',
    '--wx-background': 'var(--sg-surface)',
    '--wx-background-alt': 'var(--sg-surface-raised)',
    '--wx-background-hover': 'var(--sg-surface-soft)',
    '--wx-color-font': 'var(--sg-text)',
    '--wx-color-font-alt': 'var(--sg-text-secondary)',
    '--wx-color-font-disabled': 'var(--sg-text-muted)',
    '--wx-grid-body-font-color': 'var(--sg-text)',
    '--wx-grid-header-font-color': 'var(--sg-text-secondary)',
    '--wx-timescale-font-color': 'var(--sg-text-secondary)',
    '--wx-timescale-shadow': 'none',
    '--wx-gantt-holiday-background': 'color-mix(in srgb, var(--sg-surface-soft) 72%, transparent)',
    '--wx-gantt-holiday-color': 'var(--sg-text-muted)'
  }
})
const ganttThemeStyle = {
  color: 'var(--sg-text)',
  background: 'var(--sg-surface)',
  border: '1px solid var(--sg-border)',
  borderRadius: 'var(--sg-radius-md, 14px)'
}
const scaleConfig = computed(() => ganttScaleFor(props.scale) || ganttScaleFor('day'))
const ganttStart = computed(() => new Date(props.windowStart))
const ganttEnd = computed(() => new Date(props.windowEnd))

function initializeGantt(api) {
  // 在位移预览前阻止只读任务，不能等拖动结束才拒绝保存。
  api.intercept('drag-task', ({ id }) => {
    const task = ganttTasks.value.find(item => item.id === id)
    if (!props.editable || !task || task.readonly || task.taskId == null) return false
  })
  api.on('select-task', ({ id }) => {
    const selected = ganttTasks.value.find(task => task.id === id)
    if (selected?.taskId != null) {
      emit('task-click', { taskId: selected.taskId })
    }
  })
  api.intercept('update-task', ({ id, task: changes = {}, diff = 0, inProgress }) => {
    if (inProgress || (!changes.start && !changes.end)) return false
    const original = ganttTasks.value.find(task => task.id === id)
    if (!original) {
      emit('change-rejected', { reason: 'task-missing', taskId: id })
      return false
    }
    if (original.taskId == null) {
      return false
    }
    const request = rangeChangeRequest({
      task: original,
      ...ganttChangedRange(original, changes, diff, scaleConfig.value.lengthUnit),
      nextAssigneeUserId: changes.assigneeUserId ?? original.assigneeUserId,
      operationSource: 'gantt'
    })
    if (request.accepted) {
      emit('range-change-request', request.payload)
    } else {
      emit('change-rejected', { reason: request.reason, taskId: original.taskId })
    }
    return false
  })
}
</script>

<template>
  <div class="schedule-gantt-adapter" data-testid="schedule-gantt-adapter" :style="ganttThemeStyle">
    <Gantt
      :key="themeStore.mode"
      :style="ganttRuntimeStyle"
      :tasks="ganttTasks"
      :selected="selectedTaskId == null ? [] : [`task:${selectedTaskId}`]"
      :links="[]"
      :columns="columnConfig"
      :grid-width="columnConfig.reduce((total, column) => total + column.width, 0)"
      :scales="scaleConfig.scales"
      :start="ganttStart"
      :end="ganttEnd"
      :cell-width="scaleConfig.cellWidth"
      :length-unit="scaleConfig.lengthUnit"
      :task-template="ScheduleGanttTaskTemplate"
      duration-unit="hour"
      :readonly="!editable"
      :zoom="false"
      :auto-scale="false"
      :baselines="showBaseline"
      :init="initializeGantt"
    />
  </div>
</template>

<style scoped>
.schedule-gantt-adapter {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.schedule-gantt-adapter :deep(.wx-gantt),
.schedule-gantt-adapter :deep(.wx-layout),
.schedule-gantt-adapter :deep(.wx-table-container),
.schedule-gantt-adapter :deep(.wx-chart),
.schedule-gantt-adapter :deep(.wx-area) {
  color: var(--sg-text);
  background-color: var(--sg-surface);
}

.schedule-gantt-adapter :deep(.wx-chart) {
  scrollbar-width: none;
}

.schedule-gantt-adapter :deep(.wx-table .wx-cell) {
  font-size: 12px;
}

.schedule-gantt-adapter :deep(.wx-chart::-webkit-scrollbar) {
  height: 0;
}

.schedule-gantt-adapter :deep(.wx-table .wx-header),
.schedule-gantt-adapter :deep(.wx-table .wx-header .wx-cell),
.schedule-gantt-adapter :deep(.wx-scale) {
  color: var(--sg-text-secondary);
  background-color: var(--sg-surface-soft);
}

.schedule-gantt-adapter :deep(.wx-table .wx-header) {
  border-bottom: var(--wx-gantt-border);
}

.schedule-gantt-adapter :deep(.wx-table .wx-header .wx-cell:not(:last-child)),
.schedule-gantt-adapter :deep(.wx-table .wx-body .wx-cell:not(:last-child)) {
  border-right: var(--wx-gantt-border);
}

.schedule-gantt-adapter :deep(.wx-table .wx-body .wx-row:not(:last-child)) {
  border-bottom: var(--wx-gantt-border);
}

.schedule-gantt-adapter :deep(.wx-table .wx-body .wx-row[data-id^='group:']) {
  font-weight: 600;
  background-color: var(--sg-surface-raised);
}

.schedule-gantt-adapter :deep(.wx-scale) {
  border-bottom: var(--wx-gantt-border);
}

.schedule-gantt-adapter :deep(.wx-scale .wx-row:not(:last-child)) {
  border-bottom: var(--wx-gantt-border);
}

.schedule-gantt-adapter :deep(.wx-scale .wx-cell) {
  border-right: var(--wx-gantt-border);
}
.schedule-gantt-adapter :deep(.wx-bar:has(.schedule-task-content.is-readonly)) {
  cursor: pointer !important;
}
.schedule-gantt-adapter :deep(.wx-bar:has(.schedule-task-content.is-readonly) .wx-link),
.schedule-gantt-adapter :deep(.wx-bar:has(.schedule-task-content.is-readonly) .wx-progress-marker) {
  display: none;
}
</style>
