<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Warning } from '@element-plus/icons-vue'

import { useScheduleStore } from '@/store/modules/schedule'
import { scheduleErrorState } from '@/views/schedule/schedulePresentation'
import ScheduleToolbar from '@/views/schedule/components/ScheduleToolbar.vue'
import PersonnelSwimlane from '@/views/schedule/components/PersonnelSwimlane.vue'
import TaskGantt from '@/views/schedule/components/TaskGantt.vue'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'
import UnscheduledTaskDrawer from '@/views/schedule/components/UnscheduledTaskDrawer.vue'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  targetKind: { type: String, default: 'all' },
  initialMode: { type: String, default: 'swimlane' },
  initialScale: { type: String, default: 'week' },
  initialGroupBy: { type: String, default: 'assignee' },
  initialWindowStart: { type: String, default: '' },
  initialWindowEnd: { type: String, default: '' },
  editableAllowed: Boolean
})

const emit = defineEmits(['query-change'])
const store = useScheduleStore()
const detailVisible = ref(false)
const unscheduledVisible = ref(false)
const accessNotice = ref('')
const windowStart = ref(props.initialWindowStart || monthWindow().windowStart)
const windowEnd = ref(props.initialWindowEnd || monthWindow().windowEnd)
const selectedTask = computed(() => store.tasks.find(task => task.taskId === store.selectedTaskId) || null)
const errorState = computed(() => store.error ? scheduleErrorState(store.error) : null)
const effectiveQuery = computed(() => ({
  windowStart: store.loadedWindow?.windowStart || windowStart.value,
  windowEnd: store.loadedWindow?.windowEnd || windowEnd.value,
  targetKind: store.targetKind,
  groupBy: store.groupBy,
  ...store.filters
}))

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatBusinessTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function monthWindow(now = new Date()) {
  const start = new Date(now.getFullYear(), now.getMonth(), 1)
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  return { windowStart: formatBusinessTime(start), windowEnd: formatBusinessTime(end) }
}

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
  store.setScale(scale)
  publishQuery()
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
    setWindow(monthWindow())
    return
  }
  const start = new Date(windowStart.value)
  const end = new Date(windowEnd.value)
  const duration = end.getTime() - start.getTime()
  setWindow({
    windowStart: formatBusinessTime(new Date(start.getTime() + duration * direction)),
    windowEnd: formatBusinessTime(new Date(end.getTime() + duration * direction))
  })
}

function setFilters(filters) {
  store.setFilters(filters)
  load()
}

function toggleEdit(enabled) {
  accessNotice.value = ''
  if (enabled && !props.editableAllowed) {
    store.setEditMode(false)
    accessNotice.value = '没有调整排期权限；当前仍可只读查看项目计划。'
    return
  }
  store.setEditMode(enabled)
}

function openTask({ taskId }) {
  store.selectedTaskId = taskId
  detailVisible.value = true
}

function requestRangeChange(payload) {
  const task = store.tasks.find(item => item.taskId === payload.taskId)
  if (task) openTask({ taskId: task.taskId })
}

function handleRejected(payload) {
  accessNotice.value = payload.reason === 'assignee-change'
    ? '跨泳道拖动不会改变负责人；请使用现有改派流程。'
    : '该任务当前不可调整排期。'
}

function refresh() {
  store.invalidateQuery()
  load()
}

onMounted(() => {
  store.setProject(props.projectId)
  store.setMode(props.initialMode)
  store.setScale(props.initialScale)
  store.setGrouping(props.initialGroupBy)
  store.setTargetKind(props.targetKind)
  load()
})

watch(() => props.projectId, projectId => {
  store.setProject(projectId)
  load()
})

watch(() => props.editableAllowed, allowed => {
  if (!allowed) store.setEditMode(false)
})

onBeforeUnmount(() => store.dispose())
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
      @update:mode="setMode"
      @update:scale="setScale"
      @update:group-by="setGroupBy"
      @window-change="setWindow"
      @window-shift="shiftWindow"
      @filters-change="setFilters"
      @refresh="refresh"
      @edit-toggle="toggleEdit"
      @open-unscheduled="unscheduledVisible = true"
    />

    <el-alert
      v-if="accessNotice"
      type="warning"
      :closable="false"
      show-icon
      :title="accessNotice"
    />
    <div v-else class="schedule-board__mode-hint">
      <el-icon><Warning /></el-icon>
      <span>{{ store.editMode ? '排期编辑已开启；拖动只生成草稿，确认原因后才会保存。' : '默认只读；当前排期为实色条，首版基线为细线，红框表示同一负责人重叠。' }}</span>
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
    <el-empty v-else-if="!store.tasks.length" :image-size="72" description="当前时间窗口没有已排期任务">
      <p>可调整日期、筛选条件，或打开未排期任务池安排时间。</p>
    </el-empty>
    <div v-else class="schedule-board__viewport" :class="{ 'is-loading': store.loading }">
      <PersonnelSwimlane
        v-if="store.mode === 'swimlane'"
        :rows="store.tasks"
        :window-start="windowStart"
        :window-end="windowEnd"
        :scale="store.scale"
        :editable="store.editMode && editableAllowed"
        @task-click="openTask"
        @range-change-request="requestRangeChange"
      />
      <TaskGantt
        v-else
        :rows="store.tasks"
        :scale="store.scale"
        :editable="store.editMode && editableAllowed"
        @task-click="openTask"
        @range-change-request="requestRangeChange"
        @change-rejected="handleRejected"
      />
    </div>
    <p v-if="store.total > store.pageSize" class="schedule-board__limit">当前仅加载前 {{ store.pageSize }} 项；请缩小时间窗口或增加筛选后继续查看。</p>

    <ScheduleTaskDrawer
      v-model:visible="detailVisible"
      :task="selectedTask"
      :can-edit="Boolean(selectedTask?.allowedActions?.includes('schedule') && store.editMode && editableAllowed)"
    />
    <UnscheduledTaskDrawer
      v-model:visible="unscheduledVisible"
      :project-id="projectId"
      :query="effectiveQuery"
      @edit-task="task => { store.selectedTaskId = task.taskId; detailVisible = true }"
    />
  </section>
</template>

<style scoped>
.schedule-board { display: grid; gap: 14px; min-width: 0; }
.schedule-board__mode-hint { display: flex; gap: 8px; align-items: center; color: var(--sg-text-muted); font-size: 11px; }
.schedule-board__viewport { min-height: 460px; overflow: auto; border-radius: var(--sg-radius-md); }
.schedule-board__viewport.is-loading { opacity: .62; pointer-events: none; }
.schedule-board__skeleton { min-height: 420px; padding: 22px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.schedule-board__limit { margin: 0; color: var(--el-color-warning); font-size: 11px; text-align: right; }
</style>
