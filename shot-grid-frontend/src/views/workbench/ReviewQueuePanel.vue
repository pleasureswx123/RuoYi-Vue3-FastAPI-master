<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { ElAlert, ElButton, ElDatePicker, ElEmpty, ElForm, ElFormItem, ElInput, ElOption, ElPagination, ElRadioGroup, ElRadioButton, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { RefreshLeft, Refresh, Search } from '@element-plus/icons-vue'
import { getMineReviewListPage, getMineReviewProjects, getMineReviewProducers } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { formatReviewDateTime } from '@/views/review/reviewPresentation'

const detailDrawer = ref(null)
const projects = ref([])
const projectsLoading = ref(false)
const projectsError = ref(false)
const producers = ref([])
const producersLoading = ref(false)
const producersError = ref(false)
let producersController
let projectsController
const typeOptions = [{ value: '', label: '全部内容' }, { value: 'shot_video', label: '镜头视频' }, { value: 'asset_image', label: '资产图片' }]
const dateShortcuts = [1, 7, 30].map(days => ({ text: days === 1 ? '今天' : `近${days}天`, value: () => {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - days + 1)
  start.setHours(0, 0, 0, 0)
  return [start, end]
} }))
const session = useSessionStore()
const canOpen = session.permissions.includes('*:*:*') || session.permissions.includes('shotgrid:reviewList:query')
const canViewWork = session.permissions.includes('*:*:*') || session.permissions.includes('shotgrid:version:query')
const form = ref(null)
const filters = reactive({ projectId: '', keyword: '', taskKind: '', reviewMode: '', orderValue: 'submittedTime:ascending', submittedBy: '', dates: [] })
const rules = {
  keyword: [{ max: 200, message: '搜索内容不能超过 200 个字符', trigger: 'blur' }],
  dates: [{ validator: (_rule, value, callback) => {
    const [start, end] = value || []
    callback(start && end && start > end ? new Error('提交时间起点不能晚于终点') : undefined)
  }, trigger: 'change' }]
}
const page = reactive({ pageNum: 1, pageSize: 10 })
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const failed = ref(false)
let applied = {}
let controller
let generation = 0
let disposed = false
let searchGeneration = 0

async function load() {
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  failed.value = false
  try {
    const response = await getMineReviewListPage({ orderByColumn: 'submittedTime', isAsc: 'ascending', ...applied, ...page }, { signal: controller.signal })
    if (disposed || current !== generation) return
    total.value = Number(response.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / page.pageSize))
    if (page.pageNum > lastPage) {
      page.pageNum = lastPage
      await load()
      return
    }
    rows.value = response.rows || []
  } catch (error) {
    if (disposed || current !== generation || error?.code === 'ERR_CANCELED') return
    failed.value = true
    rows.value = []
    total.value = 0
  } finally {
    if (!disposed && current === generation) loading.value = false
  }
}

async function search() {
  const current = ++searchGeneration
  controller?.abort()
  generation += 1
  loading.value = true
  const valid = await form.value.validate().catch(() => false)
  if (disposed || current !== searchGeneration) return
  if (!valid) { loading.value = false; return }
  const [orderByColumn, isAsc] = filters.orderValue.split(':')
  const [submittedFrom, submittedTo] = filters.dates || []
  applied = {
    projectId: filters.projectId || undefined, keyword: filters.keyword.trim() || undefined,
    taskKind: filters.taskKind || undefined, reviewMode: filters.reviewMode || undefined,
    submittedBy: filters.submittedBy || undefined,
    submittedFrom: submittedFrom || undefined, submittedTo: submittedTo || undefined,
    orderByColumn, isAsc
  }
  page.pageNum = 1
  await load()
}

function reset() {
  searchGeneration += 1
  form.value.resetFields()
  filters.taskKind = ''
  loadProducers()
  applied = {}
  page.pageNum = 1
  load()
}
function changePage(value) { page.pageNum = value; load() }
function changeSize(value) { page.pageSize = value; page.pageNum = 1; load() }
async function loadProjects() {
  projectsController?.abort()
  const request = new AbortController()
  projectsController = request
  projectsLoading.value = true
  projectsError.value = false
  try {
    const response = await getMineReviewProjects({ signal: request.signal })
    if (!disposed && projectsController === request) projects.value = response.data || []
  } catch (error) {
    if (!disposed && projectsController === request && error?.code !== 'ERR_CANCELED') projectsError.value = true
  } finally {
    if (!disposed && projectsController === request) projectsLoading.value = false
  }
}
async function loadProducers() {
  producersController?.abort()
  const request = new AbortController()
  producersController = request
  producersLoading.value = true
  producersError.value = false
  producers.value = []
  try {
    const response = await getMineReviewProducers({ projectId: filters.projectId || undefined }, { signal: request.signal })
    if (!disposed && producersController === request) producers.value = response.data || []
  } catch (error) {
    if (!disposed && producersController === request && error?.code !== 'ERR_CANCELED') producersError.value = true
  } finally {
    if (!disposed && producersController === request) producersLoading.value = false
  }
}
function changeProject() {
  filters.submittedBy = ''
  loadProducers()
  search()
}
function refreshAfterReview() { load(); loadProjects(); loadProducers() }
onMounted(() => { load(); loadProjects(); loadProducers() })
onBeforeUnmount(() => { disposed = true; generation += 1; searchGeneration += 1; controller?.abort(); projectsController?.abort(); producersController?.abort() })
</script>

