<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Refresh, VideoPlay } from '@element-plus/icons-vue'

import { assertPositiveId } from '@/api/shot-grid/projects'
import { getTaskDetail, startTask } from '@/api/shot-grid/tasks'
import VersionWorkspace from '@/components/version/VersionWorkspace.vue'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import TaskEditDialog from '@/views/task/components/TaskEditDialog.vue'
import {
  formatTaskDateTime,
  taskAssigneeLabel,
  taskDueState,
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta,
  taskVersionStatusMeta
} from '@/views/task/taskPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const task = ref(null)
const loading = ref(false)
const errorState = ref(null)
const actionError = ref(null)
const showEdit = ref(false)
const editContext = ref(null)
const routeContext = ref(null)
const startingOperation = ref(null)
let controller = null
let loadGeneration = 0
let operationGeneration = 0
let disposed = false

const taskId = computed(() => {
  try {
    return assertPositiveId(route.params.taskId, '任务')
  } catch {
    return null
  }
})
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const allowedActions = computed(() => new Set(task.value?.allowedActions || []))
const canEdit = computed(() => allowedActions.value.has('task.edit') && hasPermission('shotgrid:task:edit'))
const canStart = computed(() => allowedActions.value.has('task.start') && hasPermission('shotgrid:task:start'))
const isStarting = computed(() => isCurrentRouteOperation(startingOperation.value))
const targetRoute = computed(() => {
  if (!task.value?.project?.projectId || !task.value?.target) return null
  if (task.value.target.targetType === 'shot' && task.value.target.shotId) {
    return `/projects/${task.value.project.projectId}/shots/${task.value.target.shotId}`
  }
  if (task.value.target.targetType === 'asset_item' && task.value.target.assetId) {
    return `/projects/${task.value.project.projectId}/assets/${task.value.target.assetId}`
  }
  return null
})

function nextOperationGeneration() {
  operationGeneration += 1
  return operationGeneration
}

function closeEditDialog() {
  showEdit.value = false
  editContext.value = null
}

function isCurrentRouteOperation(operation) {
  return Boolean(
    operation &&
    routeContext.value &&
    operation.taskId === taskId.value &&
    operation.routeGeneration === routeContext.value.operationGeneration
  )
}

function isActiveEdit(operationContext) {
  return Boolean(
    editContext.value &&
    operationContext &&
    editContext.value.taskId === Number(operationContext.taskId) &&
    editContext.value.operationGeneration === Number(operationContext.operationGeneration) &&
    editContext.value.routeGeneration === routeContext.value?.operationGeneration &&
    taskId.value === Number(operationContext.taskId)
  )
}

async function loadDetail() {
  const generation = ++loadGeneration
  controller?.abort()
  closeEditDialog()
  task.value = null
  errorState.value = null
  actionError.value = null
  const targetTaskId = taskId.value
  if (!targetTaskId) {
    routeContext.value = null
    loading.value = false
    errorState.value = {
      title: '任务地址无效',
      message: '任务 ID 必须是正整数。',
      retryable: false
    }
    return
  }

  const activeContext = Object.freeze({
    taskId: targetTaskId,
    operationGeneration: nextOperationGeneration()
  })
  routeContext.value = activeContext
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  const isCurrent = () => (
    !disposed &&
    controller === requestController &&
    generation === loadGeneration &&
    !requestController.signal.aborted &&
    routeContext.value === activeContext &&
    taskId.value === targetTaskId
  )
  try {
    const response = await getTaskDetail(targetTaskId, { signal: requestController.signal })
    if (!isCurrent()) return
    task.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && isCurrent()) {
      errorState.value = taskErrorState(error, '任务详情加载失败')
    }
  } finally {
    if (controller === requestController && generation === loadGeneration) loading.value = false
  }
}

function openEditDialog() {
  if (!canEdit.value || !task.value || !routeContext.value || loading.value || isStarting.value) return
  editContext.value = Object.freeze({
    taskId: Number(task.value.taskId),
    routeGeneration: routeContext.value.operationGeneration,
    operationGeneration: nextOperationGeneration()
  })
  showEdit.value = true
}

async function beginTask() {
  if (!canStart.value || !task.value || !routeContext.value || loading.value || isStarting.value) return
  const operation = Object.freeze({
    taskId: Number(task.value.taskId),
    routeGeneration: routeContext.value.operationGeneration,
    operationGeneration: nextOperationGeneration(),
    lockVersion: Number(task.value.lockVersion)
  })
  startingOperation.value = operation
  actionError.value = null
  try {
    const response = await startTask(operation.taskId, { lockVersion: operation.lockVersion })
    if (!isCurrentRouteOperation(operation)) {
      ElMessage.success('任务已开始；当前页面未自动刷新。')
      return
    }
    task.value = response.data
    ElMessage.success('任务已进入制作中')
  } catch (error) {
    if (isCurrentRouteOperation(operation)) {
      actionError.value = taskErrorState(error, '开始任务失败')
    }
  } finally {
    if (startingOperation.value === operation) startingOperation.value = null
  }
}

