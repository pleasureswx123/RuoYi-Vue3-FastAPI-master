<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Collection, Film, FolderOpened, Refresh, Right, Search, Tickets } from '@element-plus/icons-vue'

import { getMineTaskPage } from '@/api/shot-grid/tasks'
import { getMineReviewListPage, getRecentMineVersions } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import {
  taskAssigneeLabel,
  taskDueState,
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta
} from '@/views/task/taskPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const tasks = ref([])
const total = ref(0)
const loading = ref(false)
const errorState = ref(null)
const pendingReviews = ref([])
const recentSubmissions = ref([])
const activityLoading = ref(false)
const validationMessage = ref('')
const query = reactive({
  keyword: '',
  taskKind: '',
  taskStatus: '',
  priority: '',
  dueDateFrom: '',
  dueDateTo: '',
  pageNum: 1,
  pageSize: 20,
  orderByColumn: 'updateTime',
  isAsc: 'descending'
})
const orderValue = ref('updateTime:descending')
let controller = null
let loadGeneration = 0
let disposed = false

const moduleRegistry = Object.freeze({
  projects: { title: '项目', path: '/projects', icon: Collection, description: '管理项目资料与项目成员' },
  shots: { title: '镜头管理', path: '/shots', icon: Film, description: '进入镜头生产与分配视图' },
  assets: { title: '资产库管理', path: '/assets', icon: Box, description: '查看角色、场景与道具资产' },
  reviews: { title: '版本审核', path: '/reviews', icon: Tickets, description: '处理版本反馈与审核动作' },
  files: { title: '文件与 NAS', path: '/files', icon: FolderOpened, description: '查看业务文件和存储状态' }
})

const availableModules = computed(() => {
  const navigation = Array.isArray(sessionStore.navigation) ? sessionStore.navigation : []
  return navigation
    .map((item, index) => {
      if (!Object.hasOwn(moduleRegistry, item?.routeKey)) return null
      const module = moduleRegistry[item.routeKey]
      return { ...module, routeKey: item.routeKey, orderNum: Number(item.orderNum ?? index) }
    })
    .filter(Boolean)
    .sort((left, right) => left.orderNum - right.orderNum)
})

const displayName = computed(() => sessionStore.user?.nickName || sessionStore.user?.userName || '制作成员')
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const pageSummary = computed(() => ({
  inProgress: tasks.value.filter(task => task.taskStatus === 'in_progress').length,
  pendingReview: tasks.value.filter(task => task.taskStatus === 'pending_review').length,
  revision: tasks.value.filter(task => task.taskStatus === 'revision').length,
  overdue: tasks.value.filter(task => task.taskStatus !== 'completed' && taskDueState(task.dueDate).overdue).length
}))

function buildParams() {
  return {
    keyword: query.keyword.trim() || undefined,
    taskKind: query.taskKind || undefined,
    taskStatus: query.taskStatus || undefined,
    priority: query.priority || undefined,
    dueDateFrom: query.dueDateFrom || undefined,
    dueDateTo: query.dueDateTo || undefined,
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
  validationMessage.value = ''
  if (query.dueDateFrom && query.dueDateTo && query.dueDateFrom > query.dueDateTo) {
    validationMessage.value = '截止日期起点不能晚于终点。'
    loading.value = false
    return
  }
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
  activityLoading.value = true
  try {
    const [reviewResponse, versionResponse] = await Promise.all([
      getMineReviewListPage({ pageNum: 1, pageSize: 6, orderByColumn: 'createTime', isAsc: 'descending' }),
      getRecentMineVersions({ pageNum: 1, pageSize: 6, orderByColumn: 'submittedTime', isAsc: 'descending' })
    ])
    pendingReviews.value = reviewResponse.rows || []
    recentSubmissions.value = versionResponse.rows || []
  } catch {
    pendingReviews.value = []
    recentSubmissions.value = []
  } finally { activityLoading.value = false }
}

function submitFilters() {
  query.pageNum = 1
  loadTasks()
}

function applyOrder() {
  const [column, direction] = orderValue.value.split(':')
  query.orderByColumn = column
  query.isAsc = direction
  submitFilters()
}

function resetFilters() {
  Object.assign(query, {
    keyword: '',
    taskKind: '',
    taskStatus: '',
    priority: '',
    dueDateFrom: '',
    dueDateTo: '',
    pageNum: 1,
    pageSize: 20,
    orderByColumn: 'updateTime',
    isAsc: 'descending'
  })
  orderValue.value = 'updateTime:descending'
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
  controller?.abort()
})
</script>

