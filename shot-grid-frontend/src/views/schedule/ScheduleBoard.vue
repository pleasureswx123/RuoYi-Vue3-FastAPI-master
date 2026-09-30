<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'

import { useScheduleStore } from '@/store/modules/schedule'
import { matchesScheduleDeadline, scheduleErrorState, scheduleStatusOptions, scheduleStatusStyle } from '@/views/schedule/schedulePresentation'
import { useScheduleCatalog } from '@/views/schedule/useScheduleCatalog'
import { scheduleWindowForScale, shiftScheduleWindow } from '@/views/schedule/scheduleWindow'
import { useScheduleMutation } from '@/views/schedule/useScheduleMutation'
import ScheduleToolbar from '@/views/schedule/components/ScheduleToolbar.vue'
import PersonnelSwimlane from '@/views/schedule/components/PersonnelSwimlane.vue'
import TaskGantt from '@/views/schedule/components/TaskGantt.vue'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'
import UnscheduledTaskDrawer from '@/views/schedule/components/UnscheduledTaskDrawer.vue'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  targetKind: { type: String, default: 'all' },
  initialMode: { type: String, default: 'swimlane' },
  initialScale: { type: String, default: 'day' },
  initialGroupBy: { type: String, default: 'assignee' },
  initialWindowStart: { type: String, default: '' },
  initialWindowEnd: { type: String, default: '' },
  initialFilters: { type: Object, default: () => ({}) },
  editableAllowed: Boolean,
  actionLoader: { type: Function, default: null },
  actionFactory: { type: Function, default: null }
})

const emit = defineEmits(['query-change'])
const store = useScheduleStore()
const mutation = useScheduleMutation(store, { onSaved: revealSavedTask, onRefresh: refresh })
const detailVisible = ref(false)
const unscheduledVisible = ref(false)
const accessNotice = ref('')
const showBaseline = ref(false)
const draftResetToken = ref(0)
const isPanning = ref(false)
let stopPan = null

function canvasViewport(event) {
  // 甘特图使用内部滚动容器，其 scroll 事件会同步日期表头与渲染窗口。
  return store.mode === 'gantt' ? event.target.closest('.wx-chart') : event.currentTarget
}

function startCanvasPan(event) {
  if (store.loading || event.button !== 0 || event.pointerType === 'touch') return
  if (event.target.closest('button, a, input, select, textarea, [role="button"], .wx-bar, .schedule-task-content')) return
  const viewport = canvasViewport(event)
  if (!viewport) return
  if (viewport.scrollWidth <= viewport.clientWidth) return
  stopPan?.()
  const startX = event.clientX
  const startScroll = viewport.scrollLeft
  const pointerId = event.pointerId
  const move = next => {
    if (next.pointerId !== pointerId) return
    const delta = next.clientX - startX
    if (!isPanning.value && Math.abs(delta) < 4) return
    isPanning.value = true
    next.preventDefault()
    viewport.scrollLeft = startScroll - delta
  }
  const end = next => {
    if (next.pointerId === pointerId) stopPan?.()
  }
  stopPan = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    window.removeEventListener('pointercancel', end)
    window.removeEventListener('blur', stopPan)
    isPanning.value = false
    stopPan = null
  }
  window.addEventListener('pointermove', move, { passive: false })
  window.addEventListener('pointerup', end)
  window.addEventListener('pointercancel', end)
  window.addEventListener('blur', stopPan)
  event.preventDefault()
}

function scrollCanvasHorizontally(event) {
  if (!event.shiftKey || event.ctrlKey) return
  const viewport = canvasViewport(event)
  if (!viewport) return
  if (viewport.scrollWidth <= viewport.clientWidth) return
  event.preventDefault()
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientWidth : 1
  viewport.scrollLeft += (event.deltaX || event.deltaY) * unit
}

