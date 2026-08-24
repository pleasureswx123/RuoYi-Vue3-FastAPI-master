<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Right, Search } from '@element-plus/icons-vue'

import { getMineTaskPage } from '@/api/shot-grid/tasks'
import { getMineReviewListPage, getRecentMineVersions } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import { reviewModeMeta } from '@/views/review/reviewPresentation'
import {
  taskAssigneeLabel,
  taskDueState,
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta,
  taskVersionStatusMeta
} from '@/views/task/taskPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const tasks = ref([])
const total = ref(0)
const loading = ref(false)
const errorState = ref(null)
const pendingReviews = ref([])
const pendingReviewTotal = ref(0)
const reviewActivityError = ref(false)
const recentSubmissions = ref([])
const recentSubmissionTotal = ref(0)
const recentActivityError = ref(false)
const activityLoading = ref(false)
const taskFilterForm = ref(null)
const query = reactive({
  keyword: '',
  taskKind: '',
  taskStatus: '',
  priority: '',
  dueDateRange: [],
  pageNum: 1,
  pageSize: 20,
  orderByColumn: 'updateTime',
  isAsc: 'descending',
  orderValue: 'updateTime:descending'
})
const taskFilterRules = {
  dueDateRange: [{
    validator: (_rule, value, callback) => {
      const [dueDateFrom, dueDateTo] = Array.isArray(value) ? value : []
      if (dueDateFrom && dueDateTo && dueDateFrom > dueDateTo) {
        callback(new Error('截止日期起点不能晚于终点。'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}
let controller = null
let loadGeneration = 0
let activityController = null
let activityGeneration = 0
let disposed = false

const displayName = computed(() => sessionStore.user?.userName || sessionStore.user?.nickName || '制作成员')
const hasPermission = permission => (
  sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes(permission)
)
const canReviewQueue = computed(() => (
  hasPermission('shotgrid:reviewList:list') && hasPermission('shotgrid:version:review')
))
const canViewRecentSubmissions = computed(() => hasPermission('shotgrid:version:list'))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const pageSummary = computed(() => ({
  inProgress: tasks.value.filter(task => task.taskStatus === 'in_progress').length,
  pendingReview: tasks.value.filter(task => task.taskStatus === 'pending_review').length,
  revision: tasks.value.filter(task => task.taskStatus === 'revision').length,
  overdue: tasks.value.filter(task => task.taskStatus !== 'completed' && taskDueState(task.dueDate).overdue).length
}))

function getDueDateBounds() {
  const [dueDateFrom, dueDateTo] = Array.isArray(query.dueDateRange) ? query.dueDateRange : []
  return { dueDateFrom: dueDateFrom || '', dueDateTo: dueDateTo || '' }
}

function buildParams() {
  const { dueDateFrom, dueDateTo } = getDueDateBounds()
  return {
    keyword: query.keyword.trim() || undefined,
    taskKind: query.taskKind || undefined,
    taskStatus: query.taskStatus || undefined,
    priority: query.priority || undefined,
    dueDateFrom: dueDateFrom || undefined,
    dueDateTo: dueDateTo || undefined,
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    orderByColumn: query.orderByColumn,
    isAsc: query.isAsc
  }
}

async function loadTasks() {
  const generation = ++loadGeneration
  controller?.abort()
  controller = null
  loading.value = false
  let isValid = true
  if (taskFilterForm.value) {
    await taskFilterForm.value.validate(valid => {
      isValid = valid
    })
  }
  if (!isValid || disposed || generation !== loadGeneration) return
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  errorState.value = null
  const isCurrent = () => (
    !disposed &&
    controller === requestController &&
    generation === loadGeneration &&
    !requestController.signal.aborted
  )
  try {
    const response = await getMineTaskPage(buildParams(), { signal: requestController.signal })
    if (!isCurrent()) return
    tasks.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && isCurrent()) {
      tasks.value = []
      total.value = 0
      errorState.value = taskErrorState(error, '我的任务加载失败')
    }
  } finally {
    if (controller === requestController && generation === loadGeneration) loading.value = false
  }
}

async function loadActivity() {
  const generation = ++activityGeneration
  activityController?.abort()
  if (!canReviewQueue.value && !canViewRecentSubmissions.value) {
    pendingReviews.value = []
    pendingReviewTotal.value = 0
    reviewActivityError.value = false
    recentSubmissions.value = []
    recentSubmissionTotal.value = 0
    recentActivityError.value = false
    activityLoading.value = false
    return
  }
  const requestController = new AbortController()
  activityController = requestController
  activityLoading.value = true
  const isCurrent = () => (
    !disposed &&
    activityController === requestController &&
    generation === activityGeneration &&
    !requestController.signal.aborted
  )
  try {
    const [reviewResult, versionResult] = await Promise.allSettled([
      canReviewQueue.value
        ? getMineReviewListPage(
            { pageNum: 1, pageSize: 6, orderByColumn: 'createTime', isAsc: 'descending' },
            { signal: requestController.signal }
          )
        : Promise.resolve({ rows: [], total: 0 }),
      canViewRecentSubmissions.value
        ? getRecentMineVersions(
            { pageNum: 1, pageSize: 6, orderByColumn: 'submittedTime', isAsc: 'descending' },
            { signal: requestController.signal }
          )
        : Promise.resolve({ rows: [], total: 0 })
    ])
    if (!isCurrent()) return
    pendingReviews.value = reviewResult.status === 'fulfilled' ? reviewResult.value?.rows || [] : []
    reviewActivityError.value = canReviewQueue.value && reviewResult.status === 'rejected'
    pendingReviewTotal.value = reviewResult.status === 'fulfilled'
      ? Number(reviewResult.value?.total ?? pendingReviews.value.length)
      : 0
    recentSubmissions.value = versionResult.status === 'fulfilled' ? versionResult.value?.rows || [] : []
    recentActivityError.value = canViewRecentSubmissions.value && versionResult.status === 'rejected'
    recentSubmissionTotal.value = versionResult.status === 'fulfilled'
      ? Number(versionResult.value?.total ?? recentSubmissions.value.length)
      : 0
  } finally {
    if (activityController === requestController && generation === activityGeneration) {
      activityController = null
      activityLoading.value = false
    }
  }
}

function submitFilters() {
  query.pageNum = 1
  loadTasks()
}

function applyOrder() {
  const [column, direction] = query.orderValue.split(':')
  query.orderByColumn = column
  query.isAsc = direction
  submitFilters()
}

function resetFilters() {
  taskFilterForm.value?.resetFields()
  Object.assign(query, {
    pageNum: 1,
    pageSize: 20,
    orderByColumn: 'updateTime',
    isAsc: 'descending',
    orderValue: 'updateTime:descending'
  })
  loadTasks()
}

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum || loading.value) return
  query.pageNum = page
  loadTasks()
}

function openTask(task) {
  router.push(`/tasks/${task.taskId}`)
}

onMounted(() => { loadTasks(); loadActivity() })
onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  activityGeneration += 1
  controller?.abort()
  activityController?.abort()
})
</script>

<template>
  <section class="sg-page workbench-page">
    <div class="workbench-hero">
      <div class="workbench-hero__content">
        <p class="sg-eyebrow">PRODUCTION DESK</p>
        <h2>你好，{{ displayName }}</h2>
        <p>集中查看跨项目制作任务，跟进版本提交与审核进度。</p>
      </div>
      <el-tag class="workbench-hero__tag" type="info" size="small" effect="plain" round>{{ total }} 项我的任务</el-tag>
    </div>

    <section v-if="canReviewQueue" class="activity-section review-queue" aria-labelledby="review-queue-title" :aria-busy="activityLoading">
      <el-card class="activity-card activity-card--compact" shadow="never">
        <template #header>
          <header>
            <div><p class="sg-eyebrow">REVIEW QUEUE</p><h3 id="review-queue-title">待我审核</h3></div>
            <div class="activity-card__actions">
              <el-tag type="warning" size="small" effect="plain" round>{{ pendingReviewTotal }} 项</el-tag>
              <el-button v-if="reviewActivityError" link type="primary" @click="loadActivity">重新加载</el-button>
              <el-button link type="primary" @click="router.push('/reviews')">查看全部</el-button>
            </div>
          </header>
        </template>
        <el-skeleton v-if="activityLoading" animated :rows="3" />
        <el-alert v-else-if="reviewActivityError" title="待审核内容加载失败，请稍后重试" type="error" show-icon :closable="false" />
        <div v-else-if="pendingReviews.length" class="activity-list">
          <el-button v-for="item in pendingReviews" :key="item.reviewListId" class="activity-entry" text @click="router.push(`/reviews/${item.reviewListId}`)"><span class="activity-entry__content"><strong>{{ item.reviewListName }}</strong><small>{{ item.projectCode }} · {{ item.reviewMode === 'manual_batch' ? `${item.versionCount} 个版本` : item.versionNumber }}</small><el-tag :type="tagTypeFromTone(reviewModeMeta(item.reviewMode).tone)" size="small" effect="plain" round>{{ reviewModeMeta(item.reviewMode).label }}</el-tag></span><el-icon><Right /></el-icon></el-button>
        </div>
        <el-alert v-else title="当前没有待审核内容" type="success" show-icon :closable="false" />
      </el-card>
    </section>

    <section class="task-workbench" aria-labelledby="my-task-title">
      <header class="workbench-section-heading">
        <div>
          <p class="sg-eyebrow">MY TASKS</p>
          <h3 id="my-task-title">我的制作任务</h3>
          <p>统一查看镜头视频与资产图片任务，及时掌握制作、审核和修订进度。</p>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadTasks">刷新</el-button>
      </header>

      <div class="task-stats" aria-label="当前分页任务摘要">
        <el-card shadow="never"><span>待修订</span><strong>{{ pageSummary.revision }}</strong><small>当前页</small></el-card>
        <el-card shadow="never" :class="{ 'is-alert': pageSummary.overdue > 0 }"><span>已逾期</span><strong>{{ pageSummary.overdue }}</strong><small>当前页未完成</small></el-card>
        <el-card shadow="never"><span>制作中</span><strong>{{ pageSummary.inProgress }}</strong><small>当前页</small></el-card>
        <el-card shadow="never"><span>待审核</span><strong>{{ pageSummary.pendingReview }}</strong><small>当前页</small></el-card>
      </div>

      <el-form ref="taskFilterForm" :model="query" :rules="taskFilterRules" class="task-filters" size="large" label-position="top" aria-label="我的任务筛选">
        <el-form-item class="task-filter-item task-filter-item--search" label="搜索" prop="keyword">
          <el-input v-model="query.keyword" class="sg-input" :prefix-icon="Search" maxlength="200" clearable placeholder="任务、项目、镜头或资产" aria-label="搜索任务" />
        </el-form-item>
        <el-form-item class="task-filter-item" label="任务类型" prop="taskKind">
          <el-select v-model="query.taskKind" class="sg-select" placeholder="全部类型" aria-label="按任务类型筛选" @change="submitFilters"><el-option label="全部类型" value="" /><el-option label="镜头视频" value="shot_video" /><el-option label="资产图片" value="asset_image" /></el-select>
        </el-form-item>
        <el-form-item class="task-filter-item" label="任务状态" prop="taskStatus">
          <el-select v-model="query.taskStatus" class="sg-select" placeholder="全部状态" aria-label="按任务状态筛选" @change="submitFilters"><el-option label="全部状态" value="" /><el-option label="未开始" value="not_started" /><el-option label="目录准备中" value="preparing" /><el-option label="制作中" value="in_progress" /><el-option label="待审核" value="pending_review" /><el-option label="待修订" value="revision" /><el-option label="已完成" value="completed" /></el-select>
        </el-form-item>
        <el-form-item class="task-filter-item" label="优先级" prop="priority">
          <el-select v-model="query.priority" class="sg-select" placeholder="全部优先级" aria-label="按优先级筛选" @change="submitFilters"><el-option label="全部优先级" value="" /><el-option label="紧急" value="urgent" /><el-option label="高" value="high" /><el-option label="普通" value="normal" /><el-option label="低" value="low" /></el-select>
        </el-form-item>
        <el-form-item class="task-filter-item task-filter-item--date-range" label="截止日期" prop="dueDateRange">
          <el-date-picker
            v-model="query.dueDateRange"
            class="sg-input"
            type="daterange"
            unlink-panels
            value-format="YYYY-MM-DD"
            format="YYYY/MM/DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            aria-label="截止日期范围"
            @change="submitFilters"
          />
        </el-form-item>
        <el-form-item class="task-filter-item" label="排序" prop="orderValue">
          <el-select v-model="query.orderValue" class="sg-select" aria-label="任务排序" @change="applyOrder"><el-option label="最近更新" value="updateTime:descending" /><el-option label="截止日期由近到远" value="dueDate:ascending" /><el-option label="优先级由高到低" value="priority:ascending" /><el-option label="最近创建" value="createTime:descending" /></el-select>
        </el-form-item>
        <el-form-item class="task-filter-actions"><el-button type="primary" :loading="loading" @click="submitFilters">查询</el-button><el-button :disabled="loading" @click="resetFilters">重置</el-button></el-form-item>
      </el-form>

      <ProjectStatePanel
        v-if="errorState"
        compact
        :title="errorState.title"
        :message="errorState.message"
        :retryable="errorState.retryable"
        @retry="loadTasks"
      />
      <el-card v-else-if="loading && !tasks.length" class="task-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="5" /></el-card>
      <el-empty v-else-if="!tasks.length" class="task-empty" :description="total ? '当前页没有任务' : '当前筛选暂无任务'"><p>任务由项目管理人在镜头或资产制作分项中分配。</p></el-empty>
      <div v-else class="task-list" :class="{ 'is-refreshing': loading }">
        <el-button v-for="item in tasks" :key="item.taskId" class="task-row" text @click="openTask(item)">
          <el-tag class="task-kind-tag" :type="tagTypeFromTone(taskKindMeta(item.taskKind).tone)" size="small"
                  effect="plain" round>{{ taskKindMeta(item.taskKind).shortLabel }}
          </el-tag>
          <span class="task-row__main">
            <span class="task-row__heading"><strong>{{ item.taskName }}</strong><el-tag
                :type="tagTypeFromTone(taskStatusMeta(item.taskStatus).tone)" size="small" effect="dark"
                round>{{ taskStatusMeta(item.taskStatus).label }}</el-tag></span>
            <small>{{ item.project.projectCode }} · {{ item.project.projectName }} / {{
                item.target.targetName
              }}</small>
            <span>{{ item.requirements || '暂无额外制作要求' }}</span>
          </span>
          <span class="task-row__meta"><span>{{ taskAssigneeLabel(item.assignee) }}</span><span class="task-row__due"><el-tag
              :type="tagTypeFromTone(taskDueState(item.dueDate).tone)" size="small" effect="light"
              round>{{ taskDueState(item.dueDate).label }}</el-tag></span></span>
          <span class="task-row__version"><strong>{{
              item.latestVersion?.versionNumber || '—'
            }}</strong><small>{{ item.versionCount }} 个版本</small></span>
          <el-tag class="task-priority-tag" :type="tagTypeFromTone(taskPriorityMeta(item.priority).tone)" size="small"
                  effect="plain" round>{{ taskPriorityMeta(item.priority).label }}
          </el-tag>
          <el-icon class="task-row__arrow">
            <Right/>
          </el-icon>
        </el-button>
      </div>

      <el-pagination v-if="total" class="task-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="loading" aria-label="任务分页" @current-change="changePage" />
    </section>

    <section v-if="canViewRecentSubmissions" class="activity-section recent-submissions" aria-labelledby="recent-submissions-title" :aria-busy="activityLoading">
      <el-card class="activity-card activity-card--compact" shadow="never">
        <template #header>
          <header>
            <div><p class="sg-eyebrow">RECENT DELIVERY</p><h3 id="recent-submissions-title">最近提交</h3></div>
            <div class="activity-card__actions">
              <el-tag type="info" size="small" effect="plain" round>{{ recentSubmissionTotal }} 项</el-tag>
              <el-button v-if="recentActivityError" link type="primary" @click="loadActivity">重新加载</el-button>
            </div>
          </header>
        </template>
        <el-skeleton v-if="activityLoading" animated :rows="3" />
        <el-alert v-else-if="recentActivityError" title="最近提交加载失败，请稍后重试" type="error" show-icon :closable="false" />
        <div v-else-if="recentSubmissions.length" class="activity-list">
          <el-button v-for="item in recentSubmissions" :key="item.versionId" class="activity-entry" text @click="router.push(`/versions/${item.versionId}`)"><span class="activity-entry__content"><strong>{{ item.versionNumber }} · {{ item.changelog }}</strong><el-tag :type="tagTypeFromTone(taskVersionStatusMeta(item.versionStatus).tone)" size="small" effect="plain" round>{{ taskVersionStatusMeta(item.versionStatus).label }}</el-tag></span><el-icon><Right /></el-icon></el-button>
        </div>
        <el-alert v-else title="最近还没有提交版本" type="info" show-icon :closable="false" />
      </el-card>
    </section>

  </section>
</template>

<style scoped lang="scss">
.workbench-page {
  display: grid;
  gap: 20px;
}

.workbench-hero {
  position: relative;
  display: flex;
  min-height: 112px;
  align-items: center;
  justify-content: space-between;
  padding: 22px clamp(22px, 3vw, 34px);
  overflow: hidden;
  background: var(--sg-workbench-hero-bg);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-lg);
  box-shadow: var(--sg-shadow);
}

