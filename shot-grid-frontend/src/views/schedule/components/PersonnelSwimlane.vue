<script setup>
import { computed } from 'vue'

import { toGanttTasks, toSwimlaneRows } from '@/views/schedule/adapters/svarGanttAdapter'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  scale: { type: String, default: 'week' },
  editable: Boolean
})

const emit = defineEmits(['task-click', 'range-change-request'])
const windowStartMs = computed(() => new Date(props.windowStart).getTime())
const windowEndMs = computed(() => new Date(props.windowEnd).getTime())
const windowDuration = computed(() => Math.max(1, windowEndMs.value - windowStartMs.value))
const lanes = computed(() => toSwimlaneRows(toGanttTasks(props.rows, { editable: props.editable })))
const laneHeight = lane => Math.max(54, lane.trackCount * 38 + 16)

function positionStyle(start, end, track = 0) {
  const clippedStart = Math.max(start.getTime(), windowStartMs.value)
  const clippedEnd = Math.min(end.getTime(), windowEndMs.value)
  const left = ((clippedStart - windowStartMs.value) / windowDuration.value) * 100
  const width = Math.max(0.8, ((clippedEnd - clippedStart) / windowDuration.value) * 100)
  return { left: `${left}%`, width: `${width}%`, top: `${8 + track * 38}px` }
}

function baselineStyle(task) {
  const style = positionStyle(task.baseline.start, task.baseline.end, task.track)
  return { left: style.left, width: style.width, top: `${31 + task.track * 38}px` }
}

const ticks = computed(() => {
  const count = props.scale === 'day' ? 8 : props.scale === 'week' ? 6 : 4
  return Array.from({ length: count + 1 }, (_, index) => {
    const date = new Date(windowStartMs.value + (windowDuration.value * index) / count)
    return {
      key: date.toISOString(),
      left: `${(index / count) * 100}%`,
      label: props.scale === 'month'
        ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
        : `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    }
  })
})
</script>

<template>
  <section class="personnel-swimlane" data-testid="personnel-swimlane">
    <div class="personnel-swimlane__header">
      <strong>制作人员</strong>
      <div class="personnel-swimlane__ticks">
        <span v-for="tick in ticks" :key="tick.key" :style="{ left: tick.left }">{{ tick.label }}</span>
      </div>
    </div>
    <div
      v-for="lane in lanes"
      :key="lane.id"
      class="personnel-lane"
      data-testid="personnel-lane"
      :data-track-count="lane.trackCount"
      :style="{ minHeight: `${laneHeight(lane)}px` }"
    >
      <header><strong>{{ lane.assigneeName }}</strong><small>{{ lane.tasks.length }} 项任务</small></header>
      <div class="personnel-lane__timeline">
        <span v-for="tick in ticks" :key="tick.key" class="personnel-lane__gridline" :style="{ left: tick.left }" aria-hidden="true" />
        <template v-for="task in lane.tasks" :key="task.id">
          <span class="personnel-task__baseline" :style="baselineStyle(task)" aria-hidden="true" />
          <el-button
            class="personnel-task"
            :class="[task.className, `status-${task.taskStatus}`]"
            :style="positionStyle(task.start, task.end, task.track)"
            :data-task-id="task.taskId"
            :aria-label="`${task.text}，${task.assigneeName}`"
            text
            @click="emit('task-click', { taskId: task.taskId })"
          >{{ task.text }}</el-button>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.personnel-swimlane { min-width: 900px; overflow: hidden; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.personnel-swimlane__header,.personnel-lane { display: grid; grid-template-columns: 170px minmax(720px,1fr); }
.personnel-swimlane__header { min-height: 44px; color: var(--sg-text-muted); font-size: 11px; background: var(--sg-surface-raised); border-bottom: 1px solid var(--sg-border); }
.personnel-swimlane__header>strong,.personnel-lane>header { display: flex; padding: 0 16px; align-items: center; border-right: 1px solid var(--sg-border); }
.personnel-swimlane__ticks,.personnel-lane__timeline { position: relative; min-width: 0; }
.personnel-swimlane__ticks span { position: absolute; top: 13px; transform: translateX(-50%); white-space: nowrap; }
.personnel-lane { border-bottom: 1px solid var(--sg-border); }
.personnel-lane:last-child { border-bottom: 0; }
.personnel-lane>header { flex-direction: column; align-items: flex-start; justify-content: center; }
.personnel-lane>header small { margin-top: 3px; color: var(--sg-text-muted); font-size: 10px; }
.personnel-lane__gridline { position: absolute; top: 0; bottom: 0; border-left: 1px dashed color-mix(in srgb,var(--sg-border) 75%,transparent); }
.personnel-task { position: absolute; z-index: 2; display: block; height: 28px; padding: 0 9px!important; overflow: hidden; color: var(--sg-text)!important; text-align: left; text-overflow: ellipsis; white-space: nowrap; background: color-mix(in srgb,var(--el-color-primary) 22%,var(--sg-surface-raised))!important; border: 1px solid color-mix(in srgb,var(--el-color-primary) 55%,transparent)!important; border-radius: 6px; }
.personnel-task.status-completed { background: color-mix(in srgb,var(--el-color-success) 18%,var(--sg-surface-raised))!important; border-color: var(--el-color-success)!important; }
.personnel-task.is-conflicted { border-color: var(--el-color-danger)!important; box-shadow: 0 0 0 1px color-mix(in srgb,var(--el-color-danger) 38%,transparent); }
.personnel-task__baseline { position: absolute; z-index: 1; height: 4px; background: color-mix(in srgb,var(--el-color-info) 60%,transparent); border: 1px dashed var(--el-color-info); border-radius: 999px; }
</style>