watch(() => [store.mode, store.loading, props.projectId], () => stopPan?.())
onBeforeUnmount(() => stopPan?.())
const defaultWindow = scheduleWindowForScale(props.initialScale)
const windowStart = ref(props.initialWindowStart || defaultWindow.windowStart)
const windowEnd = ref(props.initialWindowEnd || defaultWindow.windowEnd)
const viewportRef = ref(null)
const deadlineFilter = ref('')
const catalog = useScheduleCatalog(() => ({ projectId: props.projectId, targetKind: props.targetKind, windowStart: windowStart.value, windowEnd: windowEnd.value }))
const visibleTasks = computed(() => store.tasks.filter(task =>
  new Date(task.currentStart) < new Date(windowEnd.value)
  && new Date(task.currentEnd) > new Date(windowStart.value)
  && matchesScheduleDeadline(task, deadlineFilter.value, store.serverTime || new Date())
))
const selectedIndex = computed(() => visibleTasks.value.findIndex(task => task.taskId === store.selectedTaskId))
const statusCounts = computed(() => catalog.rows.value.reduce((counts, task) => {
  counts[task.taskStatus] = (counts[task.taskStatus] || 0) + 1
  return counts
}, {}))
const selectedTask = computed(() => store.tasks.find(task => task.taskId === store.selectedTaskId) || null)
const errorState = computed(() => store.error ? scheduleErrorState(store.error) : null)
const filterOptions = computed(() => {
  const assignees = new Map()
  const episodes = new Map()
  const scenes = new Map()
  const assetTypes = new Set()
  for (const task of catalog.rows.value) {
    if (task.assignee?.userId) assignees.set(task.assignee.userId, task.assignee.userName)
    if (task.target?.episodeId) episodes.set(task.target.episodeId, `第 ${task.target.episodeNo ?? task.target.episodeId} 集`)
    if (task.target?.sceneId) scenes.set(task.target.sceneId, `场次 ${task.target.sceneNo ?? task.target.sceneId}`)
    if (task.target?.assetType) assetTypes.add(task.target.assetType)
  }
  const entries = map => [...map].map(([value, label]) => ({ value, label }))
  return {
    assignees: entries(assignees),
    episodes: entries(episodes),
    scenes: entries(scenes),
    assetTypes: [...assetTypes].map(value => ({ value, label: value }))
  }
})
const effectiveQuery = computed(() => ({
  windowStart: store.loadedWindow?.windowStart || windowStart.value,
  windowEnd: store.loadedWindow?.windowEnd || windowEnd.value,
  targetKind: store.targetKind,
  groupBy: store.groupBy,
  ...store.filters
}))

async function load() {
  await store.loadSchedule(windowStart.value, windowEnd.value).catch(() => undefined)
}

function publishQuery() {
  emit('query-change', {
    mode: store.mode,
    scale: store.scale,
    groupBy: store.groupBy,
    windowStart: windowStart.value,
    windowEnd: windowEnd.value
  })
}

function setMode(mode) {
  store.setMode(mode)
  publishQuery()
}

function setScale(scale) {
  if (scale === store.scale) return
  const now = new Date()
  const currentStart = new Date(windowStart.value)
  const currentEnd = new Date(windowEnd.value)
  const anchor = now >= currentStart && now < currentEnd
    ? now
    : new Date(currentStart.getTime() + (currentEnd.getTime() - currentStart.getTime()) / 2)
  store.setScale(scale)
  setWindow(scheduleWindowForScale(scale, anchor))
}

function setGroupBy(groupBy) {
  store.setGrouping(groupBy)
  publishQuery()
  load()
}

function setWindow(value) {
  windowStart.value = value.windowStart
  windowEnd.value = value.windowEnd
  store.invalidateQuery()
  publishQuery()
  load()
}

function shiftWindow(direction) {
  if (direction === 0) {
    setWindow(scheduleWindowForScale(store.scale))
    return
  }
  setWindow(shiftScheduleWindow(windowStart.value, windowEnd.value, direction, store.scale))
}

function setFilters(filters) {
  store.setFilters(filters)
  load()
}

function filterByLegend(status) {
  const selected = store.filters.taskStatuses || []
  setFilters({
    ...store.filters,
    taskStatuses: selected.length === 1 && selected[0] === status ? [] : [status]
  })
}

function applyInitialFilters(value) {
  const source = value && typeof value === 'object' ? value : {}
  store.setFilters({
    assigneeUserIds: Array.isArray(source.assigneeUserIds) ? source.assigneeUserIds : [],
    taskKinds: Array.isArray(source.taskKinds) ? source.taskKinds : [],
    taskStatuses: Array.isArray(source.taskStatuses) ? source.taskStatuses : [],
    priorities: Array.isArray(source.priorities) ? source.priorities : [],
    keyword: typeof source.keyword === 'string' ? source.keyword : '',
    episodeIds: Array.isArray(source.episodeIds) ? source.episodeIds : [],
    sceneIds: Array.isArray(source.sceneIds) ? source.sceneIds : [],
    shotNoStart: source.shotNoStart ?? null,
    shotNoEnd: source.shotNoEnd ?? null,
    assetTypes: Array.isArray(source.assetTypes) ? source.assetTypes : [],
    onlyConflicts: Boolean(source.onlyConflicts),
    onlyDelayed: Boolean(source.onlyDelayed)
  })
}