<template>
  <section class="sg-page workbench-page">
    <div class="workbench-hero">
      <div>
        <p class="sg-eyebrow">PRODUCTION DESK</p>
        <h2>你好，{{ displayName }}</h2>
        <p>这里使用后端强制绑定当前账号的跨项目任务范围，不使用本地 Mock 或前端推断负责人。</p>
      </div>
      <span class="workbench-hero__label">{{ total }} 项我的任务</span>
    </div>

    <section class="activity-grid" :class="{ 'is-loading': activityLoading }">
      <article><header><div><p class="sg-eyebrow">REVIEW QUEUE</p><h3>待我审核</h3></div><el-button text @click="router.push('/reviews')">查看全部</el-button></header><button v-for="item in pendingReviews" :key="item.reviewListId" type="button" @click="router.push(`/reviews/${item.reviewListId}`)"><span><strong>{{ item.reviewListName }}</strong><small>{{ item.projectCode }} · {{ item.reviewMode === 'manual_batch' ? `${item.versionCount} 个版本` : item.versionNumber }}</small></span><el-icon><Right /></el-icon></button><p v-if="!pendingReviews.length">当前没有待审核内容</p></article>
      <article><header><div><p class="sg-eyebrow">RECENT DELIVERY</p><h3>最近提交</h3></div></header><button v-for="item in recentSubmissions" :key="item.versionId" type="button" @click="router.push(`/versions/${item.versionId}`)"><span><strong>{{ item.versionNumber }} · {{ item.changelog }}</strong><small>{{ item.versionStatus === 'pending_review' ? '等待审核' : item.versionStatus === 'final' ? '已通过' : '已退回' }}</small></span><el-icon><Right /></el-icon></button><p v-if="!recentSubmissions.length">最近还没有提交版本</p></article>
    </section>

    <section class="task-workbench" aria-labelledby="my-task-title">
      <header class="workbench-section-heading">
        <div>
          <p class="sg-eyebrow">MY TASKS</p>
          <h3 id="my-task-title">我的制作任务</h3>
          <p>镜头视频和资产图片任务共用同一套后端状态与分页契约。</p>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadTasks">刷新</el-button>
      </header>

      <div class="task-stats" aria-label="当前分页任务摘要">
        <article><span>制作中</span><strong>{{ pageSummary.inProgress }}</strong><small>当前页</small></article>
        <article><span>待审核</span><strong>{{ pageSummary.pendingReview }}</strong><small>当前页</small></article>
        <article><span>待修订</span><strong>{{ pageSummary.revision }}</strong><small>当前页</small></article>
        <article :data-alert="pageSummary.overdue > 0"><span>已逾期</span><strong>{{ pageSummary.overdue }}</strong><small>当前页未完成</small></article>
      </div>

      <form class="task-filters" aria-label="我的任务筛选" @submit.prevent="submitFilters">
        <label class="task-filters__search"><span>搜索</span><div><el-icon><Search /></el-icon><input v-model="query.keyword" maxlength="200" placeholder="任务、项目、镜头或资产" /></div></label>
        <label><span>任务类型</span><el-select v-model="query.taskKind" class="sg-select" placeholder="全部类型"><el-option label="全部类型" value="" /><el-option label="镜头视频" value="shot_video" /><el-option label="资产图片" value="asset_image" /></el-select></label>
        <label><span>任务状态</span><el-select v-model="query.taskStatus" class="sg-select" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="未开始" value="not_started" /><el-option label="制作中" value="in_progress" /><el-option label="待审核" value="pending_review" /><el-option label="待修订" value="revision" /><el-option label="已完成" value="completed" /></el-select></label>
        <label><span>优先级</span><el-select v-model="query.priority" class="sg-select" placeholder="全部优先级"><el-option label="全部优先级" value="" /><el-option label="紧急" value="urgent" /><el-option label="高" value="high" /><el-option label="普通" value="normal" /><el-option label="低" value="low" /></el-select></label>
        <label><span>截止日期起</span><input v-model="query.dueDateFrom" type="date" /></label>
        <label><span>截止日期止</span><input v-model="query.dueDateTo" type="date" /></label>
        <label><span>排序</span><el-select v-model="orderValue" class="sg-select" aria-label="任务排序" @change="applyOrder"><el-option label="最近更新" value="updateTime:descending" /><el-option label="截止日期由近到远" value="dueDate:ascending" /><el-option label="优先级由高到低" value="priority:ascending" /><el-option label="最近创建" value="createTime:descending" /></el-select></label>
        <div class="task-filters__actions"><el-button native-type="submit" type="primary" :loading="loading">查询</el-button><el-button :disabled="loading" @click="resetFilters">重置</el-button></div>
        <p v-if="validationMessage" class="task-filters__error" role="alert">{{ validationMessage }}</p>
      </form>

      <ProjectStatePanel
        v-if="errorState"
        compact
        :title="errorState.title"
        :message="errorState.message"
        :retryable="errorState.retryable"
        @retry="loadTasks"
      />
      <div v-else-if="loading && !tasks.length" class="task-loading">正在加载我的任务…</div>
      <div v-else-if="!tasks.length" class="task-empty">
        <strong>{{ total ? '当前页没有任务' : '当前筛选暂无任务' }}</strong>
        <p>任务由项目总监在镜头或资产制作分项上分配，不在工作台中临时创建无归属任务。</p>
      </div>
      <div v-else class="task-list" :class="{ 'is-refreshing': loading }">
        <button v-for="item in tasks" :key="item.taskId" class="task-row" type="button" @click="openTask(item)">
          <span class="task-row__kind" :data-tone="taskKindMeta(item.taskKind).tone">{{ taskKindMeta(item.taskKind).shortLabel }}</span>
          <span class="task-row__main">
            <span class="task-row__heading"><strong>{{ item.taskName }}</strong><span class="status-chip" :data-tone="taskStatusMeta(item.taskStatus).tone">{{ taskStatusMeta(item.taskStatus).label }}</span></span>
            <small>{{ item.project.projectCode }} · {{ item.project.projectName }} / {{ item.target.targetName }}</small>
            <span>{{ item.requirements || '暂无额外制作要求' }}</span>
          </span>
          <span class="task-row__meta"><span>{{ taskAssigneeLabel(item.assignee) }}</span><small :data-tone="taskDueState(item.dueDate).tone">{{ taskDueState(item.dueDate).label }}</small></span>
          <span class="task-row__version"><strong>{{ item.latestVersion?.versionNumber || '—' }}</strong><small>{{ item.versionCount }} 个版本</small></span>
          <span class="priority-chip" :data-tone="taskPriorityMeta(item.priority).tone">{{ taskPriorityMeta(item.priority).label }}</span>
          <el-icon class="task-row__arrow"><Right /></el-icon>
        </button>
      </div>

      <nav v-if="total" class="task-pagination" aria-label="任务分页">
        <button type="button" :disabled="query.pageNum <= 1 || loading" @click="changePage(query.pageNum - 1)">上一页</button>
        <span>第 {{ query.pageNum }} / {{ pageCount }} 页 · 共 {{ total }} 项</span>
        <button type="button" :disabled="query.pageNum >= pageCount || loading" @click="changePage(query.pageNum + 1)">下一页</button>
      </nav>
    </section>

    <section v-if="availableModules.length" class="module-section">
      <div class="workbench-section-heading"><div><h3>其他可访问模块</h3><p>权限来自 Shot Grid 业务导航，不加载系统管理菜单。</p></div></div>
      <div class="module-grid">
        <button v-for="item in availableModules" :key="item.routeKey" class="module-card" type="button" @click="router.push(item.path)">
          <span class="module-card__icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="module-card__copy"><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span>
          <el-icon class="module-card__arrow"><Right /></el-icon>
        </button>
      </div>
    </section>
  </section>
