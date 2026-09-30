<script setup>
import { computed, onBeforeUnmount, onMounted, provide, reactive, ref } from 'vue'
import { ElTable, ElTableColumn, ElRadioGroup, ElRadioButton, ElEmpty } from 'element-plus'
import { RefreshLeft, Refresh, Search } from '@element-plus/icons-vue'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { detailNavigationKey } from '@/composables/useDetailNavigation'
import { getRecentMineVersions, getMineSubmissionProjects } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { formatReviewDateTime } from '@/views/review/reviewPresentation'
import { taskVersionStatusMeta } from '@/views/task/taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const detailDrawer = ref(null)
const openDetail = target => Boolean(detailDrawer.value?.open(target))
provide(detailNavigationKey, openDetail)
const session = useSessionStore()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const form = ref(null)
const filters = reactive({ projectId: '', taskKeyword: '', versionStatus: '', dates: [] })
const projectOptions = ref([])
const projectsLoading = ref(false)
const projectsError = ref(false)
let projectController
let filterGeneration = 0
const statusOptions = [
  { value: '', label: '全部' },
  { value: 'rejected', label: '已退回' },
  { value: 'pending_review', label: '待审核' },
  { value: 'final', label: '最终版本' }
]
const dateShortcuts = [
  { text: '今天', days: 1 }, { text: '近7天', days: 7 }, { text: '近30天', days: 30 }
].map(item => ({ text: item.text, value: () => {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - item.days + 1)
  start.setHours(0, 0, 0, 0)
  return [start, end]
} }))
async function loadProjects() {
  projectController?.abort()
  const request = new AbortController()
  projectController = request
  projectsLoading.value = true
  projectsError.value = false
  try {
    const response = await getMineSubmissionProjects({ signal: request.signal })
    if (!disposed && !request.signal.aborted) projectOptions.value = response.data || []
  } catch (failure) {
    if (!disposed && !request.signal.aborted && failure?.code !== 'ERR_CANCELED') projectsError.value = true
  } finally {
    if (!disposed && projectController === request) projectsLoading.value = false
  }
}
const page = reactive({ pageNum: 1, pageSize: 10 })
const applied = ref({})
const rows = ref([])
const total = ref(0)
const expandedTaskKeys = ref([])
function handleExpand(row, expanded) {
  if (!row.isTask) return
  expandedTaskKeys.value = expanded
    ? [...new Set([...expandedTaskKeys.value, row.rowKey])]
    : expandedTaskKeys.value.filter(key => key !== row.rowKey)
}
function reviewActionLabel(row) {
  return { rejected: '查看修改意见', pending_review: '查看审核进度', final: '查看审核结果' }[row.versionStatus] || '查看审核结果'
}
function reviewActionType(row) {
  return { rejected: 'danger', pending_review: 'warning', final: 'success' }[row.versionStatus] || 'info'
}
const submissionTree = computed(() => {
  const groups = new Map()
  for (const row of rows.value) {
    const key = `${row.projectId}:task:${row.taskId}`
    if (!groups.has(key)) groups.set(key, { rowKey: key, isTask: true, children: [] })
    groups.get(key).children.push({ ...row, rowKey: `${key}:version:${row.versionId}` })
  }
  return [...groups.values()].map(group => {
    group.children.sort((a, b) => Number(b.versionNo) - Number(a.versionNo))
    return { ...group.children[0], ...group }
  })
})
const loading = ref(false)
const error = ref(false)
const rules = { dates: [{ validator: (_rule, value, callback) => {
  callback(value?.[0] && value?.[1] && value[0] > value[1] ? new Error('提交日期起点不能晚于终点') : undefined)
}, trigger: 'change' }] }
let controller
let generation = 0
let disposed = false