function toggleEdit(enabled) {
  accessNotice.value = ''
  if (enabled && !props.editableAllowed) {
    store.setEditMode(false)
    accessNotice.value = '没有调整排期权限；当前仍可只读查看项目计划。'
    return
  }
  store.setEditMode(enabled)
  if (!enabled) mutation.close()
}

function openTask({ taskId }) {
  store.selectedTaskId = taskId
  detailVisible.value = true
}

function requestRangeChange(payload) {
  const task = store.tasks.find(item => item.taskId === payload.taskId)
  if (!store.editMode || !props.editableAllowed) {
    accessNotice.value = '请先由授权管理人员显式进入排期编辑模式。'
    return
  }
  if (task) mutation.open(task, payload)
}

function openEdit(task) {
  if (!props.editableAllowed || !task?.allowedActions?.includes('schedule')) {
    accessNotice.value = '当前没有调整该任务排期的权限。'
    return
  }
  accessNotice.value = ''
  if (mutation.open(task, { operationSource: 'dialog' })) unscheduledVisible.value = false
}

async function revealSavedTask(saved) {
  if (!saved || Number(saved.projectId) !== Number(props.projectId)) return
  const start = new Date(saved.currentStart)
  if (start < new Date(windowStart.value) || start >= new Date(windowEnd.value)) {
    const range = scheduleWindowForScale(store.scale, start)
    windowStart.value = range.windowStart
    windowEnd.value = range.windowEnd
    publishQuery()
  }
  deadlineFilter.value = ''
  await refresh()
  if (Number(saved.projectId) !== Number(props.projectId)) return
  store.selectedTaskId = saved.taskId
  await nextTick()
  const target = viewportRef.value?.querySelector(`[data-task-id="${saved.taskId}"], .wx-row[data-id="task:${saved.taskId}"]`)
  target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  if (!visibleTasks.value.some(task => task.taskId === saved.taskId)) {
    accessNotice.value = '排期已保存，该任务不符合当前筛选条件；可重置筛选后查看。'
  }
}

function cancelScheduleDraft() {
  if (mutation.saving.value || !mutation.visible.value) return
  mutation.close()
  draftResetToken.value += 1
}

async function saveMutation(form) {
  const saved = await mutation.save(form)
  if (saved) ElMessage.success('排期已保存')
  if (!saved && ['SG_TASK_SCHEDULE_READ_ONLY'].includes(mutation.error.value?.errorKey)) {
    accessNotice.value = '排期权限或任务状态已变化，已退出编辑模式；请刷新后确认。'
  }
}

function handleRejected(payload) {
  accessNotice.value = payload.reason === 'assignee-change'
    ? '跨泳道拖动不会改变负责人；请使用现有改派流程。'
    : '该任务当前不可调整排期。'
}

async function refresh() {
  const viewport = viewportRef.value
  const positions = [viewport, viewport?.querySelector('.wx-gantt'), viewport?.querySelector('.wx-chart')]
    .filter(Boolean).map(element => ({ element, top: element.scrollTop, left: element.scrollLeft }))
  store.invalidateQuery()
  await Promise.all([load(), catalog.refresh()])
  await nextTick()
  for (const { element, top, left } of positions) {
    if (element.isConnected) { element.scrollTop = top; element.scrollLeft = left }
  }
}

function navigateTask(direction) {
  const task = visibleTasks.value[selectedIndex.value + direction]
  if (task) store.selectedTaskId = task.taskId
}

onMounted(() => {
  store.setProject(props.projectId)
  store.setMode(props.initialMode)
  store.setScale(props.initialScale)
  store.setGrouping(props.initialGroupBy)
  store.setTargetKind(props.targetKind)
  applyInitialFilters(props.initialFilters)
  load()
})

watch(() => props.projectId, projectId => {
  store.setProject(projectId)
  load()
})

watch(() => props.initialMode, mode => {
  store.setMode(mode)
})

watch(() => props.initialScale, scale => {
  store.setScale(scale)
})

watch(() => props.initialGroupBy, groupBy => {
  store.setGrouping(groupBy)
  load()
})

watch(() => props.targetKind, targetKind => {
  store.setTargetKind(targetKind)
  load()
})

watch(() => props.initialFilters, filters => {
  applyInitialFilters(filters)
  load()
}, { deep: true })

