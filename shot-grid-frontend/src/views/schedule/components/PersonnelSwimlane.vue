<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

import { rangeChangeRequest, toGanttTasks, toSwimlaneRows } from '@/views/schedule/adapters/svarGanttAdapter'

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
const preview = ref(null)
let dragCleanup = null
let suppressClickTaskId = null

function positionStyle(start, end, track = 0) {
  const clippedStart = Math.max(start.getTime(), windowStartMs.value)
  const clippedEnd = Math.min(end.getTime(), windowEndMs.value)
  const left = ((clippedStart - windowStartMs.value) / windowDuration.value) * 100
  const width = Math.max(0.8, ((clippedEnd - clippedStart) / windowDuration.value) * 100)
  return { left: `${left}%`, width: `${width}%`, top: `${8 + track * 38}px` }
}

function visibleRange(task) {
  if (preview.value?.taskId === task.taskId) {
    return { start: preview.value.start, end: preview.value.end }
  }
  return { start: task.start, end: task.end }
}

function taskPositionStyle(task) {
  const range = visibleRange(task)
  return positionStyle(range.start, range.end, task.track)
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

function startDrag(event, task, edge = 'move') {
  if (!props.editable || task.readonly || event.button !== 0) return
  event.preventDefault()
  event.stopPropagation()
  dragCleanup?.()
  const timeline = event.currentTarget.closest('.personnel-lane__timeline')
  const width = Math.max(1, timeline?.getBoundingClientRect().width || 1)
  const originX = event.clientX
  const originStart = task.start.getTime()
  const originEnd = task.end.getTime()
  const minimumDuration = 60 * 1000
  let moved = false
  const move = moveEvent => {
    const delta = Math.round(((moveEvent.clientX - originX) / width) * windowDuration.value / 1000) * 1000
    moved ||= delta !== 0
    let nextStart = originStart
    let nextEnd = originEnd
    if (edge === 'move') {
      nextStart += delta
      nextEnd += delta
    } else if (edge === 'start') {
      nextStart = Math.min(originStart + delta, originEnd - minimumDuration)
    } else {
      nextEnd = Math.max(originEnd + delta, originStart + minimumDuration)
    }
    preview.value = { taskId: task.taskId, start: new Date(nextStart), end: new Date(nextEnd) }
  }
  const up = () => {
    const next = preview.value
    dragCleanup?.()
    if (!moved || !next || next.taskId !== task.taskId) return
    suppressClickTaskId = task.taskId
    globalThis.setTimeout(() => { suppressClickTaskId = null }, 0)
    const request = rangeChangeRequest({
      task,
      nextStart: next.start,
      nextEnd: next.end,
      nextAssigneeUserId: task.assigneeUserId,
      operationSource: 'swimlane'
    })
    if (request.accepted) emit('range-change-request', request.payload)
  }
  dragCleanup = () => {
    globalThis.removeEventListener('pointermove', move)
    globalThis.removeEventListener('pointerup', up)
    preview.value = null
    dragCleanup = null
  }
  globalThis.addEventListener('pointermove', move)
  globalThis.addEventListener('pointerup', up, { once: true })
}

function openTask(task) {
  if (suppressClickTaskId === task.taskId) return
  emit('task-click', { taskId: task.taskId })
}

onBeforeUnmount(() => dragCleanup?.())
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
            :style="taskPositionStyle(task)"
            :data-task-id="task.taskId"
            :aria-label="`${task.text}，${task.assigneeName}`"
            text
            @pointerdown="event => startDrag(event, task, 'move')"
            @click="openTask(task)"
          >
            <span v-if="editable && !task.readonly" class="personnel-task__handle is-start" aria-hidden="true" @pointerdown.stop="event => startDrag(event, task, 'start')" />
            <span class="personnel-task__label">{{ task.text }}</span>
            <span v-if="editable && !task.readonly" class="personnel-task__handle is-end" aria-hidden="true" @pointerdown.stop="event => startDrag(event, task, 'end')" />
          </el-button>
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
.personnel-task__label { display: block; overflow: hidden; text-overflow: ellipsis; }
.personnel-task__handle { position: absolute; z-index: 3; top: 3px; bottom: 3px; width: 6px; cursor: ew-resize; background: color-mix(in srgb,var(--sg-text) 35%,transparent); border-radius: 3px; }
.personnel-task__handle.is-start { left: 2px; }.personnel-task__handle.is-end { right: 2px; }
.personnel-task.status-completed { background: color-mix(in srgb,var(--el-color-success) 18%,var(--sg-surface-raised))!important; border-color: var(--el-color-success)!important; }
.personnel-task.is-conflicted { border-color: var(--el-color-danger)!important; box-shadow: 0 0 0 1px color-mix(in srgb,var(--el-color-danger) 38%,transparent); }
.personnel-task__baseline { position: absolute; z-index: 1; height: 4px; background: color-mix(in srgb,var(--el-color-info) 60%,transparent); border: 1px dashed var(--el-color-info); border-radius: 999px; }
</style>
