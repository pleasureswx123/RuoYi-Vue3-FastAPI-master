<script setup>
import { formatGanttDate } from '@/views/schedule/adapters/svarGanttAdapter'

defineProps({ row: { type: Object, required: true } })
</script>

<template>
  <div class="schedule-date-cell">
    <span class="schedule-date-cell__line"><span class="schedule-date-cell__label">起</span>{{ formatGanttDate(row.start) || '—' }}</span>
    <span class="schedule-date-cell__line"><span class="schedule-date-cell__label">止</span>{{ formatGanttDate(row.end) || '—' }}</span>
  </div>
</template>

<style scoped>
.schedule-date-cell { display: flex; flex-direction: column; justify-content: center; font-size: 10px; line-height: 14px; font-weight: 400; white-space: nowrap; }
.schedule-date-cell__line { display: flex; align-items: center; gap: 4px; }
.schedule-date-cell__label { color: var(--sg-text-muted); }
</style>
