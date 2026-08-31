<script setup>
import { computed } from 'vue'

import { baselineOverlayStyle } from '@/views/schedule/adapters/svarGanttAdapter'

defineOptions({ name: 'ScheduleGanttTaskTemplate' })

const props = defineProps({
  data: { type: Object, required: true }
})

const baselineStyle = computed(() => baselineOverlayStyle(props.data))
const hasConflict = computed(() => props.data.conflictTaskIds?.length > 0)
const isGroup = computed(() => props.data.isScheduleGroup === true)
const hasBaseline = computed(() => (
  props.data.showBaseline !== false
  && !isGroup.value
  && Object.keys(baselineStyle.value).length > 0
))
const currentBarClasses = computed(() => ({
  'is-current-schedule': !isGroup.value,
  'is-conflicted': hasConflict.value,
  'is-readonly': props.data.readonly,
  'is-group': isGroup.value,
  [`status-${props.data.taskStatus}`]: !isGroup.value && Boolean(props.data.taskStatus)
}))
</script>

<template>
  <div
    class="schedule-task-content"
    :class="{ 'is-conflicted': hasConflict, 'is-readonly': data.readonly, 'is-group': isGroup }"
    data-testid="schedule-task-content"
  >
    <span
      v-if="hasBaseline"
      class="schedule-task-content__baseline"
      :style="baselineStyle"
      data-testid="schedule-baseline-shadow"
      aria-hidden="true"
    />
    <span
      class="schedule-task-content__current"
      :class="currentBarClasses"
      data-testid="schedule-current-bar"
    >
      <span class="schedule-task-content__label">{{ data.text }}</span>
    </span>
  </div>
</template>

<style scoped>
.schedule-task-content {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  align-items: center;
  overflow: visible;
}

.schedule-task-content__current {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  min-width: 0;
  align-items: center;
  overflow: hidden;
  color: var(--sg-text);
  border: 1px solid transparent;
  border-radius: 5px;
}

.schedule-task-content__current.is-current-schedule {
  background: color-mix(in srgb, var(--el-color-primary) 22%, var(--sg-surface-raised));
  border-color: color-mix(in srgb, var(--el-color-primary) 55%, transparent);
}

.schedule-task-content__current.status-completed {
  background: color-mix(in srgb, var(--el-color-success) 18%, var(--sg-surface-raised));
  border-color: var(--el-color-success);
}

.schedule-task-content__current.is-conflicted {
  border-color: var(--el-color-danger);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-danger) 38%, transparent);
}

.schedule-task-content__current.is-readonly {
  cursor: default;
}

.schedule-task-content__current.is-group {
  font-weight: 600;
}

.schedule-task-content__baseline {
  position: absolute;
  bottom: -7px;
  height: 4px;
  pointer-events: none;
  background: color-mix(in srgb, var(--el-color-info) 58%, transparent);
  border: 1px solid color-mix(in srgb, var(--el-color-info) 82%, transparent);
  border-radius: 999px;
}

.schedule-task-content__label {
  position: relative;
  min-width: 0;
  padding: 0 7px;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
