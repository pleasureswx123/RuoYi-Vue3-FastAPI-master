<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElTable, ElTableColumn, ElTabs, ElTabPane, ElRadioGroup, ElRadioButton } from 'element-plus'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { RefreshLeft, Refresh, Search } from '@element-plus/icons-vue'

import { getMineTaskPage } from '@/api/shot-grid/tasks'
import ReviewQueuePanel from './ReviewQueuePanel.vue'
import MySubmissionsPanel from './MySubmissionsPanel.vue'
import { useTaskStatePolling } from '@/composables/useTaskStatePolling'
import { useCurrentTime } from '@/composables/useCurrentTime'
import TaskTimeReminder from '@/views/task/components/TaskTimeReminder.vue'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import {
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta,
  taskVersionStatusMeta
} from '@/views/task/taskPresentation'

const sessionStore = useSessionStore()
const tasks = ref([])
const taskDetailDrawer = ref(null)
const statusOptions = [
  { value: 'unfinished', label: '未完成' },
  { value: 'revision', label: '待修改' },
  { value: 'in_progress', label: '制作中' },
  { value: 'pending_review', label: '待审核' },
  { value: 'pending_schedule', label: '待排期' },
  { value: 'not_started', label: '待开工' },
  { value: 'completed', label: '已完成' },
  { value: '', label: '全部' }
]
const currentTime = useCurrentTime()
const total = ref(0)
const loading = ref(false)
const errorState = ref(null)
const taskFilterForm = ref(null)
const query = reactive({
  keyword: '',
  taskKind: '',
  taskStatus: 'unfinished',
  priority: '',
  dueDateRange: [],
  pageNum: 1,
  pageSize: 20,
  orderByColumn: 'workbench',
  isAsc: 'ascending',
  orderValue: 'workbench:ascending'
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
const appliedQuery = ref('')
let controller = null
let loadGeneration = 0
let disposed = false

const displayName = computed(() => sessionStore.user?.userName || sessionStore.user?.nickName || '制作成员')
const hasPermission = permission => (
  sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes(permission)
)
const canReviewQueue = computed(() => (
  hasPermission('shotgrid:reviewList:list') && hasPermission('shotgrid:version:review')
))
const hasProductionRole = computed(() => !canReviewQueue.value || sessionStore.roles.includes('shotgrid_creator'))
const canViewTasks = computed(() => hasProductionRole.value && hasPermission('shotgrid:task:list'))
const canViewRecentSubmissions = computed(() => hasProductionRole.value && hasPermission('shotgrid:version:list'))
const activeTab = ref(canReviewQueue.value ? 'reviews' : canViewTasks.value ? 'tasks' : 'submissions')
const welcomeDescription = computed(() => canReviewQueue.value
  ? '在“待审核”中查看管理范围内的审核内容，跟进审核进度。'
  : '在“我的任务”中跟进制作进度，在“提交记录”中查看历史版本与审核反馈。')
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const { pollingError } = useTaskStatePolling({
  getDelay: () => {
    if (activeTab.value !== 'tasks' || loading.value || errorState.value || appliedQuery.value !== JSON.stringify(query)) return null
    const activeTasks = tasks.value.filter(task => (
      !['completed', 'archived'].includes(task.project?.projectStatus) && task.target?.lifecycleStatus !== 'archived'
    ))
    if (activeTasks.some(task => task.taskStatus === 'preparing')) return 1500
    return activeTasks.some(task => task.taskStatus === 'not_started') ? 5000 : null
  },
  refresh: requestController => loadTasks(requestController)
})

function getDueDateBounds() {
  const [dueDateFrom, dueDateTo] = Array.isArray(query.dueDateRange) ? query.dueDateRange : []
  return { dueDateFrom: dueDateFrom || '', dueDateTo: dueDateTo || '' }
}

function buildParams() {
  const { dueDateFrom, dueDateTo } = getDueDateBounds()
  return {
    keyword: query.keyword.trim() || undefined,
    taskKind: query.taskKind || undefined,
    taskStatus: query.taskStatus === 'unfinished' ? undefined : query.taskStatus || undefined,
    unfinishedOnly: query.taskStatus === 'unfinished',
    priority: query.priority || undefined,
    dueDateFrom: dueDateFrom || undefined,
    dueDateTo: dueDateTo || undefined,
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    orderByColumn: query.orderByColumn,
    isAsc: query.isAsc
  }
}

async function loadTasks(backgroundController = null) {
  const background = Boolean(backgroundController)
  const generation = ++loadGeneration
  controller?.abort()
  controller = null
  if (!background) {
    loading.value = true
    let isValid = true
    if (taskFilterForm.value) {
      await taskFilterForm.value.validate(valid => {
        isValid = valid
      })
    }
    if (!isValid || disposed || generation !== loadGeneration) {
      if (generation === loadGeneration) loading.value = false
      return
    }
    errorState.value = null
    appliedQuery.value = JSON.stringify(query)
  }
  const requestController = backgroundController || new AbortController()
  controller = requestController
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
      if (background) throw error
      tasks.value = []
      total.value = 0
      errorState.value = taskErrorState(error, '我的任务加载失败')
    }
  } finally {
    if (!background && controller === requestController && generation === loadGeneration) loading.value = false
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
    taskStatus: 'unfinished',
    pageNum: 1,
    pageSize: 20,
    orderByColumn: 'workbench',
    isAsc: 'ascending',
    orderValue: 'workbench:ascending'
  })
  loadTasks()
}

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum || loading.value) return
  query.pageNum = page
  loadTasks()
}

