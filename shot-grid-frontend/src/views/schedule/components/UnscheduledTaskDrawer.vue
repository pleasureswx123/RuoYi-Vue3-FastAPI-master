<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElCard, ElDrawer } from 'element-plus'
import { getUnscheduledScheduleTasks } from '@/api/shot-grid/schedules'
import { scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { taskStatusMeta } from '@/views/task/taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({
  visible: Boolean,
  inline: Boolean,
  editableAllowed: { type: Boolean, default: false },
  projectId: { type: [Number, String], required: true },
  query: { type: Object, required: true }
})
const emit = defineEmits(['update:visible', 'edit-task', 'open-task', 'rows-change'])
const rows = ref([])
watch(rows, value => emit('rows-change', value), { flush: 'sync' })
const total = ref(0)
const loading = ref(false)
const error = ref(false)
const page = ref(0)
const collapsed = ref([])
let controller
let generation = 0
let failedAppend = false
const groups = computed(() => {
  const result = new Map()
  for (const row of rows.value) {
    const key = String(row.assignee?.userId || 'unassigned')
    if (!result.has(key)) result.set(key, { key, name: row.assignee?.userName || '未分配', rows: [] })
    result.get(key).rows.push(row)
  }
  return [...result.values()]
})
const expanded = computed({
  get: () => groups.value.map(group => group.key).filter(key => !collapsed.value.includes(key)),
  set: keys => { collapsed.value = groups.value.map(group => group.key).filter(key => !keys.includes(key)) }
})
const containerProps = computed(() => props.inline
  ? { shadow: 'never' }
  : { modelValue: props.visible, title: '未设周期的任务', direction: 'rtl', size: 'min(760px, 100vw)', appendToBody: true, destroyOnClose: true })

async function loadRows(append = false) {
  controller?.abort()
  const requestGeneration = ++generation
  loading.value = false
  error.value = false
  if (!append) { rows.value = []; total.value = 0; page.value = 0 }
  if (!props.visible) return
  const request = new AbortController()
  controller = request
  const nextPage = append ? page.value + 1 : 1
  loading.value = true
  failedAppend = append
  try {
    const response = await getUnscheduledScheduleTasks(props.projectId,
      { ...props.query, pageNum: nextPage, pageSize: 100 }, { signal: request.signal })
    if (request.signal.aborted || requestGeneration !== generation) return
    const result = response?.data ?? response
    if (!Array.isArray(result?.rows) || result.rows.some(row => Number(row.projectId) !== Number(props.projectId))) throw new Error('任务范围无效')
    const merged = new Map((append ? rows.value : []).map(row => [row.taskId, row]))
    for (const row of result.rows) merged.set(row.taskId, row)
    if (append && result.rows.length === 0 && merged.size < Number(result.total)) throw new Error('任务列表已变化，请刷新')
    rows.value = [...merged.values()]
    total.value = Number(result.total || 0)
    page.value = nextPage
  } catch (caught) {
    if (!request.signal.aborted && requestGeneration === generation && caught?.code !== 'ERR_CANCELED') error.value = true
  } finally {
    if (requestGeneration === generation) loading.value = false
  }
}
watch(() => [props.visible, props.projectId, JSON.stringify(props.query)], () => loadRows(), { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
defineExpose({ refresh: () => loadRows() })
</script>

<template>
  <component :is="inline ? ElCard : ElDrawer" class="unscheduled-tasks" v-bind="containerProps" @update:model-value="value => emit('update:visible', value)">
    <template v-if="inline" #header><strong>未设周期的任务</strong><el-text size="small"> {{ loading ? '加载中…' : `${total} 项` }}</el-text></template>
    <p class="unscheduled-tasks__hint">已分配的任务会显示在这里；系统目录就绪后即可提交，无需先排期或确认开工。未设周期任务不参与到期、重叠或延后筛选。</p>
    <el-text v-if="query.productionFrom || query.productionTo" type="info" size="small">当前制作周期筛选仍生效；清除周期筛选可查看没有日期的任务。</el-text>
    <el-alert v-if="error" type="error" :closable="false" title="未设周期任务加载失败"><el-button link type="primary" :loading="loading" @click="loadRows(failedAppend)">重试</el-button></el-alert>
    <el-skeleton v-if="loading && !rows.length" animated :rows="2" />
    <el-text v-else-if="!error && !rows.length" type="info" size="small">当前筛选没有未设周期的任务</el-text>
    <div v-loading="loading && rows.length > 0" class="unscheduled-tasks__list">
      <el-collapse v-model="expanded">
        <el-collapse-item v-for="group in groups" :key="group.key" :name="group.key" :title="`${group.name} · ${group.rows.length} 项`">
          <el-table :data="group.rows" row-key="taskId" size="small" empty-text="暂无任务">
            <el-table-column label="任务" min-width="220"><template #default="{ row }"><el-button link type="primary" :disabled="loading" @click="emit('open-task', row)">{{ scheduleTaskLabel(row) }}</el-button></template></el-table-column>
            <el-table-column label="状态" width="125"><template #default="{ row }"><el-tag size="small" :type="tagTypeFromTone(taskStatusMeta(row).tone)">{{ taskStatusMeta(row).label }}</el-tag></template></el-table-column>
            <el-table-column v-if="editableAllowed" label="计划时间" width="110"><template #default="{ row }"><el-button v-if="row.allowedActions?.includes('schedule')" size="small" :disabled="loading" @click="emit('edit-task', row)">设置周期</el-button><el-text v-else size="small">—</el-text></template></el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>
    <div v-if="rows.length < total" class="unscheduled-tasks__more"><el-text size="small">已加载 {{ rows.length }} / {{ total }} 项</el-text><el-button size="small" :loading="loading" @click="loadRows(true)">加载更多</el-button></div>
  </component>
</template>

<style scoped>
.unscheduled-tasks :deep(.el-card__header) { padding: 10px 14px; }
.unscheduled-tasks :deep(.el-card__body) { padding: 10px 14px; }
.unscheduled-tasks__hint { margin: 0 0 8px; color: var(--sg-text-muted); font-size: 12px; }
.unscheduled-tasks__list { max-height: 250px; overflow: auto; }
.unscheduled-tasks__more { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 8px; }
</style>
