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
const hasBaseline = computed(() => !isGroup.value && Object.keys(baselineStyle.value).length > 0)
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
    <span class="schedule-task-content__label">{{ data.text }}</span>
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
  border: 1px solid transparent;
  border-radius: 5px;
}

.schedule-task-content.is-conflicted {
  border-color: var(--el-color-danger);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-danger) 38%, transparent);
}

.schedule-task-content.is-readonly {
  cursor: default;
}

.schedule-task-content.is-group {
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
  z-index: 1;
  min-width: 0;
  padding: 0 7px;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
