<script setup>
import RevisionTransferDialog from '@/components/version/RevisionTransferDialog.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Refresh } from '@element-plus/icons-vue'

import { assertPositiveId } from '@/api/shot-grid/projects'
import { getTaskIssues } from '@/api/shot-grid/reviews'
import { showWorkflowSuccess } from '@/utils/workflowSuccess'
import { useVersionRealtime } from '@/composables/useVersionRealtime'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import VersionWorkspace from '@/components/version/VersionWorkspace.vue'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'
import TaskEditDialog from '@/views/task/components/TaskEditDialog.vue'
import TaskTimeReminder from '@/views/task/components/TaskTimeReminder.vue'
import { useCurrentTime } from '@/composables/useCurrentTime'
import {
  formatTaskDateTime,
  taskAssigneeLabel,
  taskErrorState,
  taskKindMeta,
  taskPriorityMeta,
  taskStatusMeta
} from '@/views/task/taskPresentation'

const WAITING_START_POLL_INTERVAL_MS = 5000
const STATUS_POLL_MAX_FAILURES = 3
const PREPARATION_POLL_INTERVAL_MS = 1500
const PREPARATION_POLL_MAX_ATTEMPTS = 80

const props = defineProps({ targetTaskId: { type: [Number, String], default: null }, embedded: { type: Boolean, default: false } })
const emit = defineEmits(['completed'])
const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const task = ref(null)
const currentTime = useCurrentTime()
const openIssues = ref([])
const loading = ref(false)
const errorState = ref(null)
const actionError = ref(null)
const showEdit = ref(false)
const editContext = ref(null)
const routeContext = ref(null)
let controller = null
let statusController = null
let statusTimer = null
let statusGeneration = 0
let loadGeneration = 0
let operationGeneration = 0
let disposed = false

const taskId = computed(() => {
  try {
    return assertPositiveId(props.targetTaskId ?? route.params.taskId, '任务')
  } catch {
    return null
  }
})
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const issueRealtimeVersionId = computed(() => hasPermission('shotgrid:version:query') && ['pending_review', 'revision'].includes(task.value?.taskStatus)
  ? task.value?.latestVersion?.versionId : null)
useVersionRealtime(issueRealtimeVersionId, async versionId => {
  const targetTaskId = taskId.value
  const generation = loadGeneration
  const [taskResponse, response] = await Promise.all([
    getTaskDetail(targetTaskId),
    hasPermission('shotgrid:note:list') ? getTaskIssues(targetTaskId, { status: 'open' }) : Promise.resolve({ data: [] })
  ])
  if (disposed || loading.value || generation !== loadGeneration || targetTaskId !== taskId.value || versionId !== issueRealtimeVersionId.value) return
  const knownIds = new Set(openIssues.value.map(issue => issue.issueId))
  const updated = response.data || []
  const added = updated.filter(issue => !knownIds.has(issue.issueId)).length
  const previousStatus = task.value?.taskStatus
  task.value = taskResponse.data
  openIssues.value = updated
  if (previousStatus === 'pending_review' && task.value?.taskStatus === 'revision') ElMessage.info('审核已退回，请按修改意见继续制作')
  else if (previousStatus === 'pending_review' && task.value?.taskStatus === 'completed') ElMessage.success('审核已通过，任务已完成')
  else if (added) ElMessage.info(`审核人追加了 ${added} 条修改意见，已更新问题列表`)
})
const transferDialog = ref(null)
const allowedActions = computed(() => new Set(task.value?.allowedActions || []))
const canEdit = computed(() => (
  task.value?.taskStatus === 'not_started' &&
  allowedActions.value.has('task.edit') &&
  hasPermission('shotgrid:task:edit')
))
const isShotTask = computed(() => task.value?.taskKind === 'shot_video')
const isWaitingForStart = computed(() => task.value?.taskStatus === 'not_started')
const shouldPollTaskState = computed(() => (
  !['completed', 'archived'].includes(task.value?.project?.projectStatus) &&
  task.value?.target?.lifecycleStatus === 'active' &&
  (isWaitingForStart.value || task.value?.taskStatus === 'preparing')
))
const shotProduction = computed(() => isShotTask.value ? task.value?.shotProduction : null)
const versionProductionDescription = computed(() => {
  if (isShotTask.value) {
    return String(shotProduction.value?.description || task.value?.requirements || task.value?.target?.targetDescription || '').trim()
  }
  return String(task.value?.requirements || task.value?.target?.targetDescription || task.value?.target?.productionItem || '').trim()
})
const hasAdditionalShotRequirements = computed(() => {
  if (!isShotTask.value) return false
  const requirements = String(task.value?.requirements || '').trim()
  const description = String(shotProduction.value?.description || '').trim()
  return Boolean(requirements && requirements !== description)
})
const assetTargetIncomplete = computed(() => (
  task.value?.taskKind === 'asset_image' && !String(task.value?.target?.productionItem || '').trim()
))
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

