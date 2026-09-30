<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useDetailNavigation } from '@/composables/useDetailNavigation'
import { Refresh, Right } from '@element-plus/icons-vue'
import { taskPriorityMeta, taskStatusMeta } from '@/views/task/taskPresentation'
import TaskTimeReminder from '@/views/task/components/TaskTimeReminder.vue'
import { useCurrentTime } from '@/composables/useCurrentTime'

import { getProductionHistory } from '@/api/shot-grid/productionHistory'
import {
  PRODUCTION_HISTORY_STEPS,
  actorDisplayName,
  assigneeDisplayName,
  assertProductionHistoryData,
  currentProductionHandoff,
  eventsForLane,
  expandProductionTimeline,
  formatHistoryDateTime,
  historyEventMeta,
  historyImportBatchStatusMeta,
  historyReviewActionMeta,
  historyStageMeta,
  historyTagType,
  historyVersionStatusMeta,
  productionHistoryActiveStep,
  productionHistoryStage,
  productionHistoryErrorState
} from './productionHistoryPresentation'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  subjectId: { type: [Number, String], required: true },
  subjectType: {
    type: String,
    required: true,
    validator: value => ['shot', 'asset'].includes(value)
  },
  refreshKey: { type: [Number, String], default: 0 }
})

const navigate = useDetailNavigation()
const currentTime = useCurrentTime()
const history = ref(null)
const loading = ref(false)
const errorState = ref(null)
const selectedLaneKey = ref('')

let controller = null
let loadGeneration = 0
let disposed = false
let contextKey = ''

const isAsset = computed(() => props.subjectType === 'asset')
const lanes = computed(() => Array.isArray(history.value?.lanes) ? history.value.lanes : [])
const allAssetLanesSelected = computed(() => isAsset.value && selectedLaneKey.value === 'all')
const selectedLane = computed(() => {
  if (!history.value) return null
  if (!isAsset.value) return lanes.value[0] || null
  return lanes.value.find(lane => String(lane.laneId) === selectedLaneKey.value) || null
})
const stageSource = computed(() => selectedLane.value || history.value?.summary || null)
const currentStage = computed(() => productionHistoryStage(stageSource.value))
const activeStep = computed(() => productionHistoryActiveStep(currentStage.value, stageSource.value?.activeStep))
const currentStageMeta = computed(() => historyStageMeta(currentStage.value))
const currentAssignee = computed(() => assigneeDisplayName(selectedLane.value?.task?.assignee))
const currentHandoff = computed(() => currentProductionHandoff(selectedLane.value))
const selectedEvents = computed(() => expandProductionTimeline(eventsForLane(history.value?.events, selectedLane.value?.laneId)))
const metrics = computed(() => {
  const source = selectedLane.value || history.value?.summary || {}
  return [
    { key: 'versions', label: '版本', value: Number(source.versionCount || 0) },
    { key: 'rejections', label: '退回', value: Number(source.rejectionCount || 0) },
    { key: 'issues', label: '修改问题', value: Number(source.issueCount || 0) },
    { key: 'openIssues', label: '未解决', value: Number(source.openIssueCount || 0) },
    { key: 'finals', label: '最终版本', value: Number(source.finalVersionCount || (source.finalVersion ? 1 : 0)) }
  ]
})

function isCanceled(error, requestController) {
  return requestController.signal.aborted || error?.code === 'ERR_CANCELED'
}

function syncLaneSelection({ reset = false } = {}) {
  if (!isAsset.value) {
    selectedLaneKey.value = lanes.value[0]?.laneId == null ? '' : String(lanes.value[0].laneId)
    return
  }
  const currentExists = !reset && lanes.value.some(lane => String(lane.laneId) === selectedLaneKey.value)
  if (!currentExists) selectedLaneKey.value = 'all'
}

async function loadHistory({ resetLane = false } = {}) {
  const generation = ++loadGeneration
  controller?.abort()
  errorState.value = null
  const targetProjectId = Number(props.projectId)
  const targetSubjectId = Number(props.subjectId)
  const targetSubjectType = props.subjectType
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  const isCurrent = () => (
    !disposed &&
    controller === requestController &&
    generation === loadGeneration &&
    !requestController.signal.aborted &&
    Number(props.projectId) === targetProjectId &&
    Number(props.subjectId) === targetSubjectId &&
    props.subjectType === targetSubjectType
  )
  try {
    const response = await getProductionHistory(
      targetProjectId,
      targetSubjectType,
      targetSubjectId,
      { signal: requestController.signal }
    )
    if (!isCurrent()) return
    history.value = assertProductionHistoryData(response.data, targetSubjectType)
    syncLaneSelection({ reset: resetLane })
  } catch (error) {
    if (!isCanceled(error, requestController) && isCurrent()) {
      errorState.value = productionHistoryErrorState(error, targetSubjectType)
    }
  } finally {
    if (controller === requestController && generation === loadGeneration) {
      controller = null
      loading.value = false
    }
  }
}