async function handleSaved(_result, operationContext) {
  if (disposed || !isActiveEdit(operationContext)) {
    ElMessage.success('任务已保存；当前页面未自动刷新。')
    return
  }
  closeEditDialog()
  ElMessage.success('任务已更新')
  await loadDetail()
}

async function handleEditRefresh(operationContext) {
  if (!isActiveEdit(operationContext)) return
  closeEditDialog()
  await loadDetail()
}

async function handleVersionCommitted(_status, operationContext) {
  if (
    disposed ||
    Number(operationContext?.taskId) !== taskId.value ||
    Number(operationContext?.operationGeneration) !== routeContext.value?.operationGeneration
  ) {
    ElMessage.success('版本已发布；当前页面未自动刷新。')
    return
  }
  ElMessage.success('新版本已发布并创建自动审核单')
  await loadDetail()
}

onMounted(loadDetail)
watch(() => route.params.taskId, loadDetail)
onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  routeContext.value = null
  controller?.abort()
  closeEditDialog()
})
</script>

<template>
  <section class="sg-page task-detail-page">
    <button class="back-link" type="button" @click="router.push('/workbench')">
      <el-icon><ArrowLeft /></el-icon>
      返回任务工作台
    </button>

    <ProjectStatePanel
      v-if="errorState"
      :title="errorState.title"
      :message="errorState.message"
      :retryable="errorState.retryable"
      @retry="loadDetail"
    />
    <div v-else-if="loading && !task" class="task-detail-loading">正在加载任务详情…</div>

    <template v-else-if="task">
      <header class="task-hero">
        <div class="task-hero__main">
          <p class="sg-eyebrow">{{ task.project.projectCode }} · {{ taskKindMeta(task.taskKind).label }}</p>
          <div class="task-hero__title">
            <h2>{{ task.taskName }}</h2>
            <span class="status-chip" :data-tone="taskStatusMeta(task.taskStatus).tone">{{ taskStatusMeta(task.taskStatus).label }}</span>
          </div>
          <p>{{ task.target.targetName }} · {{ task.project.projectName }}</p>
          <small>更新于 {{ formatTaskDateTime(task.updateTime) }}</small>
        </div>
        <div class="task-hero__actions">
          <el-button :icon="Refresh" :loading="loading" :disabled="isStarting" @click="loadDetail">刷新</el-button>
          <el-button v-if="canStart" type="primary" :icon="VideoPlay" :loading="isStarting" :disabled="loading" @click="beginTask">开始任务</el-button>
          <el-button v-if="canEdit" :icon="Edit" :disabled="loading || isStarting" @click="openEditDialog">编辑任务</el-button>
        </div>
      </header>

      <ProjectStatePanel
        v-if="actionError"
        compact
        :title="actionError.title"
        :message="actionError.message"
        :retryable="actionError.retryable"
        @retry="loadDetail"
      />

      <section class="task-detail-grid">
        <article class="task-card task-card--wide">
          <header><div><p class="sg-eyebrow">BRIEF</p><h3>制作要求</h3></div><span class="priority-chip" :data-tone="taskPriorityMeta(task.priority).tone">{{ taskPriorityMeta(task.priority).label }}优先级</span></header>
          <p class="task-requirements">{{ task.requirements || '暂无额外制作要求。' }}</p>
          <dl class="task-fields task-fields--four">
            <div><dt>主制作人</dt><dd>{{ taskAssigneeLabel(task.assignee) }}</dd></div>
            <div><dt>截止日期</dt><dd :data-tone="taskDueState(task.dueDate).tone">{{ taskDueState(task.dueDate).label }}</dd></div>
            <div><dt>任务锁版本</dt><dd>{{ task.lockVersion }}</dd></div>
            <div><dt>已提交版本</dt><dd>{{ task.versionCount }}</dd></div>
          </dl>
        </article>

        <article class="task-card">
          <p class="sg-eyebrow">TARGET</p>
          <h3>生产对象</h3>
          <strong>{{ task.target.targetName }}</strong>
          <p>{{ task.target.targetDescription || '暂无对象说明' }}</p>
          <dl class="task-fields">
            <div><dt>类型</dt><dd>{{ taskKindMeta(task.taskKind).label }}</dd></div>
            <div><dt>生命周期</dt><dd>{{ task.target.lifecycleStatus === 'active' ? '活动' : '已归档' }}</dd></div>
          </dl>
          <button v-if="targetRoute" class="text-action" type="button" @click="router.push(targetRoute)">查看{{ taskKindMeta(task.taskKind).shortLabel }}详情</button>
        </article>

        <article class="task-card">
          <p class="sg-eyebrow">VERSION</p>
          <h3>版本摘要</h3>
          <template v-if="task.latestVersion">
            <strong class="version-number">{{ task.latestVersion.versionNumber }}</strong>
            <span class="status-chip" :data-tone="taskVersionStatusMeta(task.latestVersion.versionStatus).tone">{{ taskVersionStatusMeta(task.latestVersion.versionStatus).label }}</span>
            <p>提交于 {{ formatTaskDateTime(task.latestVersion.submittedTime) }}</p>
          </template>
          <div v-else class="task-empty">尚未生成正式版本。</div>
          <p v-if="task.finalVersion" class="final-version">最终版本：{{ task.finalVersion.versionNumber }}</p>
        </article>

        <article class="task-card task-card--wide version-workspace-anchor" data-testid="version-workspace-anchor">
          <p class="sg-eyebrow">DELIVERY</p>
          <h3>版本提交与历史</h3>
          <VersionWorkspace
            :task-id="task.taskId"
            :task-kind="task.taskKind"
            :allowed-actions="task.allowedActions"
            :has-uncommitted-submission="task.hasUncommittedSubmission"
            :operation-generation="routeContext.operationGeneration"
            @committed="handleVersionCommitted"
          />
        </article>

        <article class="task-card task-card--wide">
          <p class="sg-eyebrow">AUDIT</p>
          <h3>审计与备注</h3>
          <p class="task-remark">{{ task.remark || '暂无内部备注。' }}</p>
          <dl class="task-fields task-fields--four">
            <div><dt>创建人</dt><dd>{{ task.createBy }}</dd></div>
            <div><dt>创建时间</dt><dd>{{ formatTaskDateTime(task.createTime) }}</dd></div>
            <div><dt>更新人</dt><dd>{{ task.updateBy }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatTaskDateTime(task.updateTime) }}</dd></div>
          </dl>
        </article>
      </section>

      <TaskEditDialog
        v-if="showEdit && editContext"
        :task="task"
        :operation-generation="editContext.operationGeneration"
        @close="closeEditDialog"
        @saved="handleSaved"
        @refresh="handleEditRefresh"
      />
    </template>
  </section>