function stopTaskStatusPolling() {
  statusGeneration += 1
  if (statusTimer !== null) {
    clearTimeout(statusTimer)
    statusTimer = null
  }
  statusController?.abort()
  statusController = null
}

function isCurrentStatusContext(context, generation) {
  return Boolean(
    !disposed &&
    context &&
    statusGeneration === generation &&
    routeContext.value === context &&
    taskId.value === context.taskId
  )
}

function preparationTimeoutState() {
  return {
    title: '制作目录准备时间较长',
    message: '页面未能及时确认目录准备结果，请点击刷新查看最新状态；如果任务持续停留在目录准备中，请联系管理员检查目录任务。',
    retryable: true
  }
}

function scheduleTaskStatusPoll(context, generation, attempt, failures = 0) {
  if (!isCurrentStatusContext(context, generation) || !shouldPollTaskState.value) return
  if (failures >= STATUS_POLL_MAX_FAILURES) {
    stopTaskStatusPolling()
    actionError.value = {
      title: '任务状态更新失败',
      message: '连续查询失败，已暂停自动刷新。请检查网络后点击刷新查看最新状态。',
      retryable: true
    }
    return
  }
  if (!isWaitingForStart.value && attempt >= PREPARATION_POLL_MAX_ATTEMPTS) {
    stopTaskStatusPolling()
    actionError.value = preparationTimeoutState()
    return
  }
  const waiting = isWaitingForStart.value
  statusTimer = setTimeout(() => {
    statusTimer = null
    void pollTaskStatus(context, generation, waiting ? 0 : attempt + 1, failures)
  }, waiting ? WAITING_START_POLL_INTERVAL_MS : PREPARATION_POLL_INTERVAL_MS)
}

async function pollTaskStatus(context, generation, attempt, failures) {
  if (!isCurrentStatusContext(context, generation)) return
  const requestController = new AbortController()
  statusController = requestController
  try {
    const response = await getTaskDetail(context.taskId, { signal: requestController.signal })
    if (!isCurrentStatusContext(context, generation) || requestController.signal.aborted) return
    const previousStatus = task.value?.taskStatus
    task.value = response.data
    if (shouldPollTaskState.value) {
      scheduleTaskStatusPoll(context, generation, previousStatus === 'preparing' ? attempt : 0)
      return
    }
    stopTaskStatusPolling()
    actionError.value = null
    if (response.data?.taskStatus === 'in_progress') {
      ElMessage.success('制作目录已准备完成，可以' +
        (Number(response.data?.versionCount || 0) > 0 ? '提交修改成果' : '提交首版成果'))
    }
  } catch (error) {
    if (error?.code === 'ERR_CANCELED' || !isCurrentStatusContext(context, generation)) return
    if ([401, 403, 404].includes(Number(error?.status || error?.httpStatus))) {
      stopTaskStatusPolling()
      actionError.value = { ...taskErrorState(error, '无法更新任务状态'), retryable: false }
      return
    }
    scheduleTaskStatusPoll(context, generation, attempt, failures + 1)
  } finally {
    if (statusController === requestController) statusController = null
  }
}