function handleContextChange() {
  const nextContextKey = `${props.subjectType}:${props.projectId}:${props.subjectId}`
  const changed = nextContextKey !== contextKey
  if (changed) {
    contextKey = nextContextKey
    history.value = null
    selectedLaneKey.value = ''
  }
  void loadHistory({ resetLane: changed })
}

function positiveId(value) {
  const result = Number(value)
  return Number.isSafeInteger(result) && result > 0 ? result : null
}

function routeForResource(resourceRef) {
  const id = positiveId(resourceRef?.resourceId)
  if (!id) return null
  if (resourceRef.resourceType === 'task') return { name: 'task-detail', params: { taskId: id } }
  if (resourceRef.resourceType === 'version') return { name: 'version-detail', params: { versionId: id } }
  if (resourceRef.resourceType === 'reviewList') return { name: 'review-detail', params: { reviewListId: id } }
  if (resourceRef.resourceType === 'shot') {
    return { name: 'shot-detail', params: { projectId: positiveId(props.projectId), shotId: id } }
  }
  if (resourceRef.resourceType === 'asset') {
    return { name: 'asset-detail', params: { projectId: positiveId(props.projectId), assetId: id } }
  }
  return null
}

function resourceActionLabel(resourceType) {
  return ({
    task: '查看任务',
    version: '查看版本',
    reviewList: '查看审核单',
    shot: '查看镜头',
    asset: '查看资产'
  })[resourceType] || ''
}

function showEventResourceAction(event) {
  if (event?.eventType === 'subject_created') return false
  return Boolean(routeForResource(event?.resourceRef))
}

function openResource(resourceRef) {
  if (resourceRef?.resourceType === 'assetItem') {
    const lane = lanes.value.find(item => String(item.laneId) === String(resourceRef.resourceId))
    if (lane) selectedLaneKey.value = String(lane.laneId)
    return
  }
  const target = routeForResource(resourceRef)
  if (target) void navigate(target)
}

function reviewListRef(cycle) {
  const reviewListId = positiveId(cycle?.autoReviewList?.reviewListId)
  return reviewListId ? { resourceType: 'reviewList', resourceId: reviewListId } : null
}

function selectLane(laneId) {
  selectedLaneKey.value = String(laneId)
}

watch(
  () => [props.projectId, props.subjectId, props.subjectType, props.refreshKey],
  handleContextChange,
  { immediate: true }
)

onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  controller?.abort()
})

defineExpose({ refresh: loadHistory })
function cycleFiles(cycle) {
  return cycle.files?.length ? cycle.files : cycle.primaryFile ? [cycle.primaryFile] : []
}
function taskForEvent(event) {
  return lanes.value.find(lane => Number(lane.task?.taskId) === Number(event.resourceRef?.resourceId))?.task
}

</script>