async function load() {
  const current = ++generation
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = false
  try {
    const response = await getRecentMineVersions({ ...applied.value, ...page, groupByTask: true, orderByColumn: 'submittedTime', isAsc: 'descending' }, { signal: request.signal })
    if (disposed || request.signal.aborted || current !== generation) return
    rows.value = response.rows || []
    const visibleTaskKeys = new Set(rows.value.map(row => `${row.projectId}:task:${row.taskId}`))
    expandedTaskKeys.value = expandedTaskKeys.value.filter(key => visibleTaskKeys.has(key))
    total.value = Number(response.total || 0)
    if (page.pageNum > 1 && !rows.value.length && total.value > 0) {
      page.pageNum = Math.ceil(total.value / page.pageSize)
      await load()
    }
  } catch (failure) {
    if (!disposed && !request.signal.aborted && current === generation && failure?.code !== 'ERR_CANCELED') {
      error.value = true
      rows.value = []
      expandedTaskKeys.value = []
      total.value = 0
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
async function search() {
  const current = ++filterGeneration
  controller?.abort()
  generation += 1
  loading.value = true
  const valid = !form.value || await form.value.validate().catch(() => false)
  if (disposed || current !== filterGeneration) return
  if (!valid) { loading.value = false; return }
  applied.value = {
    projectId: filters.projectId || undefined,
    taskKeyword: filters.taskKeyword.trim() || undefined,
    versionStatus: filters.versionStatus || undefined,
    submittedFrom: filters.dates?.[0] || undefined,
    submittedTo: filters.dates?.[1] || undefined
  }
  page.pageNum = 1
  await load()
}
function reset() {
  filterGeneration += 1
  form.value?.resetFields()
  filters.versionStatus = ''
  applied.value = {}
  page.pageNum = 1
  void load()
}
function changeSize() {
  page.pageNum = 1
  void load()
}
onMounted(() => { void load(); void loadProjects() })
onBeforeUnmount(() => { disposed = true; generation += 1; filterGeneration += 1; controller?.abort(); projectController?.abort() })
</script>

<template>
  <section class="activity-section recent-submissions" aria-label="提交记录">
    <header class="submission-heading"><div><p class="submission-help">按任务查看本人提交记录，展开可查看各版本；按最近提交排序，保留转交前本人的历史提交。</p></div><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button></header>
    <el-radio-group v-model="filters.versionStatus" class="submission-status" aria-label="按提交版本审核状态筛选" @change="search">
      <el-radio-button v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio-button>
    </el-radio-group>
    <el-form ref="form" :model="filters" :rules="rules" class="submission-filters" size="large" label-position="top" aria-label="提交记录筛选">
      <el-form-item label="项目" prop="projectId"><el-select v-model="filters.projectId" class="sg-select" filterable clearable placeholder="全部项目" :loading="projectsLoading" :disabled="projectsError" @change="search"><el-option v-for="project in projectOptions" :key="project.projectId" :value="project.projectId" :label="`${project.projectName} · ${project.projectCode}${project.projectStatus === 'archived' ? '（已归档）' : ''}`" /></el-select></el-form-item>
      <el-form-item label="任务" prop="taskKeyword"><el-input class="sg-input" :prefix-icon="Search" v-model="filters.taskKeyword" placeholder="搜索任务名称" clearable maxlength="240" @keyup.enter="search" /></el-form-item>

      <el-form-item label="提交时间" prop="dates"><el-date-picker class="sg-input" v-model="filters.dates" :shortcuts="dateShortcuts" @change="search" unlink-panels format="YYYY/MM/DD" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至" /></el-form-item>
      <el-form-item class="submission-filter-actions"><el-button type="primary" :loading="loading" @click="search">搜索</el-button><el-button :icon="RefreshLeft" :disabled="loading" @click="reset">重置</el-button></el-form-item>
    </el-form>
    <el-alert v-if="projectsError" title="项目选项加载失败，仍可按状态、任务和时间筛选" type="warning" :closable="false" show-icon><el-button link type="primary" @click="loadProjects">重试项目选项</el-button></el-alert>
    <p v-if="applied.versionStatus" class="submission-help" role="status">仅显示{{ statusOptions.find(option => option.value === applied.versionStatus)?.label }}的提交版本；历史审核结果不代表任务当前状态。</p>
    <el-alert v-if="error" title="提交记录加载失败，请重试" type="error" :closable="false" show-icon><el-button link type="primary" @click="load">重新加载</el-button></el-alert>
    <el-empty v-else-if="!loading && !rows.length" class="submission-empty" description="没有符合条件的提交记录"><el-button :icon="RefreshLeft" @click="reset">重置</el-button></el-empty>
    <el-table v-else class="submission-table" v-loading="loading" :data="submissionTree" row-key="rowKey" :expand-row-keys="expandedTaskKeys" @expand-change="handleExpand" :tree-props="{ children: 'children' }" empty-text="没有符合条件的提交记录" aria-label="提交记录">
      <el-table-column label="任务 / 提交版本" min-width="280"><template #default="{ row }"><strong v-if="row.isTask">{{ row.taskName || `任务 #${row.taskId}` }}</strong><el-button v-else-if="row.versionId && allowed('shotgrid:version:query')" link type="primary" :aria-label="`${row.versionNumber} 查看作品`" @click="openDetail(`/versions/${row.versionId}`)">{{ row.versionNumber }}</el-button><strong v-else>{{ row.versionNumber }}</strong><el-tag v-if="row.isTask" size="small" type="info" style="margin-left:8px">{{ row.children.length }} 个匹配版本</el-tag></template></el-table-column>
      <el-table-column label="项目" width="120" show-overflow-tooltip><template #default="{ row }">{{ row.projectName || `项目 #${row.projectId}` }}<small class="submission-secondary">{{ row.projectCode }}</small></template></el-table-column>
      <el-table-column label="版本 / 筛选内最新" width="175"><template #default="{ row }"><el-button v-if="row.versionId && allowed('shotgrid:version:query')" link type="primary" :aria-label="`${row.versionNumber} 查看作品`" @click="openDetail(`/versions/${row.versionId}`)">{{ row.versionNumber }}</el-button><span v-else>{{ row.versionNumber }}</span></template></el-table-column>
      <el-table-column prop="candidateCount" label="文件数" width="80" />
      <el-table-column label="提交时间" width="175"><template #default="{ row }">{{ formatReviewDateTime(row.submittedTime) }}</template></el-table-column>
      <el-table-column label="审核状态" width="110"><template #default="{ row }"><el-tag :type="tagTypeFromTone(taskVersionStatusMeta(row.versionStatus).tone)" size="small" effect="plain" round>{{ taskVersionStatusMeta(row.versionStatus).label }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="270" fixed="right" class-name="submission-actions">
        <template #default="{ row }">
          <template v-if="!row.isTask || !expandedTaskKeys.includes(row.rowKey)">
            <el-button v-if="allowed('shotgrid:reviewList:query') && row.autoReviewListId" :type="reviewActionType(row)" size="small" :aria-label="`${row.versionNumber} ${reviewActionLabel(row)}`" @click="openDetail(`/reviews/${row.autoReviewListId}`)">{{ reviewActionLabel(row) }}</el-button>
            <el-button v-if="row.versionId && allowed('shotgrid:version:query')" :type="reviewActionType(row)" plain size="small" :aria-label="`${row.versionNumber} 查看作品`" @click="openDetail(`/versions/${row.versionId}`)">查看作品</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <p class="submission-help">共 {{ total }} 个匹配任务，按任务分页。</p>
    <el-pagination v-model:current-page="page.pageNum" v-model:page-size="page.pageSize" class="submission-pagination" :total="total" :page-sizes="[10, 20, 50]" :disabled="loading" layout="total, sizes, prev, pager, next" background @current-change="load" @size-change="changeSize" />
    <RelatedDetailDrawer ref="detailDrawer" />
  </section>
</template>

<style scoped>
.recent-submissions { display: grid; gap: 14px; min-width: 0; }
.submission-status { gap: 6px; }
.submission-status :deep(.el-radio-button__inner) { border: 1px solid var(--sg-border); border-radius: 6px; box-shadow: none; }
.submission-empty { border: 1px dashed var(--sg-border-strong); border-radius: var(--sg-radius-md); background: var(--sg-surface); }
.submission-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.submission-help { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.submission-filters {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(200px, 1.3fr) minmax(260px, 1.4fr) auto;
  gap: 10px;
  align-items: end;
  padding: 16px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
}
.submission-filters :deep(.el-form-item) { min-width: 0; margin-bottom: 0; }
.submission-filters :deep(.el-form-item__label) { height: auto; padding-bottom: 6px; color: var(--sg-text-muted); font-size: 10px; line-height: 1; }
.submission-filters :deep(.el-form-item__content),
.submission-filters :deep(.el-input),
.submission-filters :deep(.el-select),
.submission-filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
.submission-filters :deep(.el-input__inner) { height: auto; padding: 0; background: transparent; border: 0; border-radius: 0; }
.submission-filters :deep(.el-range-editor.sg-input) { background: var(--sg-surface-soft); border-radius: 10px; box-shadow: 0 0 0 1px var(--sg-border-strong) inset; }
.submission-filters :deep(.el-range-editor.sg-input:hover) { box-shadow: 0 0 0 1px rgba(255, 182, 87, .46) inset; }
.submission-filters :deep(.el-range-editor.sg-input.is-active) { box-shadow: 0 0 0 1px var(--sg-accent) inset; }
.submission-filter-actions :deep(.el-form-item__content) { flex-wrap: nowrap; justify-content: flex-end; }
.submission-table { border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.submission-secondary { display: block; margin-top: 5px; color: var(--sg-text-muted); font-size: 12px; overflow-wrap: anywhere; }
.submission-pagination { justify-content: center; }
:deep(.submission-actions .cell) { white-space: nowrap; }
@media (max-width: 1100px) {
  .submission-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .submission-filter-actions :deep(.el-form-item__content) { justify-content: flex-start; }
}
@media (max-width: 680px) {
  .submission-heading { align-items: flex-start; flex-direction: column; }
  .submission-filters { grid-template-columns: minmax(0, 1fr); }
  .submission-pagination { flex-wrap: wrap; gap: 8px; }
}
</style>