function startTaskStatusPolling(context = routeContext.value) {
  stopTaskStatusPolling()
  if (!context || !shouldPollTaskState.value) return
  scheduleTaskStatusPoll(context, statusGeneration, 0)
}

function closeEditDialog() {
  showEdit.value = false
  editContext.value = null
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
  stopTaskStatusPolling()
  closeEditDialog()
  task.value = null
  openIssues.value = []
  errorState.value = null
  actionError.value = null
  const targetTaskId = taskId.value
  if (!targetTaskId) {
    routeContext.value = null
    loading.value = false
    errorState.value = {
      title: '任务地址无效',
      message: '请返回任务工作台并重新打开该任务。',
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
    const [response, issueResponse] = await Promise.all([
      getTaskDetail(targetTaskId, { signal: requestController.signal }),
      hasPermission('shotgrid:note:list')
        ? getTaskIssues(targetTaskId, { status: 'open' }, { signal: requestController.signal })
        : Promise.resolve({ data: [] })
    ])
    if (!isCurrent()) return
    task.value = response.data
    openIssues.value = issueResponse.data || []
    startTaskStatusPolling(activeContext)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && isCurrent()) {
      errorState.value = taskErrorState(error, '任务详情加载失败')
    }
  } finally {
    if (controller === requestController && generation === loadGeneration) loading.value = false
  }
}

function openEditDialog() {
  if (!canEdit.value || !task.value || !routeContext.value || loading.value) return
  editContext.value = Object.freeze({
    // 编辑字段和锁版本必须来自同一次快照，不能被后台轮询替换。
    task: Object.freeze({ ...task.value }),
    taskId: Number(task.value.taskId),
    routeGeneration: routeContext.value.operationGeneration,
    operationGeneration: nextOperationGeneration()
  })
  showEdit.value = true
}

async function handleSaved(_result, operationContext) {
  if (disposed || !isActiveEdit(operationContext)) {
    ElMessage.success('任务已保存，请返回原任务查看最新结果。')
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
    ElMessage.success('版本已发布，请返回原任务查看最新结果。')
    return
  }
  const submittedTaskId = taskId.value
  showWorkflowSuccess(task.value?.taskStatus === 'pending_review' ? 'appended' : 'submitted').then(confirmed => {
    if (confirmed && !disposed && props.embedded && taskId.value === submittedTaskId) emit('completed')
  })
  await loadDetail()
}

onMounted(loadDetail)
watch(taskId, loadDetail)
onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  routeContext.value = null
  controller?.abort()
  stopTaskStatusPolling()
  closeEditDialog()
})
</script>