</template>

<style scoped lang="scss">
.activity-grid.is-loading{opacity:.55;pointer-events:none}
.activity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.activity-grid>article{display:grid;gap:8px;padding:18px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.activity-grid header{display:flex;align-items:center;justify-content:space-between}.activity-grid h3{margin:3px 0 0;font-size:16px}.activity-grid button{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:11px;color:var(--sg-text);text-align:left;cursor:pointer;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:9px}.activity-grid button span{display:grid;min-width:0;gap:5px}.activity-grid button strong{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.activity-grid button small,.activity-grid>article>p{margin:0;color:var(--sg-text-muted);font-size:9px}@media(max-width:800px){.activity-grid{grid-template-columns:1fr}}
.workbench-page{display:grid;gap:28px}.workbench-hero{position:relative;display:flex;min-height:218px;align-items:flex-end;justify-content:space-between;padding:clamp(30px,5vw,54px);overflow:hidden;background:radial-gradient(circle at 86% 12%,rgba(255,182,87,.24),transparent 28%),linear-gradient(135deg,#1c222c,#101319 72%);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg);box-shadow:var(--sg-shadow)}.workbench-hero::after{position:absolute;top:-80px;right:-10px;width:310px;height:310px;content:'';border:1px solid rgba(255,255,255,.08);border-radius:50%}.workbench-hero>div{position:relative;z-index:1;max-width:760px}.workbench-hero h2{margin:0;font-size:clamp(30px,4vw,48px);font-weight:600;letter-spacing:-.045em}.workbench-hero p:not(.sg-eyebrow){max-width:680px;margin:16px 0 0;color:var(--sg-text-secondary);font-size:14px;line-height:1.8}.workbench-hero__label{position:relative;z-index:1;padding:7px 11px;color:var(--sg-text-secondary);font-size:11px;background:rgba(0,0,0,.22);border:1px solid var(--sg-border);border-radius:999px}.task-workbench,.module-section{display:grid;gap:16px}.workbench-section-heading{display:flex;gap:20px;align-items:flex-end;justify-content:space-between}.workbench-section-heading h3{margin:0;font-size:19px}.workbench-section-heading p:not(.sg-eyebrow){margin:7px 0 0;color:var(--sg-text-muted);font-size:12px}.task-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.task-stats article{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:15px 17px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.task-stats article[data-alert=true]{border-color:rgba(255,107,107,.28)}.task-stats span,.task-stats small{color:var(--sg-text-muted);font-size:10px}.task-stats strong{grid-row:1/3;grid-column:2;font-size:25px}.task-filters{display:grid;grid-template-columns:2fr repeat(6,minmax(120px,1fr)) auto;gap:10px;align-items:end;padding:16px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.task-filters label{display:grid;gap:6px}.task-filters label>span{color:var(--sg-text-muted);font-size:10px}.task-filters input,.task-filters select{width:100%;height:38px;box-sizing:border-box;padding:0 10px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.task-filters__search>div{position:relative}.task-filters__search .el-icon{position:absolute;top:11px;left:10px;color:var(--sg-text-muted)}.task-filters__search input{padding-left:31px}.task-filters__actions{display:flex;gap:7px}.task-filters__error{grid-column:1/-1;margin:0;color:var(--sg-danger);font-size:12px}.task-loading,.task-empty{display:grid;min-height:190px;padding:24px;color:var(--sg-text-muted);text-align:center;background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-md);place-content:center}.task-empty strong{color:var(--sg-text-secondary)}.task-empty p{max-width:620px;margin:8px 0 0;font-size:12px;line-height:1.7}.task-list{display:grid;overflow:hidden;background:var(--sg-border);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);gap:1px}.task-list.is-refreshing{pointer-events:none;opacity:.58}.task-row{display:grid;min-height:88px;grid-template-columns:48px minmax(240px,2fr) minmax(150px,1fr) 80px auto auto;gap:14px;align-items:center;padding:16px 18px;color:var(--sg-text);text-align:left;cursor:pointer;background:var(--sg-surface);border:0}.task-row:hover{background:var(--sg-surface-raised)}.task-row__kind{display:grid;width:42px;height:42px;color:#80bfff;font-size:11px;background:rgba(128,191,255,.08);border-radius:11px;place-items:center}.task-row__kind[data-tone=purple]{color:#c9a7ff;background:rgba(165,112,255,.1)}.task-row__main,.task-row__meta,.task-row__version{display:grid;min-width:0;gap:6px}.task-row__heading{display:flex;gap:8px;align-items:center}.task-row__heading strong{overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.task-row__main>small,.task-row__main>span:not(.task-row__heading),.task-row__meta,.task-row__version small{overflow:hidden;color:var(--sg-text-muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.task-row__meta>span{color:var(--sg-text-secondary);font-size:11px}.task-row__meta small[data-tone=danger]{color:var(--sg-danger)}.task-row__version strong{color:var(--sg-accent)}.status-chip,.priority-chip{display:inline-flex;width:max-content;padding:4px 7px;font-size:9px;background:rgba(255,255,255,.05);border-radius:999px}.status-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning],.priority-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger],.priority-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}.status-chip[data-tone=info],.priority-chip[data-tone=info]{color:#80bfff;background:rgba(128,191,255,.08)}.task-row__arrow{color:var(--sg-text-muted)}.task-pagination{display:flex;gap:14px;align-items:center;justify-content:center}.task-pagination button{padding:7px 11px;color:var(--sg-text-secondary);cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:8px}.task-pagination button:disabled{opacity:.35;cursor:not-allowed}.task-pagination span{color:var(--sg-text-muted);font-size:11px}.module-section{padding-top:6px;border-top:1px solid var(--sg-border)}.module-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.module-card{display:grid;min-height:105px;grid-template-columns:42px minmax(0,1fr) auto;gap:15px;align-items:center;padding:19px;color:var(--sg-text);text-align:left;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:160ms ease}.module-card:hover{background:var(--sg-surface-raised);border-color:rgba(255,182,87,.3);transform:translateY(-2px)}.module-card__icon{display:grid;width:42px;height:42px;color:var(--sg-accent);background:var(--sg-accent-soft);border-radius:12px;place-items:center}.module-card__copy strong,.module-card__copy small{display:block}.module-card__copy strong{font-size:13px}.module-card__copy small{margin-top:6px;color:var(--sg-text-muted);font-size:10px;line-height:1.5}.module-card__arrow{color:var(--sg-text-muted)}@media(max-width:1400px){.task-filters{grid-template-columns:repeat(4,minmax(0,1fr))}.task-filters__search{grid-column:span 2}.task-row{grid-template-columns:48px minmax(240px,2fr) minmax(140px,1fr) 70px auto}.task-row__arrow{display:none}}@media(max-width:1000px){.task-stats,.module-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.task-row{grid-template-columns:44px minmax(0,1fr) auto}.task-row__meta,.task-row__version{display:none}}@media(max-width:680px){.workbench-hero__label{display:none}.workbench-section-heading{align-items:flex-start;flex-direction:column}.task-stats,.task-filters,.module-grid{grid-template-columns:1fr}.task-filters__search{grid-column:auto}.task-filters__actions{width:100%}.task-row{grid-template-columns:38px minmax(0,1fr)}.task-row>.priority-chip{display:none}.task-row__kind{width:36px;height:36px}.task-row__heading{align-items:flex-start;flex-direction:column}}
</style>