watch(
  () => [props.initialWindowStart, props.initialWindowEnd],
  ([nextStart, nextEnd], [previousStart, previousEnd]) => {
    if (!nextStart || !nextEnd || (nextStart === previousStart && nextEnd === previousEnd)) return
    windowStart.value = nextStart
    windowEnd.value = nextEnd
    store.invalidateQuery()
    load()
  }
)

watch(() => props.editableAllowed, allowed => {
  if (!allowed) {
    store.setEditMode(false)
    mutation.close()
  }
})

onBeforeUnmount(() => {
  mutation.dispose()
  store.dispose()
})
</script>

<template>
  <section class="schedule-board" data-testid="schedule-board">
    <ScheduleToolbar
      :mode="store.mode"
      :scale="store.scale"
      :group-by="store.groupBy"
      :window-start="windowStart"
      :window-end="windowEnd"
      :filters="store.filters"
      :loading="store.loading"
      :edit-mode="store.editMode"
      :editable-allowed="editableAllowed"
      :unscheduled-count="store.unscheduledCount"
      :filter-options="filterOptions"
      :show-baseline="showBaseline"
      @update:mode="setMode"
      @update:scale="setScale"
      @update:group-by="setGroupBy"
      @window-change="setWindow"
      @window-shift="shiftWindow"
      @filters-change="setFilters"
      @baseline-change="value => { showBaseline = value }"
      @refresh="refresh"
      @edit-toggle="toggleEdit"
      @open-unscheduled="unscheduledVisible = true"
    >
      <template #deadline-filter>
      <el-radio-group v-model="deadlineFilter" size="small" aria-label="当前窗口到期筛选">
        <el-radio-button value="">全部时间</el-radio-button>
        <el-radio-button value="today">今日到期</el-radio-button>
        <el-radio-button value="overdue">已逾期</el-radio-button>
        <el-radio-button value="week">本周交付</el-radio-button>
      </el-radio-group>
      </template>
    </ScheduleToolbar>

    <el-alert v-if="catalog.error.value" :title="catalog.error.value" type="warning" :closable="false">
      <el-button link type="primary" @click="catalog.refresh">重新加载选项</el-button>
    </el-alert>

    <el-alert
      v-if="accessNotice"
      type="warning"
      :closable="false"
      show-icon
      :title="accessNotice"
    />
    <div class="schedule-board__caption">
      <div v-if="!accessNotice" class="schedule-board__mode-hint">
        <el-icon><Warning /></el-icon>
        <span>{{ store.editMode ? '拖动编辑已开启；拖动只生成草稿，确认原因后才会保存。' : '拖动编辑未开启；当前排期为实色条，开启对比后细线表示最初排期，允许同一制作人安排重叠任务。' }}</span>
        <span>拖动空白处或 Shift＋滚轮可左右移动。</span>
      </div>
      <div class="schedule-board__legend" aria-label="任务状态颜色图例" title="数量为当前项目时间窗口内的状态总数，不随其他筛选变化">
        <span class="schedule-board__task-count" title="当前窗口内符合筛选条件的任务数">当前窗口显示 {{ visibleTasks.length }} 项任务</span>
        <el-button
          v-for="status in scheduleStatusOptions"
          :key="status.value"
          class="schedule-board__legend-item"
          :class="{ 'is-selected': store.filters.taskStatuses?.includes(status.value) }"
          :style="scheduleStatusStyle(status.value)"
          :aria-pressed="Boolean(store.filters.taskStatuses?.includes(status.value))"
          :data-status="status.value"
          text
          size="small"
          @click="filterByLegend(status.value)"
        ><span class="schedule-board__swatch" aria-hidden="true" />{{ status.label }} {{ catalog.loading.value || catalog.error.value ? '—' : statusCounts[status.value] || 0 }}</el-button>
      </div>
    </div>
    <el-alert
      v-if="errorState"
      type="error"
      :closable="false"
      show-icon
      :title="errorState.title"
      :description="`${errorState.message} · ${errorState.action}`"
    >
      <template v-if="errorState.retryable" #default><el-button size="small" @click="refresh">重试</el-button></template>
    </el-alert>
    <el-skeleton v-else-if="store.loading && !store.tasks.length" class="schedule-board__skeleton" animated :rows="10" />
    <el-empty v-else-if="!visibleTasks.length" :image-size="72" description="当前时间窗口没有符合筛选条件的排期任务">
      <p>可调整日期、筛选条件，或打开未排期任务池安排时间。</p>
    </el-empty>
    <div
      v-else
      ref="viewportRef"
      class="schedule-board__viewport"
      :class="{ 'is-loading': store.loading, 'is-pannable': store.mode === 'swimlane', 'is-gantt': store.mode === 'gantt', 'is-panning': isPanning }"
      :style="{ overflowX: store.mode === 'gantt' ? 'hidden' : undefined }"
      @pointerdown="startCanvasPan"
      @wheel="scrollCanvasHorizontally"
    >
      <PersonnelSwimlane
        v-if="store.mode === 'swimlane'"
        :rows="visibleTasks"
        :selected-task-id="store.selectedTaskId"
        :window-start="windowStart"
        :window-end="windowEnd"
        :scale="store.scale"
        :group-by="store.groupBy"
        :editable="store.editMode && editableAllowed"
        :show-baseline="showBaseline"
        @task-click="openTask"
        @range-change-request="requestRangeChange"
      />
      <TaskGantt
        :reset-token="draftResetToken"
        v-else
        :rows="visibleTasks"
        :selected-task-id="store.selectedTaskId"
        :scale="store.scale"
        :group-by="store.groupBy"
        :window-start="windowStart"
        :window-end="windowEnd"
        :editable="store.editMode && editableAllowed"
        :show-baseline="showBaseline"
        @task-click="openTask"
        @range-change-request="requestRangeChange"
        @change-rejected="handleRejected"
      />
    </div>

    <ScheduleTaskDrawer
      v-model:visible="detailVisible"
      :task="selectedTask"
      :position="selectedIndex + 1"
      :total="visibleTasks.length"
      @navigate="navigateTask"
      :action-loader="actionLoader"
      :action-factory="actionFactory"
      :can-edit="Boolean(selectedTask?.allowedActions?.includes('schedule') && editableAllowed)"
      @edit="openEdit"
    />
    <UnscheduledTaskDrawer
      v-model:visible="unscheduledVisible"
      :project-id="projectId"
      :query="effectiveQuery"
      @edit-task="openEdit"
    />
    <ScheduleEditDialog
      :visible="mutation.visible.value"
      :task="mutation.activeTask.value"
      :draft="mutation.draft.value"
      :saving="mutation.saving.value"
      :error="mutation.error.value"
      @update:visible="value => { if (!value) cancelScheduleDraft() }"
      @cancel="cancelScheduleDraft"
      @save-request="saveMutation"
    />
  </section>
