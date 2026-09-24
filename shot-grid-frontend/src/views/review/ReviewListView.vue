<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'

import { getProjectPage } from '@/api/shot-grid/projects'
import { getReviewListPage } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import ManualReviewDialog from '@/views/review/components/ManualReviewDialog.vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { taskVersionStatusMeta } from '@/views/task/taskPresentation'
import {
  formatReviewDateTime,
  reviewErrorState,
  reviewStatusMeta
} from './reviewPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const taskDrawer = ref(null)
const canQueryTask = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:task:query'))
const projects = ref([])
const selectedProjectId = ref('')
const reviews = ref([])
const total = ref(0)
const reviewTree = computed(() => {
  const groups = new Map()
  for (const item of reviews.value) {
    const isTask = item.reviewMode === 'auto_single' && item.taskId
    const key = `${selectedProjectId.value}:${isTask ? 'task' : 'manual'}:${isTask ? item.taskId : item.reviewListId}`
    if (!isTask) {
      groups.set(key, { ...item, rowKey: key, title: item.reviewListName })
      continue
    }
    if (!groups.has(key)) groups.set(key, { rowKey: key, isTask: true, title: item.taskName || `任务 #${item.taskId}`, children: [] })
    groups.get(key).children.push({ ...item, rowKey: `${key}:review:${item.reviewListId}`, title: item.versionNumber || item.reviewListName })
  }
  return [...groups.values()].map(group => {
    if (!group.isTask) return group
    group.children.sort((a, b) => Number(b.versionNo) - Number(a.versionNo))
    return { ...group.children[0], ...group }
  })
})
const projectsLoading = ref(false)
const reviewsLoading = ref(false)
const projectsError = ref(null)
const reviewsError = ref(null)
const manualDialogVisible = ref(false)
const reviewFilterFormRef = ref(null)
const query = reactive({ reviewStatus: '', pageNum: 1, pageSize: 20 })
let projectsController = null
let reviewsController = null

const canViewAll = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:project:all'))
const canListReviews = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:reviewList:list'))
const canCreateManual = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:reviewList:add'))
const manualCandidates = computed(() => reviews.value.filter(item => item.reviewStatus === 'active' && item.reviewMode === 'auto_single' && item.versionStatus === 'pending_review'))
const reviewFilterModel = computed(() => ({ projectId: selectedProjectId.value, reviewStatus: query.reviewStatus }))

function listStatusMeta(status) {
  return status === 'completed' ? { label: '已结束', tone: 'neutral' } : reviewStatusMeta(status)
}

function cardStatusMeta(item) {
  if (item.reviewMode === 'auto_single' && item.versionStatus === 'final') {
    return { label: '已通过', tone: 'success' }
  }
  return item.reviewMode === 'auto_single' && item.versionStatus
    ? taskVersionStatusMeta(item.versionStatus)
    : listStatusMeta(item.reviewStatus)
}

async function loadProjects() {
  projectsController?.abort()
  const controller = new AbortController()
  projectsController = controller
  projectsLoading.value = true
  projectsError.value = null
  try {
    const response = await getProjectPage({ pageNum: 1, pageSize: 100, scope: canViewAll.value ? 'all' : undefined }, { signal: controller.signal })
    if (projectsController !== controller) return
    projects.value = response.rows || []
    if (!projects.value.some(item => String(item.projectId) === selectedProjectId.value)) {
      selectedProjectId.value = projects.value[0] ? String(projects.value[0].projectId) : ''
    }
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') projectsError.value = reviewErrorState(error, '项目范围加载失败')
  } finally {
    if (projectsController === controller) projectsLoading.value = false
  }
}

async function loadReviews() {
  if (!canListReviews.value) {
    reviews.value = []
    total.value = 0
    reviewsError.value = reviewErrorState({ httpStatus: 403, message: '当前账号没有审核单列表权限' })
    return
  }
  if (!selectedProjectId.value) {
    reviews.value = []
    total.value = 0
    return
  }
  reviewsController?.abort()
  const controller = new AbortController()
  reviewsController = controller
  reviewsLoading.value = true
  reviewsError.value = null
  try {
    const response = await getReviewListPage(selectedProjectId.value, {
      reviewStatus: query.reviewStatus || undefined,
      groupByTask: true,
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: 'shotNo', isAsc: 'ascending'
    }, { signal: controller.signal })
    if (reviewsController !== controller) return
    reviews.value = response.rows || []
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') reviewsError.value = reviewErrorState(error, '审核单加载失败')
  } finally {
    if (reviewsController === controller) reviewsLoading.value = false
  }
}

