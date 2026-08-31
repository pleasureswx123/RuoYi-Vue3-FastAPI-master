<script setup>
import { computed } from 'vue'
import { Gantt } from '@svar-ui/vue-gantt'
import '@svar-ui/vue-gantt/all.css'

import {
  ganttScaleFor,
  rangeChangeRequest,
  toGanttTasks
} from '@/views/schedule/adapters/svarGanttAdapter'
import ScheduleGanttTaskTemplate from '@/views/schedule/components/ScheduleGanttTaskTemplate.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  scale: { type: String, default: 'day' },
  groupBy: { type: String, default: 'assignee' },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  showBaseline: { type: Boolean, default: true },
  editable: Boolean
})

const emit = defineEmits(['range-change-request', 'change-rejected', 'task-click'])

const ganttTasks = computed(() => toGanttTasks(props.rows, {
  editable: props.editable,
  groupBy: props.groupBy
}))
const scaleConfig = computed(() => ganttScaleFor(props.scale) || ganttScaleFor('day'))
const ganttStart = computed(() => new Date(props.windowStart))
const ganttEnd = computed(() => new Date(props.windowEnd))

function initializeGantt(api) {
  api.on('select-task', ({ id }) => {
    const selected = ganttTasks.value.find(task => task.id === id)
    if (selected?.taskId != null) {
      emit('task-click', { taskId: selected.taskId })
    }
  })
  api.intercept('update-task', ({ id, task: changes = {} }) => {
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
      nextStart: changes.start || original.start,
      nextEnd: changes.end || original.end,
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
  <div class="schedule-gantt-adapter" data-testid="schedule-gantt-adapter">
    <Gantt
      :tasks="ganttTasks"
      :links="[]"
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
  min-height: 420px;
  height: 100%;
  overflow: hidden;
}
</style>