.workbench-hero::after {
  position: absolute;
  top: -98px;
  right: -18px;
  width: 230px;
  height: 230px;
  content: '';
  border: 1px solid var(--sg-workbench-hero-ring);
  border-radius: 50%;
}

.workbench-hero__content {
  position: relative;
  z-index: 1;
  min-width: 0;
  max-width: 760px;
}

.workbench-hero h2 {
  margin: 0;
  font-size: clamp(26px, 3vw, 36px);
  font-weight: 600;
  letter-spacing: -.045em;
}

.workbench-hero p:not(.sg-eyebrow) {
  max-width: 680px;
  margin: 8px 0 0;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.workbench-hero__tag {
  position: relative;
  z-index: 1;
}

.task-workbench {
  display: grid;
  gap: 14px;
}

.workbench-section-heading {
  display: flex;
  gap: 20px;
  align-items: flex-end;
  justify-content: space-between;
}

.workbench-section-heading h3 {
  margin: 0;
  font-size: 19px;
}

.workbench-section-heading p:not(.sg-eyebrow) {
  margin: 7px 0 0;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.task-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.task-stats span,
.task-stats small {
  color: var(--sg-text-muted);
  font-size: 10px;
}

.task-stats strong {
  grid-row: 1 / 3;
  grid-column: 2;
  font-size: 21px;
}

.task-stats:deep(.el-card) {
  background: var(--sg-surface);
  border-color: var(--sg-border);
}

.task-stats:deep(.el-card.is-alert) {
  border-color: rgba(255, 107, 107, .28);
}

.task-stats:deep(.el-card__body) {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 12px;
  padding: 10px 14px;
}

.task-filters {
  display: grid;
  grid-template-columns: 2fr repeat(6, minmax(120px, 1fr)) auto;
  gap: 10px;
  align-items: end;
  padding: 16px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
}

.task-filters:deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 0;
}

.task-filters:deep(.el-form-item__label) {
  display: flex;
  height: auto;
  padding-bottom: 6px;
  color: var(--sg-text-muted);
  font-size: 10px;
  line-height: 1;
}

.task-filter-item--date-range {
  grid-column: span 2;
}

.task-filter-item:deep(.el-form-item__content),
.task-filter-item:deep(.el-input),
.task-filter-item:deep(.el-select),
.task-filter-item:deep(.el-date-editor) {
  width: 100%;
  min-width: 0;
}

.task-filter-item:deep(.el-range-editor.sg-input) {
  background: var(--sg-surface-soft);
  border-radius: 10px;
  box-shadow: 0 0 0 1px var(--sg-border-strong) inset;
}

.task-filter-item:deep(.el-range-editor.sg-input:hover) {
  box-shadow: 0 0 0 1px rgba(255, 182, 87, .46) inset;
}

.task-filter-item:deep(.el-range-editor.sg-input.is-active) {
  box-shadow: 0 0 0 1px var(--sg-accent) inset;
}

.task-filter-item:deep(.el-input__inner) {
  height: auto;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.task-filter-item:deep(.el-form-item__error) {
  padding-top: 4px;
  white-space: nowrap;
}

.task-filter-actions:deep(.el-form-item__content) {
  flex-wrap: nowrap;
  justify-content: flex-end;
}

.task-loading.el-card {
  display: block;
  padding: 0;
}

.task-loading:deep(.el-card__body) {
  width: 100%;
  box-sizing: border-box;
  padding: 24px;
}

.task-empty.el-empty {
  min-height: 140px;
  padding: 24px;
  background: var(--sg-surface);
  border: 1px dashed var(--sg-border-strong);
  border-radius: var(--sg-radius-md);
}

.task-empty p {
  max-width: 620px;
  margin: 0;
  color: var(--sg-text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.task-list {
  display: grid;
  overflow: hidden;
  background: var(--sg-border);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
  gap: 1px;
}

.task-list.is-refreshing {
  pointer-events: none;
  opacity: .58;
}

.task-row {
  display: grid;
  min-height: 88px;
  grid-template-columns: 48px minmax(240px, 2fr) minmax(150px, 1fr) 80px auto auto;
  gap: 14px;
  align-items: center;
  padding: 16px 18px;
  color: var(--sg-text);
  text-align: left;
  cursor: pointer;
  background: var(--sg-surface);
  border: 0;
  margin-left: 0;
}

.task-row:hover {
  background: var(--sg-surface-raised);
}

:deep(.activity-entry > span),
:deep(.task-row > span) {
  display: contents;
}

.task-kind-tag,
.task-row__due {
  justify-self: start;
}

.task-row__main,
.task-row__meta,
.task-row__version {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.task-row__heading {
  display: flex;
  gap: 8px;
  align-items: center;
}

.task-row__heading strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row__main > small,
.task-row__main > span:not(.task-row__heading),
.task-row__meta,
.task-row__version small {
  overflow: hidden;
  color: var(--sg-text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row__meta > span {
  color: var(--sg-text-secondary);
  font-size: 11px;
}

.task-row__meta .el-tag {
  justify-self: start;
}

.task-row__version strong {
  color: var(--sg-accent);
}

.task-row__arrow {
  color: var(--sg-text-muted);
}

.task-pagination {
  display: flex;
  justify-content: center;
}

.activity-section {
  min-width: 0;
}

.activity-card.el-card {
  background: var(--sg-surface);
  border-color: var(--sg-border);
}

.activity-card header {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.activity-card h3 {
  margin: 3px 0 0;
  font-size: 16px;
}

.activity-card__actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.activity-card--compact:deep(.el-card__header) {
  padding: 14px 16px 8px;
  border-bottom: 0;
}

.activity-card--compact:deep(.el-card__body) {
  display: grid;
  gap: 10px;
  padding: 0 16px 14px;
}

.activity-card--compact:deep(.el-alert) {
  min-height: 42px;
}

.activity-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.activity-entry.el-button {
  display: flex;
  width: 100%;
  height: auto;
  min-width: 0;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 0;
  padding: 10px 12px;
  color: var(--sg-text);
  text-align: left;
  white-space: normal;
  background: var(--sg-surface-soft);
  border: 1px solid var(--sg-border);
  border-radius: 9px;
}

.activity-entry.el-button:hover,
.activity-entry.el-button:focus-visible {
  background: var(--sg-surface-raised);
  border-color: var(--sg-border-strong);
}

.activity-entry__content {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 5px;
}

.activity-entry__content strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-entry__content small {
  overflow: hidden;
  color: var(--sg-text-muted);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-entry__content .el-tag {
  justify-self: start;
}

.activity-section:deep(.el-skeleton) {
  grid-column: 1 / -1;
}

@media (max-width: 1400px) {
  .task-filters {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .task-filter-item--search {
    grid-column: span 2;
  }

  .task-filter-actions:deep(.el-form-item__content) {
    justify-content: flex-start;
  }

  .task-row {
    grid-template-columns: 48px minmax(240px, 2fr) minmax(140px, 1fr) 70px auto;
  }

  .task-row__arrow {
    display: none;
  }
}

@media (max-width: 1000px) {
  .task-stats,
  .activity-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .task-row {
    grid-template-columns: 44px minmax(0, 1fr) auto;
  }

  .task-row__meta,
  .task-row__version {
    display: none;
  }
}

@media (max-width: 680px) {
  .workbench-page {
    gap: 16px;
  }

  .workbench-hero {
    min-height: 96px;
    padding: 18px;
  }

  .workbench-hero p:not(.sg-eyebrow) {
    margin-top: 6px;
  }

  .workbench-hero__tag {
    display: none;
  }

  .workbench-section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .task-filters,
  .activity-list {
    grid-template-columns: 1fr;
  }

  .task-filter-item--search,
  .task-filter-item--date-range {
    grid-column: auto;
  }

  .task-filter-actions {
    width: 100%;
  }

  .task-row {
    grid-template-columns: 38px minmax(0, 1fr);
  }

  .task-row > .task-priority-tag {
    display: none;
  }

  .task-row__heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .activity-card__actions {
    gap: 6px;
  }
}
</style>