</template>

<style scoped>
.schedule-board { display: grid; gap: 14px; min-width: 0; }
.schedule-board__task-count { align-self: center; font-size: 12px; color: var(--sg-text-muted); white-space: nowrap; }
.schedule-board__caption { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 20px; }
.schedule-board__legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-left: auto; }
.schedule-board__legend-item { margin: 0; padding: 3px 5px; color: var(--sg-text-muted); font-size: 11px; white-space: nowrap; }
.schedule-board__legend-item :deep(> span) { gap: 5px; }
.schedule-board__legend-item.is-selected { color: var(--sg-schedule-status-color); background: color-mix(in srgb, var(--sg-schedule-status-color) 12%, var(--sg-surface-raised)); box-shadow: inset 0 0 0 1px var(--sg-schedule-status-color); }
.schedule-board__swatch { width: 16px; height: 10px; flex-shrink: 0; background: color-mix(in srgb, var(--sg-schedule-status-color) 18%, var(--sg-surface-raised)); border: 1px solid color-mix(in srgb, var(--sg-schedule-status-color) 65%, transparent); border-radius: 2px; }
.schedule-board__mode-hint { display: flex; gap: 8px; align-items: center; color: var(--sg-text-muted); font-size: 11px; }
.schedule-board__viewport { height: max(280px, calc(100dvh - var(--app-header-height, 76px) - 88px)); min-height: 0; overflow: auto; border-radius: var(--sg-radius-md); }
.schedule-board__viewport.is-gantt { overflow: hidden; }
.schedule-board__viewport.is-loading { opacity: .62; pointer-events: none; }
.schedule-board__viewport.is-pannable { cursor: grab; scrollbar-width: none; }
.schedule-board__viewport.is-pannable::-webkit-scrollbar { height: 0; }
.schedule-board__viewport :deep(.wx-chart .wx-area) { cursor: grab; }
.schedule-board__viewport.is-panning { cursor: grabbing; user-select: none; }
.schedule-board__viewport.is-panning :deep(*) { cursor: grabbing !important; user-select: none; }
.schedule-board__skeleton { min-height: 420px; padding: 22px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.schedule-board__limit { margin: 0; color: var(--el-color-warning); font-size: 11px; text-align: right; }
</style>
