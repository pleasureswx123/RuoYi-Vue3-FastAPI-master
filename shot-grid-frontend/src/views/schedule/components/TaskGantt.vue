<script setup>
import ScheduleGanttAdapter from '@/views/schedule/components/ScheduleGanttAdapter.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  scale: { type: String, default: 'week' },
  groupBy: { type: String, default: 'assignee' },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  showBaseline: { type: Boolean, default: true },
  editable: Boolean
})

const emit = defineEmits(['task-click', 'range-change-request', 'change-rejected'])
</script>

<template>
  <ScheduleGanttAdapter
    :rows="rows"
    :scale="scale"
    :group-by="groupBy"
    :window-start="windowStart"
    :window-end="windowEnd"
    :show-baseline="showBaseline"
    :editable="editable"
    @task-click="payload => emit('task-click', payload)"
    @range-change-request="payload => emit('range-change-request', payload)"
    @change-rejected="payload => emit('change-rejected', payload)"
  />
</template>