<template>
  <section class="sg-page task-detail-page" :class="{ 'task-detail-page--embedded': embedded }">
    <RevisionTransferDialog ref="transferDialog" @saved="loadDetail" />
    <el-button v-if="!embedded" class="back-link" link :icon="ArrowLeft" @click="router.push('/workbench')">返回任务工作台</el-button>

    <ProjectStatePanel
      v-if="errorState"
      :title="errorState.title"
      :message="errorState.message"
      :retryable="errorState.retryable"
      @retry="loadDetail"
    />
    <el-card v-else-if="loading && !task" class="task-detail-loading" shadow="never" aria-busy="true">
      <span class="task-detail-loading__label">正在加载任务详情</span>
      <el-skeleton animated :rows="8" />
    </el-card>

    <template v-else-if="task">
      <header class="task-hero">
        <div class="task-hero__main">
          <p class="sg-eyebrow">{{ task.project.projectCode }} · {{ taskKindMeta(task.taskKind).label }}</p>
          <div class="task-hero__title">
            <h2>{{ task.taskName }}</h2>
            <el-tag :type="tagTypeFromTone(taskStatusMeta(task).tone)" size="small" effect="light" round>{{ taskStatusMeta(task).label }}</el-tag>
          </div>
          <p>{{ task.target.targetName }} · {{ task.project.projectName }}</p>
          <small>更新于 {{ formatTaskDateTime(task.updateTime) }}</small>
        </div>
        <div class="task-hero__actions">
          <el-button v-if="allowedActions.has('task.transfer')" type="primary" :disabled="loading" @click="transferDialog.open(task.latestVersion.versionId)">转交修改</el-button>
          <el-button :icon="Refresh" :loading="loading" @click="loadDetail">刷新</el-button>
          <el-button v-if="canEdit" :icon="Edit" :disabled="loading" @click="openEditDialog">编辑任务</el-button>
        </div>
      </header>

      <el-alert v-if="task.latestHandoff" :title="`${task.latestHandoff.fromName} → ${task.latestHandoff.toName} · 修改交接`" type="info" :closable="false">
        <p>{{ task.latestHandoff.operatorName }}于 {{ formatTaskDateTime(task.latestHandoff.occurredAt) }} 转交 · {{ task.latestHandoff.versionNumber }} 退回后</p>
        <p>原因：{{ task.latestHandoff.reason }}</p>
        <p v-if="task.latestHandoff.handoffNote">交接说明：{{ task.latestHandoff.handoffNote }}</p>
      </el-alert>

      <ProjectStatePanel
        v-if="actionError"
        compact
        :title="actionError.title"
        :message="actionError.message"
        :retryable="actionError.retryable"
        @retry="loadDetail"
      />

      <el-alert
        v-if="isWaitingForStart"
        :title="task.expectedStartTime && task.expectedEndTime ? '等待管理人员确认开工' : '待排期：等待管理人员设置计划起止时间'"
        :description="isShotTask
          ? '任务已分配。管理人员确认所需资产齐备并开始任务后，制作目录就绪即可提交版本。'
          : '任务已分配。管理人员确认该制作分项的开工条件齐备并开始任务后，制作目录就绪即可提交版本；同一资产的其他分项独立确认。'"
        type="info"
        :closable="false"
        show-icon
      />

      <ProjectStatePanel
        v-if="assetTargetIncomplete"
        compact
        title="资产任务资料不完整"
        message="该任务尚未填写制作分项，因此不能开始或提交版本。请联系项目管理人进入资产详情补齐制作分项；无需重新创建任务。"
      />

      <section class="task-detail-grid">
        <el-card v-if="task.projectReferenceDescription?.trim() || task.projectReferenceFiles?.length" class="task-card task-card--wide" shadow="never" data-testid="project-references">
          <header><div><p class="sg-eyebrow">PROJECT REFERENCES</p><h3>项目资料</h3></div></header>
          <p v-if="task.projectReferenceDescription" class="task-requirements">{{ task.projectReferenceDescription }}</p>
          <ReviewReferenceFiles v-if="task.projectReferenceFiles?.length" :files="task.projectReferenceFiles" />
        </el-card>

        <el-card class="task-card task-card--wide" shadow="never" data-testid="task-requirements">
          <header><div><p class="sg-eyebrow">BRIEF</p><h3>制作要求</h3></div><div class="brief-actions"><el-button v-if="targetRoute && !embedded" link type="primary" @click="router.push(targetRoute)">查看{{ taskKindMeta(task.taskKind).shortLabel }}详情</el-button><el-tag :type="tagTypeFromTone(taskPriorityMeta(task.priority).tone)" size="small" effect="plain" round>{{ taskPriorityMeta(task.priority).label }}优先级</el-tag></div></header>
          <template v-if="isShotTask">
            <ShotProductionInfo v-if="shotProduction" :shot="shotProduction" :reference-files="task.referenceFiles" :reference-description="task.referenceDescription" />
            <p v-else class="task-requirements">{{ task.requirements || task.target.targetDescription || '暂无镜头制作信息。' }}</p>
            <section v-if="hasAdditionalShotRequirements" class="task-additional-requirements" aria-label="任务补充要求">
              <strong>任务补充要求</strong>
              <p>{{ task.requirements }}</p>
            </section>
          </template>
          <template v-else>
            <p class="task-requirements">{{ task.requirements || '暂无额外制作要求。' }}</p>
            <section v-if="task.referenceDescription || task.referenceFiles?.length" class="task-additional-requirements" aria-label="分项参考资料">
              <strong>参考资料</strong>
              <p v-if="task.referenceDescription" class="task-requirements">{{ task.referenceDescription }}</p>
              <ReviewReferenceFiles v-if="task.referenceFiles?.length" :files="task.referenceFiles" />
            </section>
          </template>
          <el-descriptions class="task-fields" :column="4" border>
            <el-descriptions-item label="主制作人">{{ taskAssigneeLabel(task.assignee) }}</el-descriptions-item>
            <el-descriptions-item label="计划起止时间" :span="2"><TaskTimeReminder :task="task" :now="currentTime" /></el-descriptions-item>
            <el-descriptions-item label="已提交版本">{{ task.versionCount }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card id="version-workspace" class="task-card task-card--wide version-workspace-anchor" shadow="never" data-testid="version-workspace-anchor">
          <VersionWorkspace
            :task-id="task.taskId"
            :task-kind="task.taskKind"
            :task-status="task.taskStatus"
            :version-count="Number(task.versionCount || 0)"
            :latest-version-no="Number(task.latestVersion?.versionNo || 0)"
            :production-description="versionProductionDescription"
            :open-issues="openIssues"
            :allowed-actions="task.allowedActions"
            :has-uncommitted-submission="task.hasUncommittedSubmission"
            :operation-generation="routeContext.operationGeneration"
            @committed="handleVersionCommitted"
          />
        </el-card>

        <el-card class="task-card task-card--wide" shadow="never">
          <p class="sg-eyebrow">AUDIT</p>
          <h3>审计与备注</h3>
          <p class="task-remark">{{ task.remark || '暂无内部备注。' }}</p>
          <el-descriptions class="task-fields" :column="4" border>
            <el-descriptions-item label="创建人">{{ task.createBy }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTaskDateTime(task.createTime) }}</el-descriptions-item>
            <el-descriptions-item label="更新人">{{ task.updateBy }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatTaskDateTime(task.updateTime) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </section>

      <TaskEditDialog
        v-if="showEdit && editContext"
        :task="editContext.task"
        :operation-generation="editContext.operationGeneration"
        @close="closeEditDialog"
        @saved="handleSaved"
        @refresh="handleEditRefresh"
      />
    </template>
  </section>
</template>

<style scoped>
.brief-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.task-detail-page{display:grid;gap:18px}.back-link{display:inline-flex;width:max-content;gap:7px;align-items:center;padding:0;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0}.back-link:hover{color:var(--sg-text)}.task-detail-loading{display:grid;min-height:360px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg);place-items:center}.task-hero{display:flex;gap:24px;align-items:center;justify-content:space-between;padding:26px;background:linear-gradient(135deg,rgba(255,182,87,.075),transparent 42%),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg)}.task-hero__main{min-width:0}.task-hero__title{display:flex;gap:12px;align-items:center}.task-hero h2,.task-hero p{margin:0}.task-hero h2{font-size:clamp(23px,3vw,31px);letter-spacing:-.025em}.task-hero__main>p:not(.sg-eyebrow){margin-top:9px;color:var(--sg-text-secondary);font-size:13px}.task-hero small{display:block;margin-top:8px;color:var(--sg-text-muted)}.task-hero__actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}.task-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.task-card{padding:21px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.task-card--wide{grid-column:1/-1}.task-card header{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.task-card h3,.task-card p{margin:0}.task-card h3{margin-bottom:16px;font-size:17px}.task-card>strong{display:block;font-size:16px}.task-card>strong+p{margin-top:7px;color:var(--sg-text-secondary);font-size:12px;line-height:1.7}.task-requirements,.task-remark,.version-workspace-anchor>p:not(.sg-eyebrow){color:var(--sg-text-secondary);font-size:13px;line-height:1.8;white-space:pre-wrap}.task-additional-requirements{display:grid;gap:6px;margin-top:12px;padding:12px 14px;background:var(--sg-accent-soft);border-radius:9px}.task-additional-requirements strong{color:var(--sg-accent);font-size:11px}.task-additional-requirements p{color:var(--sg-text-secondary);font-size:12px;line-height:1.7;white-space:pre-wrap}.version-workspace-anchor{background:linear-gradient(135deg,rgba(93,176,255,.055),transparent 46%),var(--sg-surface)}.version-workspace-anchor code{color:var(--sg-accent)}.task-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:16px 0 0;overflow:hidden;background:var(--sg-border);border-radius:9px}.task-fields--four{grid-template-columns:repeat(4,minmax(0,1fr))}.task-fields div{padding:13px;background:rgba(13,16,21,.92)}dt{color:var(--sg-text-muted);font-size:10px}dd{margin:5px 0 0;color:var(--sg-text-secondary);font-size:12px;overflow-wrap:anywhere}.text-action{margin-top:15px;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.version-number{display:inline!important;margin-right:9px;color:var(--sg-accent);font-size:25px!important}.task-empty{padding:20px;color:var(--sg-text-muted);font-size:12px;text-align:center;background:rgba(255,255,255,.02);border:1px dashed var(--sg-border);border-radius:9px}.final-version-tag{margin-top:14px}@media(max-width:820px){.task-hero{align-items:flex-start;flex-direction:column}.task-hero__actions{justify-content:flex-start}.task-fields--four{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.task-detail-grid{grid-template-columns:1fr}.task-card--wide{grid-column:auto}.task-fields,.task-fields--four{grid-template-columns:1fr}.task-hero__title{align-items:flex-start;flex-direction:column}}
.task-detail-page.task-detail-page--embedded { padding: 0; }
.task-card.el-card{padding:0;overflow:visible;background:var(--sg-surface);border-color:var(--sg-border)}
.task-card > :deep(.el-card__body){padding:16px}
.version-workspace-anchor > :deep(.el-card__body) { overflow: visible; }
.task-card:deep(.el-card__body)>strong{display:block;font-size:16px}
.task-card:deep(.el-card__body)>strong+p{margin-top:7px;color:var(--sg-text-secondary);font-size:12px;line-height:1.7}
.version-workspace-anchor:deep(.el-card__body)>p:not(.sg-eyebrow){color:var(--sg-text-secondary);font-size:13px;line-height:1.8;white-space:pre-wrap}
.task-detail-loading.el-card{display:block;padding:0}
.task-detail-loading:deep(.el-card__body){width:100%;box-sizing:border-box;padding:28px}
.task-detail-loading__label{display:block;margin-bottom:18px;color:var(--sg-text-secondary);font-size:13px}
.task-fields.el-descriptions{display:block;margin-top:16px;background:transparent}
.task-fields:deep(.el-descriptions__body),.task-fields:deep(.el-descriptions__table){background:transparent}
.task-fields:deep(.el-descriptions__cell){padding:13px!important;background:rgba(13,16,21,.92)!important;border-color:var(--sg-border)!important}
.task-fields:deep(.el-descriptions__label){color:var(--sg-text-muted)!important;font-size:10px}
.task-fields:deep(.el-descriptions__content){color:var(--sg-text-secondary)!important;font-size:12px;overflow-wrap:anywhere}
.task-empty.el-empty{min-height:132px;padding:12px;background:rgba(255,255,255,.02)}
.task-fields:deep(.el-descriptions__cell) { background: var(--sg-surface-raised) !important; }
</style>