async function refreshAll() {
  const previousProjectId = selectedProjectId.value
  await loadProjects()
  if (selectedProjectId.value === previousProjectId) await loadReviews()
}

function changePage(next) {
  query.pageNum = next
  loadReviews()
}

function openCreatedManual(detail) {
  router.push(`/reviews/${detail.reviewListId}`)
}

watch(selectedProjectId, () => {
  query.pageNum = 1
  loadReviews()
})
watch(() => query.reviewStatus, () => {
  query.pageNum = 1
  loadReviews()
})
onMounted(loadProjects)
onBeforeUnmount(() => {
  projectsController?.abort()
  reviewsController?.abort()
})
</script>

<template>
  <section class="sg-page review-page">
    <header class="sg-page-heading">
      <div><p class="sg-eyebrow">REVIEWS</p><h2 class="sg-page-title">版本审核</h2><p class="sg-page-description">按任务查看审核进度，展开任务可查看各版本审核记录。</p></div>
      <div class="heading-actions"><el-button v-if="canCreateManual && selectedProjectId" type="primary" :icon="Plus" @click="manualDialogVisible = true">创建批量审核单</el-button><el-button :icon="Refresh" :loading="projectsLoading || reviewsLoading" @click="refreshAll">刷新</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form ref="reviewFilterFormRef" :model="reviewFilterModel" class="review-toolbar" size="large" label-position="top" aria-label="审核单筛选">
        <el-form-item label="当前项目" prop="projectId"><el-select v-model="selectedProjectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :loading="projectsLoading" :disabled="projectsLoading"><el-option v-for="project in projects" :key="project.projectId" :label="`${project.projectCode} · ${project.projectName}`" :value="String(project.projectId)" /></el-select></el-form-item>
        <el-form-item label="审核单状态" prop="reviewStatus"><el-select v-model="query.reviewStatus" class="sg-select" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="草稿" value="draft" /><el-option label="待审核" value="active" /><el-option label="已结束" value="completed" /><el-option label="已归档" value="archived" /></el-select></el-form-item>
        <div class="review-toolbar__summary"><el-icon><Search /></el-icon><span>当前筛选 {{ total }} 个任务 / 批量单</span></div>
      </el-form>

      <ProjectStatePanel v-if="reviewsError" :title="reviewsError.title" :message="reviewsError.message" :retryable="reviewsError.retryable" @retry="loadReviews" />
      <el-card v-else-if="reviewsLoading && !reviews.length" class="review-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="6" /></el-card>
      <el-table v-else-if="reviews.length" :data="reviewTree" row-key="rowKey" :tree-props="{ children: 'children' }" class="review-tree" :aria-busy="reviewsLoading">
        <el-table-column label="任务 / 版本审核单" min-width="330">
          <template #default="{ row }">
            <strong>{{ row.title }}</strong>
            <el-tag v-if="row.isTask" size="small" type="info" class="review-count">{{ row.children.length }} 个匹配版本</el-tag>
            <el-tag v-else-if="row.reviewMode === 'manual_batch'" size="small" type="info">批量审核</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="预览" width="108">
          <template #default="{ row }"><ProtectedThumbnail v-if="row.thumbnail" class="review-tree-preview" :thumbnail="row.thumbnail" :alt="`${row.title} 缩略图`" /><span v-else>—</span></template>
        </el-table-column>
        <el-table-column label="审核状态" min-width="150">
          <template #default="{ row }"><el-tag :type="tagTypeFromTone(cardStatusMeta(row).tone)" size="small">{{ cardStatusMeta(row).label }}</el-tag><small v-if="row.isTask" class="review-tree-hint">{{ query.reviewStatus ? '筛选内最新' : '最新版本' }} {{ row.versionNumber }}</small></template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ formatReviewDateTime(row.createTime) }}</template></el-table-column>
        <el-table-column label="操作" width="145" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.isTask && canQueryTask" size="small" @click="taskDrawer?.open(`/tasks/${row.taskId}`)">查看任务</el-button>
            <el-button v-else-if="!row.isTask" size="small" :type="row.reviewStatus === 'active' ? 'primary' : 'default'" @click="router.push(`/reviews/${row.reviewListId}`)">{{ row.reviewStatus === 'active' ? '去审核' : '查看审核' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else class="review-empty" :description="selectedProjectId ? '当前筛选没有审核单' : '当前范围暂无项目'"><p>{{ selectedProjectId ? '版本提交成功后，系统会自动创建一张单版本审核单。' : '请先创建或加入项目。' }}</p></el-empty>

      <el-pagination v-if="total > query.pageSize" class="review-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="reviewsLoading" aria-label="任务审核分组分页" @current-change="changePage" />
    </template>
    <ManualReviewDialog v-if="manualDialogVisible && selectedProjectId" v-model="manualDialogVisible" :project-id="selectedProjectId" :candidates="manualCandidates" @created="openCreatedManual" />
    <RelatedDetailDrawer ref="taskDrawer" @closed="loadReviews" />
  </section>
</template>

<style scoped>
.heading-actions{display:flex;gap:10px}
  .review-page{display:grid;gap:18px}.review-toolbar{display:grid;grid-template-columns:minmax(260px,1fr) 180px auto;gap:12px;align-items:end;padding:16px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.review-toolbar label{display:grid;gap:6px}.review-toolbar label>span{color:var(--sg-text-muted);font-size:10px}.review-toolbar__summary{display:flex;height:var(--el-component-size-large);gap:8px;align-items:center;padding:0 13px;color:var(--sg-text-muted);font-size:11px;background:rgba(255,255,255,.025);border-radius:10px}.review-list{display:grid;gap:10px}.review-list.is-refreshing{opacity:.55;pointer-events:none}.review-card{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:15px;align-items:center;padding:17px 19px;color:var(--sg-text);text-align:left;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:.15s}.review-card:hover{border-color:rgba(255,182,87,.35);transform:translateY(-1px)}.review-card__icon{display:grid;width:42px;height:42px;color:var(--sg-accent);background:var(--sg-accent-soft);border-radius:11px;place-items:center}.review-card__main>div{display:flex;gap:9px;align-items:center}.review-card__main p{margin:6px 0;color:var(--sg-text-secondary);font-size:12px}.review-card__main small,.review-card__meta span{color:var(--sg-text-muted);font-size:10px}.review-card__meta{display:grid;gap:6px;text-align:right}.review-card__meta strong{color:var(--sg-accent);font-size:12px}.review-loading,.review-empty{display:grid;min-height:280px;padding:30px;color:var(--sg-text-muted);text-align:center;background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg);place-content:center}.review-empty>.el-icon{margin:auto;color:var(--sg-accent);font-size:36px}.review-empty h3,.review-empty p{margin:10px 0 0}.review-empty p{font-size:12px}.review-pagination{display:flex;gap:12px;align-items:center;justify-content:center;color:var(--sg-text-muted);font-size:11px}@media(max-width:760px){.review-toolbar{grid-template-columns:1fr}.review-card{grid-template-columns:auto 1fr}.review-card__meta{grid-column:2;text-align:left}}
  .review-card__preview{display:grid;width:112px;height:68px;overflow:hidden;background:var(--sg-accent-soft);border-radius:10px;place-items:center}.review-card__main>div{flex-wrap:wrap}
@media(max-width:760px){.review-card__preview{width:84px;height:56px}}
.review-toolbar:deep(.el-form-item){min-width:0;margin-bottom:0}
.review-toolbar:deep(.el-form-item__label){height:auto;padding-bottom:6px;color:var(--sg-text-muted);font-size:10px;line-height:1}
.review-toolbar:deep(.el-form-item__content),.review-toolbar:deep(.el-select){width:100%}
.review-loading.el-card{display:block;padding:0}
.review-loading:deep(.el-card__body){width:100%;box-sizing:border-box;padding:30px}
.review-card.el-card{display:block;padding:0;overflow:hidden;background:var(--sg-surface);border-color:var(--sg-border)}
.review-card:deep(.el-card__body){display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:15px;align-items:center;padding:17px 19px}
.review-empty.el-empty{padding:30px;background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg)}
.review-empty p{margin:0;color:var(--sg-text-muted);font-size:12px}
.review-pagination{justify-content:center}
.review-card__meta .review-card__explanation{max-width:260px;color:var(--sg-text-secondary);font-size:12px;line-height:1.6}
@media(max-width:760px){.review-card:deep(.el-card__body){grid-template-columns:auto 1fr}.review-card__meta{grid-column:2}}
.review-tree { width: 100%; }
.review-count { margin-left: 8px; }
.review-tree-hint { display: block; margin-top: 4px; color: var(--sg-text-muted); font-size: 11px; }
.review-tree-preview { display: block; width: 80px; height: 46px; overflow: hidden; border-radius: 6px; }
</style>