<template>
  <section class="review-queue" aria-label="待审核" :aria-busy="loading">
    <header class="review-heading">
      <el-radio-group v-model="filters.taskKind" class="review-types" aria-label="审核内容类型" @change="search"><el-radio-button v-for="option in typeOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio-button></el-radio-group>
      <p class="review-help">查看我管理范围内待处理的审核内容，打开抽屉即可审核。</p>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </header>
    <el-alert v-if="projectsError" title="项目选项加载失败，仍可使用其他筛选条件" type="warning" show-icon :closable="false"><el-button link type="primary" @click="loadProjects">重试项目选项</el-button></el-alert>
    <el-form ref="form" :model="filters" :rules="rules" size="default" label-position="top" class="review-filters sg-filter-bar" aria-label="待审核筛选">
      <el-form-item class="review-field-project" label="项目" prop="projectId"><el-select v-model="filters.projectId" filterable clearable placeholder="全部项目" :loading="projectsLoading" :disabled="projectsError" @change="changeProject"><el-option v-for="project in projects" :key="project.projectId" :value="project.projectId" :label="`${project.projectName} · ${project.projectCode}`" /></el-select></el-form-item>
      <el-form-item class="review-field-search" label="审核内容" prop="keyword"><el-input v-model="filters.keyword" :prefix-icon="Search" placeholder="搜索镜头号、任务或审核单" clearable @clear="search" @keydown.enter.prevent="search" /></el-form-item>
      <el-form-item class="review-field-order" label="排序" prop="orderValue"><el-select v-model="filters.orderValue" @change="search"><el-option label="镜头顺序" value="shotNo:ascending" /><el-option label="等待最久" value="submittedTime:ascending" /><el-option label="最近提交" value="submittedTime:descending" /></el-select></el-form-item>


        <el-form-item class="review-field-mode" label="审核方式" prop="reviewMode"><template #label><el-tooltip content="单版本审核：提交后自动建单，由审核人审核；批量审核：管理人手动汇集多个版本集中审核。"><span>审核方式 ⓘ</span></el-tooltip></template><el-select v-model="filters.reviewMode" clearable placeholder="全部方式" @change="search"><el-option label="单版本审核" value="auto_single" /><el-option label="批量审核" value="manual_batch" /></el-select></el-form-item>
        <el-form-item class="review-field-producer" label="制作人" prop="submittedBy"><el-select v-model="filters.submittedBy" filterable clearable placeholder="全部制作人" :loading="producersLoading" :disabled="producersLoading || producersError" @change="search"><el-option v-for="producer in producers" :key="producer.userId" :value="producer.userId" :label="producer.nickName && producer.nickName !== producer.userName ? `${producer.userName} · ${producer.nickName}` : producer.userName" /></el-select></el-form-item>
        <el-form-item class="review-field-date" label="提交时间" prop="dates"><el-date-picker v-model="filters.dates" type="daterange" unlink-panels :shortcuts="dateShortcuts" format="YYYY/MM/DD" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至" @change="search" /></el-form-item>
      <el-form-item class="review-filter-actions"><el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button><el-button :icon="RefreshLeft" @click="reset">重置</el-button></el-form-item>
    </el-form>
    <p class="review-help">镜头顺序按项目、集、场、镜头排列，资产和批量单列于各项目镜头之后。批量单按所含版本匹配筛选，时间排序使用批量单创建时间。</p>
    <el-alert v-if="producersError" title="制作人选项加载失败，请重试" type="warning" show-icon :closable="false"><el-button link type="primary" @click="loadProducers">重试制作人选项</el-button></el-alert>
    <el-alert v-if="failed" title="待审核内容加载失败，请重试" type="error" show-icon :closable="false"><el-button link type="primary" @click="load">重新加载</el-button></el-alert>
    <el-empty v-else-if="!loading && !rows.length" class="review-empty" description="当前没有符合条件的待审核内容"><el-button :icon="RefreshLeft" @click="reset">重置</el-button></el-empty>
    <el-table v-else v-loading="loading" :data="rows" row-key="reviewListId" class="review-table" aria-label="待审核列表" empty-text="当前没有待审核内容">
      <el-table-column label="审核内容" min-width="270"><template #default="{ row }"><strong>{{ row.taskName || row.reviewListName }}</strong><div class="review-context"><el-tag v-if="row.taskKind" type="info" size="small" effect="plain">{{ row.taskKind === 'shot_video' ? '镜头视频' : '资产图片' }}</el-tag><el-tag v-if="row.reviewMode === 'auto_single' && row.versionNo" type="info" size="small" effect="plain">{{ row.versionNo === 1 ? '首版' : '后续版本' }}</el-tag><el-tag v-if="row.reviewMode === 'manual_batch'" type="info" size="small" effect="plain">批量审核</el-tag></div></template></el-table-column>
      <el-table-column label="项目" min-width="180"><template #default="{ row }">{{ row.projectName || row.projectCode }}<small class="review-secondary">{{ row.projectCode }}</small></template></el-table-column>
      <el-table-column label="版本 / 版本数" width="160"><template #default="{ row }">{{ row.reviewMode === 'manual_batch' ? `${row.versionCount} 个版本` : (row.versionNumber || '—') }}</template></el-table-column>
      <el-table-column label="制作人" min-width="110"><template #default="{ row }">{{ row.submittedByName || (row.reviewMode === 'manual_batch' ? '按版本查看' : '—') }}</template></el-table-column>
      <el-table-column label="提交时间" width="175"><template #default="{ row }">{{ formatReviewDateTime(row.submittedTime || row.createTime) }}<small v-if="row.reviewMode === 'manual_batch'" class="review-secondary">批量单创建时间</small></template></el-table-column>
      <el-table-column label="操作" width="225" fixed="right"><template #default="{ row }"><el-button v-if="canOpen && row.reviewListId" type="primary" size="small" @click="detailDrawer?.open(`/reviews/${row.reviewListId}`)">{{ row.reviewMode === 'manual_batch' ? '批量审核' : '进入审核' }}</el-button><el-button v-if="canViewWork && row.autoVersionId" type="primary" plain size="small" @click="detailDrawer?.open(`/versions/${row.autoVersionId}`)">查看作品</el-button><span v-if="!canOpen && !(canViewWork && row.autoVersionId)" class="review-help">无查看权限</span></template></el-table-column>
    </el-table>
    <el-pagination v-if="total" class="review-pagination" :current-page="page.pageNum" :page-size="page.pageSize" :page-sizes="[10, 20, 50]" :total="total" :disabled="loading" layout="total, sizes, prev, pager, next" background aria-label="待审核分页" @current-change="changePage" @update:page-size="changeSize" />
    <RelatedDetailDrawer ref="detailDrawer" @closed="refreshAfterReview" />
  </section>
