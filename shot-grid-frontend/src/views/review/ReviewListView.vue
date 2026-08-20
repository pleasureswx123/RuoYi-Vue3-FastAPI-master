<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh, Search, Tickets } from '@element-plus/icons-vue'

import { getProjectPage } from '@/api/shot-grid/projects'
import { getReviewListPage } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import ManualReviewDialog from '@/views/review/components/ManualReviewDialog.vue'
import { taskVersionStatusMeta } from '@/views/task/taskPresentation'
import {
  formatReviewDateTime,
  mediaDerivationStatusMeta,
  reviewErrorState,
  reviewModeMeta,
  reviewStatusMeta
} from './reviewPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const selectedProjectId = ref('')
const reviews = ref([])
const total = ref(0)
const projectsLoading = ref(false)
const reviewsLoading = ref(false)
const projectsError = ref(null)
const reviewsError = ref(null)
const manualDialogVisible = ref(false)
const query = reactive({ reviewStatus: '', pageNum: 1, pageSize: 20 })
let projectsController = null
let reviewsController = null

const canViewAll = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:project:all'))
const canListReviews = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:reviewList:list'))
const canCreateManual = computed(() => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes('shotgrid:reviewList:add'))
const manualCandidates = computed(() => reviews.value.filter(item => item.reviewStatus === 'active' && item.reviewMode === 'auto_single' && item.versionStatus === 'pending_review'))
const reviewFilterModel = computed(() => ({ projectId: selectedProjectId.value, reviewStatus: query.reviewStatus }))

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
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: 'createTime',
      isAsc: 'descending'
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
      <div><p class="sg-eyebrow">REVIEWS</p><h2 class="sg-page-title">版本审核</h2><p class="sg-page-description">处理自动单版本审核单，意见与审核动作始终绑定不可覆盖的具体版本。</p></div>
      <div class="heading-actions"><el-button v-if="canCreateManual && selectedProjectId" type="primary" :icon="Plus" @click="manualDialogVisible = true">创建批量审核单</el-button><el-button :icon="Refresh" :loading="projectsLoading || reviewsLoading" @click="refreshAll">刷新</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form :model="reviewFilterModel" class="review-toolbar" size="large" label-position="top" aria-label="审核单筛选">
        <el-form-item label="当前项目" prop="projectId"><el-select v-model="selectedProjectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :loading="projectsLoading" :disabled="projectsLoading"><el-option v-for="project in projects" :key="project.projectId" :label="`${project.projectCode} · ${project.projectName}`" :value="String(project.projectId)" /></el-select></el-form-item>
        <el-form-item label="审核状态" prop="reviewStatus"><el-select v-model="query.reviewStatus" class="sg-select" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="草稿" value="draft" /><el-option label="待审核" value="active" /><el-option label="已完成" value="completed" /><el-option label="已归档" value="archived" /></el-select></el-form-item>
        <div class="review-toolbar__summary"><el-icon><Search /></el-icon><span>当前筛选 {{ total }} 条审核单</span></div>
      </el-form>

      <ProjectStatePanel v-if="reviewsError" :title="reviewsError.title" :message="reviewsError.message" :retryable="reviewsError.retryable" @retry="loadReviews" />
      <el-card v-else-if="reviewsLoading && !reviews.length" class="review-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="6" /></el-card>
      <section v-else-if="reviews.length" class="review-list" :class="{ 'is-refreshing': reviewsLoading }">
        <el-card v-for="item in reviews" :key="item.reviewListId" class="review-card" shadow="hover" role="link" tabindex="0" @click="router.push(`/reviews/${item.reviewListId}`)" @keydown.enter="router.push(`/reviews/${item.reviewListId}`)" @keydown.space.prevent="router.push(`/reviews/${item.reviewListId}`)">
          <span class="review-card__preview"><ProtectedThumbnail v-if="item.thumbnail" :thumbnail="item.thumbnail" :alt="`${item.reviewListName} 缩略图`" /><span v-else class="review-card__icon"><el-icon><Tickets /></el-icon></span></span>
          <div class="review-card__main"><div><strong>{{ item.reviewListName }}</strong><el-tag size="small" effect="plain" round :type="tagTypeFromTone(reviewModeMeta(item.reviewMode).tone)">{{ reviewModeMeta(item.reviewMode).label }}</el-tag><el-tag size="small" effect="plain" round :type="tagTypeFromTone(reviewStatusMeta(item.reviewStatus).tone)">{{ reviewStatusMeta(item.reviewStatus).label }}</el-tag><el-tag v-if="mediaDerivationStatusMeta(item.mediaDerivationStatus)" size="small" effect="plain" round :type="tagTypeFromTone(mediaDerivationStatusMeta(item.mediaDerivationStatus).tone)">{{ mediaDerivationStatusMeta(item.mediaDerivationStatus).label }}</el-tag></div><p>{{ item.description || (item.reviewMode === 'manual_batch' ? '人工集中审核单' : '单版本自动审核单') }}</p><small>{{ item.reviewMode === 'manual_batch' ? `${item.versionCount} 个版本` : `版本 ${item.versionNumber}` }} · 创建于 {{ formatReviewDateTime(item.createTime) }}</small></div>
          <div class="review-card__meta"><span>{{ item.taskId ? `任务 #${item.taskId}` : '集中审核' }}</span><strong v-if="item.reviewMode === 'manual_batch'">{{ item.versionCount }} 项</strong><el-tag v-else size="small" effect="light" round :type="tagTypeFromTone(taskVersionStatusMeta(item.versionStatus).tone)">{{ taskVersionStatusMeta(item.versionStatus).label }}</el-tag></div>
        </el-card>
      </section>
      <el-empty v-else class="review-empty" :description="selectedProjectId ? '当前筛选没有审核单' : '当前范围暂无项目'"><p>{{ selectedProjectId ? '版本提交成功后，系统会自动创建一张单版本审核单。' : '请先创建或加入项目。' }}</p></el-empty>

      <el-pagination v-if="total > query.pageSize" class="review-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="reviewsLoading" aria-label="审核单分页" @current-change="changePage" />
    </template>
    <ManualReviewDialog v-if="manualDialogVisible && selectedProjectId" v-model="manualDialogVisible" :project-id="selectedProjectId" :candidates="manualCandidates" @created="openCreatedManual" />
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
@media(max-width:760px){.review-card:deep(.el-card__body){grid-template-columns:auto 1fr}.review-card__meta{grid-column:2}}
</style>
