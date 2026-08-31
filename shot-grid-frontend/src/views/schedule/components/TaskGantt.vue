<script setup>
import ScheduleGanttAdapter from '@/views/schedule/components/ScheduleGanttAdapter.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  scale: { type: String, default: 'week' },
  editable: Boolean
})

const emit = defineEmits(['task-click', 'range-change-request', 'change-rejected'])
</script>

<template>
  <ScheduleGanttAdapter
    :rows="rows"
    :scale="scale"
    :editable="editable"
    @task-click="payload => emit('task-click', payload)"
    @range-change-request="payload => emit('range-change-request', payload)"
    @change-rejected="payload => emit('change-rejected', payload)"
  />
</template>