</template>

<style scoped>
.task-detail-page{display:grid;gap:18px}.back-link{display:inline-flex;width:max-content;gap:7px;align-items:center;padding:0;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0}.back-link:hover{color:var(--sg-text)}.task-detail-loading{display:grid;min-height:360px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg);place-items:center}.task-hero{display:flex;gap:24px;align-items:center;justify-content:space-between;padding:26px;background:linear-gradient(135deg,rgba(255,182,87,.075),transparent 42%),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg)}.task-hero__main{min-width:0}.task-hero__title{display:flex;gap:12px;align-items:center}.task-hero h2,.task-hero p{margin:0}.task-hero h2{font-size:clamp(23px,3vw,31px);letter-spacing:-.025em}.task-hero__main>p:not(.sg-eyebrow){margin-top:9px;color:var(--sg-text-secondary);font-size:13px}.task-hero small{display:block;margin-top:8px;color:var(--sg-text-muted)}.task-hero__actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}.task-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.task-card{padding:21px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.task-card--wide{grid-column:1/-1}.task-card header{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.task-card h3,.task-card p{margin:0}.task-card h3{margin-bottom:16px;font-size:17px}.task-card>strong{display:block;font-size:16px}.task-card>strong+p{margin-top:7px;color:var(--sg-text-secondary);font-size:12px;line-height:1.7}.task-requirements,.task-remark,.version-workspace-anchor>p:not(.sg-eyebrow){color:var(--sg-text-secondary);font-size:13px;line-height:1.8;white-space:pre-wrap}.version-workspace-anchor{background:linear-gradient(135deg,rgba(93,176,255,.055),transparent 46%),var(--sg-surface)}.version-workspace-anchor code{color:var(--sg-accent)}.status-chip,.priority-chip{display:inline-flex;width:max-content;padding:5px 8px;font-size:10px;background:rgba(255,255,255,.05);border-radius:999px}.status-chip[data-tone=success],.priority-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning],.priority-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger],.priority-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}.status-chip[data-tone=info],.priority-chip[data-tone=info]{color:#80bfff;background:rgba(128,191,255,.08)}.task-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:16px 0 0;overflow:hidden;background:var(--sg-border);border-radius:9px}.task-fields--four{grid-template-columns:repeat(4,minmax(0,1fr))}.task-fields div{padding:13px;background:rgba(13,16,21,.92)}dt{color:var(--sg-text-muted);font-size:10px}dd{margin:5px 0 0;color:var(--sg-text-secondary);font-size:12px;overflow-wrap:anywhere}dd[data-tone=danger]{color:var(--sg-danger)}.text-action{margin-top:15px;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.version-number{display:inline!important;margin-right:9px;color:var(--sg-accent);font-size:25px!important}.task-empty{padding:20px;color:var(--sg-text-muted);font-size:12px;text-align:center;background:rgba(255,255,255,.02);border:1px dashed var(--sg-border);border-radius:9px}.final-version{margin-top:14px!important;color:var(--sg-success);font-size:12px}@media(max-width:820px){.task-hero{align-items:flex-start;flex-direction:column}.task-hero__actions{justify-content:flex-start}.task-fields--four{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.task-detail-grid{grid-template-columns:1fr}.task-card--wide{grid-column:auto}.task-fields,.task-fields--four{grid-template-columns:1fr}.task-hero__title{align-items:flex-start;flex-direction:column}}
</style>