<template>
  <el-card class="production-history" shadow="never" aria-label="制作履历">
    <template #header>
      <header class="production-history__heading">
        <div>
          <p class="sg-eyebrow">PRODUCTION HISTORY</p>
          <h3>制作履历</h3>
          <p>串联可确认的创建或导入、委派、制作、版本提交与审核记录；没有独立审计证据的动作不会被补写。</p>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadHistory()">刷新履历</el-button>
      </header>
    </template>

    <el-skeleton v-if="loading && !history" :rows="8" animated aria-label="正在加载制作履历" />

    <section v-else-if="errorState && !history" class="production-history__state">
      <el-alert :title="errorState.title" :description="errorState.message" type="error" :closable="false" show-icon />
      <el-button v-if="errorState.retryable" :icon="Refresh" @click="loadHistory()">重试</el-button>
    </section>

    <template v-else-if="history">
      <el-alert
        v-if="errorState"
        class="production-history__refresh-error"
        title="履历刷新失败，当前仍显示上一次成功结果"
        :description="errorState.message"
        type="warning"
        :closable="false"
        show-icon
      />

      <el-tabs v-if="isAsset" v-model="selectedLaneKey" class="history-lane-tabs">
        <el-tab-pane label="全部分项" name="all" />
        <el-tab-pane v-for="lane in lanes" :key="lane.laneId" :name="String(lane.laneId)">
          <template #label>
            <span class="history-lane-tab-label">
              <span>{{ lane.name }}</span>
              <el-tag v-if="lane.lifecycleStatus === 'archived'" type="info" size="small" effect="plain" round>已归档</el-tag>
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <section class="history-stage" :aria-busy="loading">
        <header class="history-stage__heading">
          <div class="history-stage__identity">
            <strong>{{ allAssetLanesSelected ? '资产整体进度' : selectedLane?.name || history.subject.name }}</strong>
            <span v-if="selectedLane?.task">制作负责人：{{ currentAssignee }}</span>
          </div>
          <div class="history-metrics">
            <el-statistic v-for="metric in metrics" :key="metric.key" :title="metric.label" :value="metric.value" />
          </div>
          <div class="history-stage__tags">
            <slot v-if="selectedLane" name="lane-actions" :lane="selectedLane" :loading="loading" />
            <el-tag v-if="selectedLane?.lifecycleStatus === 'archived'" type="info" effect="plain" round>已归档</el-tag>
            <el-tag :type="historyTagType(currentStageMeta)" effect="plain" round>{{ currentStageMeta.label }}</el-tag>
          </div>
        </header>
        <section v-if="currentHandoff" class="history-handoff" aria-label="当前流转状态">
          <span class="history-handoff__stage">当前环节 <el-tag :type="currentHandoff.type === 'error' ? 'warning' : currentHandoff.type" size="small" effect="light" round>{{ currentHandoff.stage }}</el-tag></span>
          <span v-if="selectedLane?.task" class="history-handoff__stage">任务状态 <el-tag :type="historyTagType(taskStatusMeta(selectedLane.task))" size="small" effect="light" round>{{ taskStatusMeta(selectedLane.task).label }}</el-tag></span>
          <strong class="history-handoff__owner">{{ currentHandoff.owner }}</strong>
          <span class="history-handoff__next">下一步：{{ currentHandoff.next }}</span>
        </section>
        <el-alert v-else-if="allAssetLanesSelected" class="history-handoff" type="info" :closable="false" title="各制作分项独立流转，请选择具体分项查看当前处理方与下一步。" show-icon />
        <el-steps class="history-stage__steps" :active="activeStep" align-center finish-status="success" :process-status="currentStage === 'final' ? 'success' : 'process'" aria-label="制作阶段">
          <el-step v-for="step in PRODUCTION_HISTORY_STEPS" :key="step" :title="step" />
        </el-steps>
      </section>

      <section v-if="allAssetLanesSelected" class="history-lane-summary">
        <el-empty v-if="!lanes.length" :image-size="64" description="该资产还没有制作分项" />
        <el-table v-else :data="lanes" row-key="laneId" stripe aria-label="资产制作分项履历汇总">
          <el-table-column label="制作分项" min-width="210">
            <template #default="{ row }">
              <span class="history-lane-name">
                <span>{{ row.name }}</span>
                <el-tag v-if="row.lifecycleStatus === 'archived'" type="info" size="small" effect="plain" round>已归档</el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="当前阶段" width="120">
            <template #default="{ row }"><el-tag :type="historyTagType(historyStageMeta(row))" effect="plain" round>{{ historyStageMeta(row).label }}</el-tag></template>
          </el-table-column>
          <el-table-column label="负责人" min-width="130">
            <template #default="{ row }">{{ assigneeDisplayName(row.task?.assignee) }}</template>
          </el-table-column>
          <el-table-column label="版本 / 退回" width="120">
            <template #default="{ row }">{{ row.versionCount || 0 }} / {{ row.rejectionCount || 0 }}</template>
          </el-table-column>
          <el-table-column label="问题 / 未解决" width="130">
            <template #default="{ row }">{{ row.issueCount || 0 }} / {{ row.openIssueCount || 0 }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="right">
            <template #default="{ row }"><el-button link type="primary" :icon="Right" @click="selectLane(row.laneId)">查看履历</el-button></template>
          </el-table-column>
        </el-table>
      </section>

      <section v-else class="history-timeline" aria-label="制作履历时间线">
        <el-empty v-if="!selectedLane" :image-size="64" description="当前对象没有可展示的制作任务" />
        <el-empty v-else-if="!selectedEvents.length" :image-size="64" description="当前分项还没有可确认的履历记录" />
        <el-timeline v-else mode="start">
          <el-timeline-item
            v-for="(event, eventIndex) in selectedEvents"
            :key="event.eventId"
            :timestamp="formatHistoryDateTime(event.occurredAt)"
            :type="eventIndex === 0 ? 'warning' : 'success'"
            size="large"
            placement="top"
          >
            <el-card class="history-event" :class="{ 'history-event--version': event.versionCycle }" shadow="always">
              <header v-if="!event.versionCycle" class="history-event__heading">
                <div>
                  <span class="history-event__title-row">
                    <strong>{{ event.title }}</strong>
                    <el-tag :type="historyTagType(historyEventMeta(event.eventType))" size="small" effect="plain" round>{{ historyEventMeta(event.eventType).label }}</el-tag>
                    <el-tag v-if="event.evidenceLevel === 'inferred'" type="info" size="small" effect="plain" round>按现有记录推断</el-tag>
                  </span>
                  <small v-if="event.eventType !== 'task_created'">{{ actorDisplayName(event.actor) }}</small>
                </div>
                <el-button
                  v-if="showEventResourceAction(event)"
                  link
                  type="primary"
                  :icon="Right"
                  @click="openResource(event.resourceRef)"
                >{{ resourceActionLabel(event.resourceRef.resourceType) }}</el-button>
              </header>
              <p v-if="event.description && !event.versionCycle" class="history-event__description">{{ event.description }}</p>
              <el-descriptions v-if="event.eventType === 'task_created' && taskForEvent(event)" class="event-import" :column="2" border size="small">
                <el-descriptions-item label="任务创建人">{{ event.actor ? actorDisplayName(event.actor) : '未记录' }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ formatHistoryDateTime(event.occurredAt) }}</el-descriptions-item>
                <el-descriptions-item label="任务名称">{{ taskForEvent(event).taskName }}</el-descriptions-item>
                <el-descriptions-item label="当前制作人">{{ assigneeDisplayName(taskForEvent(event).assignee) }}</el-descriptions-item>
                <el-descriptions-item label="当前优先级" :span="2"><el-tag :type="historyTagType(taskPriorityMeta(taskForEvent(event).priority))" size="small" effect="plain" round>{{ taskPriorityMeta(taskForEvent(event).priority).label }}</el-tag></el-descriptions-item>
                <el-descriptions-item label="当前计划制作时间" :span="2"><TaskTimeReminder :task="taskForEvent(event)" :now="currentTime" compact /></el-descriptions-item>
              </el-descriptions>

              <template v-if="event.importBatch">
                <el-descriptions class="event-import" :column="3" border>
                  <el-descriptions-item label="来源文件">{{ event.importBatch.originalFileName }}</el-descriptions-item>
                  <el-descriptions-item label="批次状态">
                    <el-tag :type="historyTagType(historyImportBatchStatusMeta(event.importBatch.batchStatus))" size="small" effect="plain" round>
                      {{ historyImportBatchStatusMeta(event.importBatch.batchStatus).label }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="提交时间">{{ formatHistoryDateTime(event.importBatch.committedTime) }}</el-descriptions-item>
                </el-descriptions>
              </template>

              <section v-if="event.reviewAction" class="version-cycle review-action">
                <header class="version-cycle__heading">
                  <div>
                    <strong>{{ event.versionCycle.versionNumber }} 审核</strong>
                    <el-tag :type="historyTagType(historyReviewActionMeta(event.reviewAction.actionType))" size="small" effect="light" round>{{ historyReviewActionMeta(event.reviewAction.actionType).label }}</el-tag>
                  </div>
                  <el-button v-if="reviewListRef(event.versionCycle)" size="small" type="primary" :icon="Right" @click="openResource(reviewListRef(event.versionCycle))">查看审核</el-button>
                </header>
                <div class="version-cycle__meta"><span>审核人：{{ actorDisplayName(event.reviewAction.reviewer) }}</span></div>
                <p v-if="event.reviewAction.reason?.trim()">{{ event.reviewAction.reason }}</p>
                <span v-if="event.versionCycle.sourceIssues?.length" class="version-cycle__summary">本版累计 {{ event.versionCycle.sourceIssues.length }} 条修改意见（含后续补充）</span>
              </section>
              <template v-else-if="event.versionCycle">
                <section class="version-cycle">
                  <header class="version-cycle__heading">
                    <div>
                      <strong>{{ event.versionCycle.versionNumber }} 提交</strong>
                      <el-tag :type="historyTagType(historyVersionStatusMeta(event.versionCycle.versionStatus))" size="small" effect="plain" round>当前：{{ historyVersionStatusMeta(event.versionCycle.versionStatus).label }}</el-tag>
                      <el-tag v-if="cycleFiles(event.versionCycle).length" type="info" size="small" effect="plain" round>{{ cycleFiles(event.versionCycle).length }} 个文件</el-tag>
                    </div>
                    <div class="version-cycle__actions">
                      <el-button size="small" plain type="primary" :icon="Right" @click="openResource({ resourceType: 'version', resourceId: event.versionCycle.versionId })">查看作品</el-button>
                      <el-button v-if="!event.versionCycle.reviewActions?.length && reviewListRef(event.versionCycle)" size="small" type="primary" :icon="Right" @click="openResource(reviewListRef(event.versionCycle))">查看审核</el-button>
                    </div>
                  </header>
                  <div class="version-cycle__meta">
                    <span>提交人：{{ actorDisplayName(event.versionCycle.submitter) }}</span>
                    <span v-if="event.versionCycle.issueResponses?.length" class="version-cycle__summary">已提交 {{ event.versionCycle.issueResponses.length }} 条处理说明</span>
                  </div>
                  <p>{{ event.versionCycle.changelog || '本版未填写整体修改说明。' }}</p>


                </section>
              </template>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </section>
    </template>
  </el-card>
</template>

<style scoped lang="scss">
.production-history {
  --el-card-bg-color: var(--sg-surface);
  --el-card-border-color: var(--sg-border);
  border-radius: var(--sg-radius-lg);
}

.production-history:deep(.el-card__header) { padding: 18px 22px; border-bottom-color: var(--sg-border); }
.production-history:deep(.el-card__body) { padding: 22px; }
.production-history__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.production-history__heading h3 { margin: 3px 0 5px; font-size: 20px; }
.production-history__heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.production-history__state { display: grid; min-height: 180px; align-content: center; gap: 14px; }
.production-history__state .el-button { justify-self: center; }
.production-history__refresh-error { margin-bottom: 16px; }
.history-lane-tabs { margin: -8px 0 16px; }
.history-lane-tabs:deep(.el-tabs__header) { margin-bottom: 0; }
.history-lane-tab-label,
.history-lane-name,
.history-stage__tags { display: inline-flex; align-items: center; gap: 7px; }
.history-stage { padding: 20px; background: var(--sg-surface-raised); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.history-stage__heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.history-stage__identity { display: flex; min-width: 0; align-items: baseline; gap: 10px; }
.history-stage__heading strong { overflow: hidden; font-size: 16px; text-overflow: ellipsis; white-space: nowrap; }
.history-stage__heading span { color: var(--sg-text-muted); font-size: 11px; }
.history-stage__tags { flex: 0 0 auto; }
.history-stage__steps { --el-color-primary: var(--sg-accent); }
.history-handoff { display: flex; align-items: center; justify-content: center; gap: 10px 18px; margin-bottom: 20px; padding: 10px 14px; background: var(--sg-accent-soft); border-radius: 6px; font-size: 12px; line-height: 1.6; text-align: center; }
.history-handoff__stage { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 8px; color: var(--sg-text-secondary); }
.history-handoff__owner { flex: 0 0 auto; color: var(--sg-text); font-size: 13px; }
.history-handoff__next { color: var(--sg-text-secondary); }
@media (max-width: 850px) { .history-handoff { flex-wrap: wrap; } }
.history-stage__steps:deep(.el-step__icon) { width: 28px; height: 28px; background: var(--sg-surface-raised); border-width: 2px; }
.history-stage__steps:deep(.el-step__icon-inner) { font-size: 11px; font-weight: 700; }
.history-stage__steps:deep(.el-step__line) { top: 13px; height: 2px; background: var(--sg-border-strong); }
.history-stage__steps:deep(.el-step__line-inner) { border-width: 1px !important; }
.history-stage__steps:deep(.el-step__main) { padding-top: 8px; }
.history-stage__steps:deep(.el-step__title) { color: var(--sg-text-secondary); font-size: 12px; line-height: 1.35; }
.history-stage__steps:deep(.el-step__title.is-process) { color: var(--sg-text); }
.history-stage__steps:deep(.el-step__title.is-success) { color: var(--el-color-success); }
.history-stage__steps:deep(.el-step__head.is-process) { color: var(--sg-accent); border-color: var(--sg-accent); }
.history-stage__steps:deep(.el-step__head.is-success) { color: var(--el-color-success); border-color: var(--el-color-success); }
.history-metrics { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px; margin-left: auto; }
.history-metrics:deep(.el-statistic) { display: inline-flex; align-items: baseline; gap: 8px; }
.history-metrics:deep(.el-statistic__head) { margin: 0; color: var(--sg-text-muted); font-size: 12px; line-height: 1.5; }
.history-metrics:deep(.el-statistic__content) { line-height: 1.5; }
.history-metrics:deep(.el-statistic__number) { color: var(--sg-text); font-size: 15px; font-weight: 600; }
.history-lane-summary,
.history-timeline { margin-top: 20px; }
.history-lane-summary:deep(.el-table) { --el-table-bg-color: var(--sg-surface); --el-table-tr-bg-color: var(--sg-surface); --el-table-header-bg-color: var(--sg-surface-raised); --el-table-border-color: var(--sg-border); --el-table-text-color: var(--sg-text-secondary); --el-table-header-text-color: var(--sg-text-muted); }
.history-timeline:deep(.el-timeline) { margin: 0; padding: 2px 0 0; }
.history-timeline:deep(.el-timeline-item) { padding-bottom: 18px; }
.history-timeline:deep(.el-timeline-item:last-child) { padding-bottom: 0; }
.history-timeline:deep(.el-timeline-item__tail) { border-left: 2px solid var(--sg-border-strong); }
.history-timeline:deep(.el-timeline-item__node--large) { box-shadow: 0 0 0 4px var(--sg-surface); }
.history-timeline:deep(.el-timeline-item__wrapper) { top: -5px; }
.history-timeline:deep(.el-timeline-item__timestamp) { margin-bottom: 7px; color: var(--sg-text-muted); font-size: 10px; font-variant-numeric: tabular-nums; line-height: 1.4; }
.history-event { text-align: left; --el-card-bg-color: var(--sg-surface-raised); --el-card-border-color: var(--sg-border); --el-box-shadow-light: 0 3px 12px rgba(35, 45, 57, 0.08); border-radius: 10px; }
.history-event:deep(.el-card__body) { padding: 14px 16px; }
.history-event--version { --el-card-border-color: color-mix(in srgb, var(--sg-accent) 32%, var(--sg-border)); }
.history-event--version:deep(> .el-card__body) { padding: 10px 12px; }
.history-event__heading,
.version-cycle__heading { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; }
.history-event__title-row,
.version-cycle__heading > div { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.history-event__heading small,
.version-cycle__heading > span { color: var(--sg-text-muted); font-size: 9px; }
.history-event__description { margin: 10px 0 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.6; }
.event-import { margin-top: 13px; }
.event-import:deep(.el-descriptions__body),
.event-import:deep(.el-descriptions__cell) { background: var(--sg-surface) !important; border-color: var(--sg-border) !important; }
.event-import:deep(.el-descriptions__label) { color: var(--sg-text-muted); font-size: 9px; }
.event-import:deep(.el-descriptions__content) { color: var(--sg-text-secondary); font-size: 10px; overflow-wrap: anywhere; }
.version-cycle { display: grid; margin-top: 0; gap: 6px; }
.version-cycle__meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 20px; font-size: 12px; line-height: 1.5; }
.version-cycle__summary { color: var(--sg-text-muted); font-size: 12px; }
.version-cycle__heading strong { font-size: 20px; }
.version-cycle__status--pending { --el-tag-bg-color: var(--sg-accent); --el-tag-border-color: var(--sg-accent); --el-tag-text-color: #fff; color: #fff; padding: 0 10px; font-size: 12px; font-weight: 700; }
.version-cycle > p { margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.7; }
.version-cycle__actions { display: flex; flex: 0 0 auto; }

@media (max-width: 850px) {
}

@media (max-width: 620px) {
  .production-history__heading,
  .history-stage__heading,
  .history-event__heading,
  .version-cycle__heading { align-items: stretch; flex-direction: column; }
  .history-stage__identity { align-items: flex-start; flex-direction: column; }
  .history-metrics { margin-left: 0; column-gap: 16px; }
}
</style>
