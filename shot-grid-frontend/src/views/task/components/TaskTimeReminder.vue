<script setup>
import { computed } from 'vue'
import { formatTaskDateTime, taskTimeReminder } from '../taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({ task: { type: Object, required: true }, now: { type: Date, required: true }, compact: { type: Boolean, default: false } })
const reminder = computed(() => taskTimeReminder(props.task, props.now))
</script>

<template>
  <span class="task-time-reminder" :class="{ 'is-compact': compact }" aria-label="时间提醒">
    <span><el-tag :type="tagTypeFromTone(reminder.tone)" effect="light" size="small" round>时间：{{ reminder.label }}</el-tag></span>
    <span v-if="task.expectedStartTime" class="task-time-reminder__range">{{ formatTaskDateTime(task.expectedStartTime) }} 至 {{ formatTaskDateTime(task.expectedEndTime) }}</span>
    <span v-else-if="task.dueDate">原截止日期：{{ task.dueDate }}</span>
    <span v-if="!compact || ['warning', 'overdue'].includes(reminder.state)" class="task-time-reminder__message">{{ reminder.message }}</span>
  </span>
</template>

<style scoped>
.task-time-reminder{display:grid;gap:6px;white-space:normal;line-height:1.6}.task-time-reminder__range{font-variant-numeric:tabular-nums}.task-time-reminder__message{font-size:12px;color:var(--sg-text-secondary)}.is-compact{font-size:11px;text-align:left}.is-compact .task-time-reminder__message{font-size:11px}
</style>