</template>

<style scoped>
.review-queue { display: grid; gap: 14px; min-width: 0; }
.review-types { gap: 6px; }
.review-types :deep(.el-radio-button__inner) { border: 1px solid var(--sg-border); border-radius: 6px; box-shadow: none; }
.review-heading { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 20px; }
.review-heading > .review-help { min-width: 0; line-height: 1.5; }
.review-heading > .review-types { flex-wrap: nowrap; }
.review-help { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.review-filters { display: grid; grid-template-columns: minmax(100px, 1fr) minmax(130px, 1.4fr) minmax(110px, 1fr) minmax(100px, .9fr) minmax(100px, .9fr) minmax(240px, 1.6fr) auto; gap: 10px; align-items: end; padding: 16px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.review-filters :deep(.el-form-item) { min-width: 0; margin-bottom: 0; }
.review-filters :deep(.el-form-item__label) { height: auto; padding-bottom: 6px; color: var(--sg-text-muted); font-size: 10px; line-height: 1; }
.review-filters :deep(.el-form-item__content), .review-filters :deep(.el-input), .review-filters :deep(.el-select) { width: 100%; min-width: 0; }
.review-filters :deep(.el-input__inner) { height: auto; padding: 0; background: transparent; border: 0; border-radius: 0; }
.review-filter-actions :deep(.el-form-item__content) { flex-wrap: nowrap; justify-content: flex-end; }
.review-filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
.review-filters :deep(.el-range-editor.sg-input) { background: var(--sg-surface-soft); border-radius: 10px; box-shadow: 0 0 0 1px var(--sg-border-strong) inset; }
.review-context { display: flex; gap: 6px; margin-top: 5px; }
.review-table { border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.review-secondary { display: block; margin-top: 5px; color: var(--sg-text-muted); font-size: 12px; }
.review-empty { border: 1px dashed var(--sg-border-strong); border-radius: var(--sg-radius-md); background: var(--sg-surface); }
.review-pagination { justify-content: center; }
@media (max-width: 1250px) { .review-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .review-filters :deep(.el-form-item) { grid-column: auto; } .review-filter-actions :deep(.el-form-item__content) { justify-content: flex-start; } }
@media (max-width: 680px) { .review-heading { grid-template-columns: minmax(0, 1fr) auto; gap: 10px; } .review-heading > .review-help { grid-row: 2; grid-column: 1 / -1; } .review-heading > .el-button { grid-column: 2; grid-row: 1; } .review-heading > .review-types { flex-wrap: wrap; } .review-filters { grid-template-columns: minmax(0, 1fr); } .review-pagination { flex-wrap: wrap; gap: 8px; } }
</style>

<style scoped src="../../assets/styles/filter-toolbar.css"></style>