function changePageSize(size) {
  if (size === query.pageSize || loading.value) return
  query.pageSize = size
  query.pageNum = 1
  loadTasks()
}

function openTask(task) {
  taskDetailDrawer.value?.open(`/tasks/${task.taskId}`)
}

function taskActionLabel(task) {
  if (['completed', 'archived'].includes(task.project?.projectStatus) || task.target?.lifecycleStatus === 'archived') return '查看任务'
  return { revision: '查看修改意见', in_progress: '继续制作', pending_review: '查看审核进度', completed: '查看成果' }[task.taskStatus] || '查看任务'
}

function taskActionType(task) {
  if (['completed', 'archived'].includes(task.project?.projectStatus) || task.target?.lifecycleStatus === 'archived') return 'info'
  return { revision: 'danger', in_progress: 'primary', pending_review: 'warning', completed: 'success' }[task.taskStatus] || 'info'
}

onMounted(() => { if (canViewTasks.value) loadTasks() })
onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  controller?.abort()
})
</script>

<template>
  <section class="sg-page workbench-page">
    <div class="workbench-hero">
      <div class="workbench-hero__content">

        <h2>你好，{{ displayName }}</h2>
        <p>{{ welcomeDescription }}</p>
      </div>

    </div>

    <el-tabs v-model="activeTab" class="workbench-tabs">
    <el-tab-pane v-if="canReviewQueue" label="待审核" name="reviews" lazy>
      <ReviewQueuePanel />
    </el-tab-pane>
    <el-tab-pane v-if="canViewTasks" label="我的任务" name="tasks">
    <section class="task-workbench" aria-label="我的任务">
      <header class="workbench-section-heading">
        <div>
          <p>查看分配给我的制作任务，跟进制作进度与审核反馈。</p>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadTasks()">刷新</el-button>
      </header>

      <el-radio-group v-model="query.taskStatus" class="task-status-shortcuts" aria-label="按任务状态筛选" @change="submitFilters">
        <el-radio-button v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio-button>
      </el-radio-group>

      <el-form ref="taskFilterForm" :model="query" :rules="taskFilterRules" class="task-filters" size="large" label-position="top" aria-label="我的任务筛选">
        <el-form-item class="task-filter-item task-filter-item--search" label="搜索" prop="keyword">
          <el-input v-model="query.keyword" class="sg-input" :prefix-icon="Search" maxlength="200" clearable placeholder="任务、项目、镜头或资产" aria-label="搜索任务" @keyup.enter="submitFilters" />
        </el-form-item>
        <el-form-item class="task-filter-item" label="任务类型" prop="taskKind">
          <el-select v-model="query.taskKind" class="sg-select" placeholder="全部类型" aria-label="按任务类型筛选" @change="submitFilters"><el-option label="全部类型" value="" /><el-option label="镜头视频" value="shot_video" /><el-option label="资产图片" value="asset_image" /></el-select>
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
          <el-select v-model="query.orderValue" class="sg-select" aria-label="任务排序" @change="applyOrder"><el-option label="优先处理" value="workbench:ascending" /><el-option label="镜头号由小到大" value="shotNo:ascending" /><el-option label="最近更新" value="updateTime:descending" /><el-option label="截止日期由近到远" value="dueDate:ascending" /><el-option label="优先级由高到低" value="priority:ascending" /><el-option label="最近创建" value="createTime:descending" /></el-select>
        </el-form-item>
        <el-form-item class="task-filter-actions"><el-button type="primary" :loading="loading" @click="submitFilters">查询</el-button><el-button :icon="RefreshLeft" :disabled="loading" @click="resetFilters">重置</el-button></el-form-item>
      </el-form>

      <el-alert v-if="pollingError" :title="pollingError" type="warning" show-icon :closable="false" />
      <ProjectStatePanel
        v-if="errorState"
        compact
        :title="errorState.title"
        :message="errorState.message"
        :retryable="errorState.retryable"
        @retry="loadTasks()"
      />
      <el-card v-else-if="loading && !tasks.length" class="task-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="5" /></el-card>
      <el-empty v-else-if="!tasks.length" class="task-empty" :description="total ? '当前页没有任务' : '当前筛选暂无任务'"><p>任务由项目管理人在镜头或资产制作分项中分配。</p></el-empty>
      <el-table v-else v-loading="loading" :data="tasks" row-key="taskId" class="task-list" aria-label="我的制作任务">
        <el-table-column label="制作任务" min-width="300">
          <template #default="{ row }">
            <el-button v-if="hasPermission('shotgrid:task:query')" link type="primary" class="task-title" @click="openTask(row)">{{ row.taskName }}</el-button>
            <strong v-else>{{ row.taskName }}</strong>
            <div class="task-context">{{ row.project.projectCode }} · {{ row.project.projectName }} / {{ taskKindMeta(row.taskKind).label }}</div>
            <div class="task-requirements">{{ row.requirements || row.target.targetDescription || '暂无额外制作要求' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="当前状态" width="140">
          <template #default="{ row }">
            <el-tag :type="tagTypeFromTone(taskStatusMeta(row).tone)" size="small" effect="dark" round>{{ taskStatusMeta(row).label }}</el-tag>
            <small v-if="row.taskStatus === 'not_started'" class="task-context">{{ row.expectedStartTime && row.expectedEndTime ? '等待管理人员确认开工' : '等待管理人员设置排期' }}</small>
            <small v-else-if="row.taskStatus === 'preparing'" class="task-context">目录就绪后可制作</small>
            <small v-if="row.project.projectStatus === 'archived' || row.target.lifecycleStatus === 'archived'" class="task-context">已归档 · 只读</small>
          </template>
        </el-table-column>
        <el-table-column label="制作时间" min-width="200"><template #default="{ row }"><TaskTimeReminder :task="row" :now="currentTime" compact /></template></el-table-column>
        <el-table-column label="最新提交" min-width="135">
          <template #default="{ row }">
            <el-button v-if="row.latestVersion && hasPermission('shotgrid:version:query')" link type="primary" @click="taskDetailDrawer?.open(`/versions/${row.latestVersion.versionId}`)">{{ row.latestVersion.versionNumber }}</el-button>
            <span v-else>{{ row.latestVersion?.versionNumber || '尚未提交' }}</span>
            <small class="task-context">{{ row.latestVersion ? taskVersionStatusMeta(row.latestVersion.versionStatus).label : '等待首次提交' }} · {{ row.versionCount }} 个版本</small>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90"><template #default="{ row }"><el-tag v-if="['urgent', 'high'].includes(row.priority)" :type="tagTypeFromTone(taskPriorityMeta(row.priority).tone)" size="small">{{ taskPriorityMeta(row.priority).label }}</el-tag><span v-else class="task-context">{{ taskPriorityMeta(row.priority).label }}</span></template></el-table-column>
        <el-table-column label="下一步" width="150" fixed="right"><template #default="{ row }"><el-button v-if="hasPermission('shotgrid:task:query')" :type="taskActionType(row)" size="small" @click="openTask(row)">{{ taskActionLabel(row) }}</el-button><span v-else class="task-context">无详情查看权限</span></template></el-table-column>
      </el-table>

      <el-pagination v-if="total" class="task-pagination" background layout="total, sizes, prev, pager, next" :current-page="query.pageNum" :page-size="query.pageSize" :page-sizes="[10, 20, 50]" :total="total" :disabled="loading" aria-label="任务分页" @current-change="changePage" @update:page-size="changePageSize" />
    </section>

    </el-tab-pane>
    <el-tab-pane v-if="canViewRecentSubmissions" label="提交记录" name="submissions" lazy>
      <MySubmissionsPanel />
    </el-tab-pane>
    </el-tabs>
    <RelatedDetailDrawer ref="taskDetailDrawer" @closed="canViewTasks && loadTasks()" />

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
  min-height: 64px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
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
  font-size: 22px;
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
  align-items: center;
  justify-content: space-between;
}

.workbench-section-heading p {
  margin: 0;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.task-filters {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr auto;
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

.task-list { border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.task-title { max-width: 100%; height: auto; white-space: normal; text-align: left; font-weight: 600; }
.task-context { display: block; margin-top: 5px; color: var(--sg-text-muted); font-size: 12px; }
.task-requirements { margin-top: 5px; color: var(--sg-text-secondary); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-status-shortcuts { gap: 6px; }
.task-status-shortcuts :deep(.el-radio-button__inner) { border: 1px solid var(--sg-border); border-radius: 6px; box-shadow: none; }
.workbench-tabs { min-width: 0; }

.task-pagination {
  display: flex;
  justify-content: center;
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


}

@media (max-width: 680px) {
  .workbench-page {
    gap: 16px;
  }

  .workbench-hero {
    min-height: 64px;
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

  .task-filters {
    grid-template-columns: 1fr;
  }

  .task-filter-item--search,
  .task-filter-item--date-range {
    grid-column: auto;
  }

  .task-filter-actions {
    width: 100%;
  }




}
</style>
