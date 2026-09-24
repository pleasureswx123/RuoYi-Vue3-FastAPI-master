<script setup>
import { computed, onBeforeUnmount, onMounted, provide, reactive, ref } from 'vue'
import { ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { detailNavigationKey } from '@/composables/useDetailNavigation'
import { getRecentMineVersions } from '@/api/shot-grid/reviews'
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
const filters = reactive({ projectKeyword: '', taskKeyword: '', versionStatus: '', dates: [] })
const page = reactive({ pageNum: 1, pageSize: 10 })
const applied = ref({})
const rows = ref([])
const total = ref(0)
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
    const response = await getRecentMineVersions({ ...applied.value, ...page, groupByTask: true, orderByColumn: 'shotNo', isAsc: 'ascending' }, { signal: request.signal })
    if (disposed || request.signal.aborted || current !== generation) return
    rows.value = response.rows || []
    total.value = Number(response.total || 0)
    if (page.pageNum > 1 && !rows.value.length && total.value > 0) {
      page.pageNum = Math.ceil(total.value / page.pageSize)
      await load()
    }
  } catch (failure) {
    if (!disposed && !request.signal.aborted && current === generation && failure?.code !== 'ERR_CANCELED') {
      error.value = true
      rows.value = []
      total.value = 0
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
async function search() {
  if (loading.value) return
  if (form.value && !await form.value.validate().catch(() => false)) return
  applied.value = {
    projectKeyword: filters.projectKeyword.trim() || undefined,
    taskKeyword: filters.taskKeyword.trim() || undefined,
    versionStatus: filters.versionStatus || undefined,
    submittedFrom: filters.dates?.[0] || undefined,
    submittedTo: filters.dates?.[1] || undefined
  }
  page.pageNum = 1
  await load()
}
function reset() {
  form.value?.resetFields()
  applied.value = {}
  page.pageNum = 1
  void load()
}
function changeSize() {
  page.pageNum = 1
  void load()
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; generation += 1; controller?.abort() })
</script>

<template>
  <section class="activity-section recent-submissions" aria-labelledby="my-submissions-title">
    <el-card shadow="never">
      <template #header>
        <header class="submission-heading"><div><p class="sg-eyebrow">MY SUBMISSIONS</p><h3 id="my-submissions-title">我的提交</h3><p class="submission-help">按任务查看本人提交记录，展开可查看各版本；任务按集、场次、镜头号排序。</p></div><el-button :loading="loading" @click="load">刷新</el-button></header>
      </template>
      <el-form ref="form" :model="filters" :rules="rules" class="submission-filters" label-position="top" aria-label="我的提交筛选">
        <el-form-item label="项目" prop="projectKeyword"><el-input v-model="filters.projectKeyword" placeholder="项目名称或编号" clearable maxlength="200" @keyup.enter="search" /></el-form-item>
        <el-form-item label="任务" prop="taskKeyword"><el-input v-model="filters.taskKeyword" placeholder="任务名称" clearable maxlength="240" @keyup.enter="search" /></el-form-item>
        <el-form-item label="审核状态" prop="versionStatus"><el-select v-model="filters.versionStatus" placeholder="全部状态" clearable><el-option label="待审核" value="pending_review" /><el-option label="已退回" value="rejected" /><el-option label="最终版本" value="final" /></el-select></el-form-item>
        <el-form-item label="提交时间" prop="dates"><el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至" /></el-form-item>
        <el-form-item class="submission-filter-actions"><el-button type="primary" :loading="loading" @click="search">查询</el-button><el-button :disabled="loading" @click="reset">重置</el-button></el-form-item>
      </el-form>
      <el-alert v-if="error" title="提交记录加载失败，请重试" type="error" :closable="false" show-icon><el-button link type="primary" @click="load">重新加载</el-button></el-alert>
      <el-table v-else v-loading="loading" :data="submissionTree" row-key="rowKey" :tree-props="{ children: 'children' }" empty-text="没有符合条件的提交记录" aria-label="我的提交记录">
        <el-table-column label="任务 / 提交版本" min-width="280"><template #default="{ row }"><strong>{{ row.isTask ? (row.taskName || `任务 #${row.taskId}`) : row.versionNumber }}</strong><el-tag v-if="row.isTask" size="small" type="info" style="margin-left:8px">{{ row.children.length }} 个匹配版本</el-tag><small v-if="!row.isTask && row.changelog" class="submission-secondary">{{ row.changelog }}</small></template></el-table-column>
        <el-table-column label="项目" min-width="140"><template #default="{ row }">{{ row.projectName || `项目 #${row.projectId}` }}<small class="submission-secondary">{{ row.projectCode }}</small></template></el-table-column>
        <el-table-column prop="versionNumber" label="版本 / 筛选内最新" width="135" />
        <el-table-column prop="candidateCount" label="文件数" width="80" />
        <el-table-column label="提交时间" width="175"><template #default="{ row }">{{ formatReviewDateTime(row.submittedTime) }}</template></el-table-column>
        <el-table-column label="审核状态" width="110"><template #default="{ row }"><el-tag :type="tagTypeFromTone(taskVersionStatusMeta(row.versionStatus).tone)" size="small" effect="plain" round>{{ taskVersionStatusMeta(row.versionStatus).label }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="220" fixed="right" class-name="submission-actions"><template #default="{ row }"><el-button v-if="allowed('shotgrid:version:query')" link type="primary" @click="openDetail(`/versions/${row.versionId}`)">{{ row.isTask ? '查看最新版本' : '查看版本' }}</el-button><el-button v-if="allowed('shotgrid:reviewList:query') && row.autoReviewListId" link type="primary" @click="openDetail(`/reviews/${row.autoReviewListId}`)">查看审核</el-button></template></el-table-column>
      </el-table>
      <p class="submission-help">共 {{ total }} 个匹配任务，按任务分页。</p>
      <el-pagination v-model:current-page="page.pageNum" v-model:page-size="page.pageSize" class="submission-pagination" :total="total" :page-sizes="[10, 20, 50]" :disabled="loading" layout="total, sizes, prev, pager, next" background @current-change="load" @size-change="changeSize" />
    </el-card>
    <RelatedDetailDrawer ref="detailDrawer" />
  </section>
</template>

<style scoped>
.submission-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.submission-heading h3 { margin: 4px 0; }
.submission-help { margin: 6px 0 0; color: var(--sg-text-muted); font-size: 12px; }
.submission-filters { display: grid; grid-template-columns: 1fr 1fr 140px minmax(240px, 1.4fr) auto; gap: 12px; align-items: end; }
.submission-filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
.submission-secondary { display: block; margin-top: 4px; color: var(--sg-text-muted); overflow-wrap: anywhere; }
.submission-pagination { margin-top: 16px; justify-content: flex-end; }
@media (max-width: 1100px) { .submission-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .submission-filters { grid-template-columns: minmax(0, 1fr); } .submission-pagination { justify-content: flex-start; overflow-x: auto; } }
:deep(.submission-actions .cell) { white-space: nowrap; }
</style>
