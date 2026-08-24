<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Right } from '@element-plus/icons-vue'

import { getProductionHistory } from '@/api/shot-grid/productionHistory'
import {
  PRODUCTION_HISTORY_STEPS,
  actorDisplayName,
  assigneeDisplayName,
  assertProductionHistoryData,
  eventsForLane,
  formatHistoryDateTime,
  formatHistoryFileSize,
  historyEventMeta,
  historyImportBatchStatusMeta,
  historyIssueStatusMeta,
  historyReviewActionMeta,
  historyStageMeta,
  historyTagType,
  historyVerificationMeta,
  historyVersionStatusMeta,
  historyWorkflowStatusLabel,
  productionHistoryActiveStep,
  productionHistoryErrorState,
  sourceIssueSummary
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

const router = useRouter()
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
const currentStage = computed(() => String(stageSource.value?.currentStage || 'created'))
const activeStep = computed(() => productionHistoryActiveStep(currentStage.value, stageSource.value?.activeStep))
const currentStageMeta = computed(() => historyStageMeta(currentStage.value))
const currentAssignee = computed(() => assigneeDisplayName(selectedLane.value?.task?.assignee))
const selectedEvents = computed(() => eventsForLane(history.value?.events, selectedLane.value?.laneId))
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
  if (target) void router.push(target)
}

function reviewListRef(cycle) {
  const reviewListId = positiveId(cycle?.autoReviewList?.reviewListId)
  return reviewListId ? { resourceType: 'reviewList', resourceId: reviewListId } : null
}

function hasVersionDetails(cycle) {
  return Boolean(
    cycle?.reviewActions?.length ||
    cycle?.sourceIssues?.length ||
    cycle?.issueResponses?.length ||
    cycle?.issueVerifications?.length
  )
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
          <div>
            <strong>{{ allAssetLanesSelected ? '资产整体进度' : selectedLane?.name || history.subject.name }}</strong>
            <span v-if="selectedLane?.task">当前负责人：{{ currentAssignee }}</span>
          </div>
          <div class="history-stage__tags">
            <el-tag v-if="selectedLane?.lifecycleStatus === 'archived'" type="info" effect="plain" round>已归档</el-tag>
            <el-tag :type="historyTagType(currentStageMeta)" effect="plain" round>{{ currentStageMeta.label }}</el-tag>
          </div>
        </header>
        <el-steps class="history-stage__steps" :active="activeStep" align-center finish-status="success" :process-status="currentStage === 'final' ? 'success' : currentStage === 'revision' ? 'error' : 'process'" aria-label="制作阶段">
          <el-step v-for="step in PRODUCTION_HISTORY_STEPS" :key="step" :title="step" />
        </el-steps>
        <div class="history-metrics">
          <el-statistic v-for="metric in metrics" :key="metric.key" :title="metric.label" :value="metric.value" />
        </div>
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
            <template #default="{ row }"><el-tag :type="historyTagType(historyStageMeta(row.currentStage))" effect="plain" round>{{ historyStageMeta(row.currentStage).label }}</el-tag></template>
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
        <el-timeline v-else>
          <el-timeline-item
            v-for="event in selectedEvents"
            :key="event.eventId"
            :timestamp="formatHistoryDateTime(event.occurredAt)"
            :type="historyEventMeta(event.eventType).timelineType"
            size="large"
            :hollow="event.evidenceLevel === 'inferred'"
            placement="top"
          >
            <el-card class="history-event" :class="{ 'history-event--version': event.eventType === 'version_cycle' }" shadow="never">
              <header class="history-event__heading">
                <div>
                  <span class="history-event__title-row">
                    <strong>{{ event.title }}</strong>
                    <el-tag :type="historyTagType(historyEventMeta(event.eventType))" size="small" effect="plain" round>{{ historyEventMeta(event.eventType).label }}</el-tag>
                    <el-tag v-if="event.evidenceLevel === 'inferred'" type="info" size="small" effect="plain" round>按现有记录推断</el-tag>
                  </span>
                  <small>{{ actorDisplayName(event.actor) }}</small>
                </div>
                <el-button
                  v-if="showEventResourceAction(event)"
                  link
                  type="primary"
                  :icon="Right"
                  @click="openResource(event.resourceRef)"
                >{{ resourceActionLabel(event.resourceRef.resourceType) }}</el-button>
              </header>
              <p v-if="event.description" class="history-event__description">{{ event.description }}</p>

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

              <template v-if="event.versionCycle">
                <section class="version-cycle">
                  <header class="version-cycle__heading">
                    <div>
                      <strong>{{ event.versionCycle.versionNumber }}</strong>
                      <el-tag :type="historyTagType(historyVersionStatusMeta(event.versionCycle.versionStatus))" size="small" effect="plain" round>{{ historyVersionStatusMeta(event.versionCycle.versionStatus).label }}</el-tag>
                    </div>
                    <span>{{ actorDisplayName(event.versionCycle.submitter) }} · {{ formatHistoryDateTime(event.versionCycle.submittedTime) }}</span>
                  </header>
                  <p>{{ event.versionCycle.changelog || '本版未填写整体修改说明。' }}</p>

                  <div class="version-cycle__file">
                    <div v-if="event.versionCycle.primaryFile"><strong>{{ event.versionCycle.primaryFile.businessFileName }}</strong><small>{{ event.versionCycle.primaryFile.contentType || '未知文件类型' }} · {{ formatHistoryFileSize(event.versionCycle.primaryFile.fileSize) }}</small></div>
                    <div v-else><strong>版本成果</strong><small>未提供主文件摘要</small></div>
                    <div class="version-cycle__actions">
                      <el-button link type="primary" :icon="Right" @click="openResource({ resourceType: 'version', resourceId: event.versionCycle.versionId })">版本详情</el-button>
                      <el-button v-if="reviewListRef(event.versionCycle)" link type="primary" :icon="Right" @click="openResource(reviewListRef(event.versionCycle))">审核单</el-button>
                    </div>
                  </div>

                  <el-collapse v-if="hasVersionDetails(event.versionCycle)" class="version-cycle__details">
                    <div class="version-cycle__detail-grid">
                    <el-collapse-item v-if="event.versionCycle.reviewActions?.length" class="version-cycle__detail-item" name="review-actions">
                      <template #title><span class="version-cycle__detail-title"><span>审核动作</span><el-tag size="small" type="info" effect="plain" round>{{ event.versionCycle.reviewActions.length }} 条</el-tag></span></template>
                      <div class="history-record-list">
                        <article v-for="action in event.versionCycle.reviewActions" :key="action.actionId" class="history-record">
                          <header><el-tag :type="historyTagType(historyReviewActionMeta(action.actionType))" size="small" effect="plain" round>{{ historyReviewActionMeta(action.actionType).label }}</el-tag><time>{{ formatHistoryDateTime(action.createTime) }}</time></header>
                          <p>{{ action.reason || '审核人未填写额外说明。' }}</p>
                          <small>{{ actorDisplayName(action.reviewer) }} · {{ historyWorkflowStatusLabel(action.fromStatus) }} → {{ historyWorkflowStatusLabel(action.toStatus) }}</small>
                        </article>
                      </div>
                    </el-collapse-item>

                    <el-collapse-item v-if="event.versionCycle.sourceIssues?.length" class="version-cycle__detail-item" name="source-issues">
                      <template #title><span class="version-cycle__detail-title"><span>修改问题</span><el-tag size="small" type="info" effect="plain" round>{{ event.versionCycle.sourceIssues.length }} 条</el-tag></span></template>
                      <div class="history-record-list">
                        <article v-for="issue in event.versionCycle.sourceIssues" :key="issue.issueId" class="history-record">
                          <header><span><strong>#{{ issue.issueId }}</strong><el-tag :type="historyTagType(historyIssueStatusMeta(issue.status))" size="small" effect="plain" round>{{ historyIssueStatusMeta(issue.status).label }}</el-tag></span><time>{{ formatHistoryDateTime(issue.createTime) }}</time></header>
                          <p>{{ sourceIssueSummary(issue) }}</p>
                          <small>来源 {{ issue.originVersionNumber }} · {{ actorDisplayName(issue.reviewer) }}<template v-if="issue.resolvedInVersionNumber"> · 在 {{ issue.resolvedInVersionNumber }} 解决</template></small>
                          <el-button v-if="reviewListRef(event.versionCycle)" link type="primary" :icon="Right" @click="openResource(reviewListRef(event.versionCycle))">查看所属审核单</el-button>
                        </article>
                      </div>
                    </el-collapse-item>

                    <el-collapse-item v-if="event.versionCycle.issueResponses?.length" class="version-cycle__detail-item" name="issue-responses">
                      <template #title><span class="version-cycle__detail-title"><span>制作处理说明</span><el-tag size="small" type="info" effect="plain" round>{{ event.versionCycle.issueResponses.length }} 条</el-tag></span></template>
                      <div class="history-record-list">
                        <article v-for="response in event.versionCycle.issueResponses" :key="response.responseId" class="history-record">
                          <header><strong>问题 #{{ response.issueId }}</strong><time>{{ formatHistoryDateTime(response.createTime) }}</time></header>
                          <p>{{ response.responseText }}</p>
                          <small>{{ actorDisplayName(response.responder) }} · 来源 {{ response.originVersionNumber }}</small>
                        </article>
                      </div>
                    </el-collapse-item>

                    <el-collapse-item v-if="event.versionCycle.issueVerifications?.length" class="version-cycle__detail-item" name="issue-verifications">
                      <template #title><span class="version-cycle__detail-title"><span>审核确认</span><el-tag size="small" type="info" effect="plain" round>{{ event.versionCycle.issueVerifications.length }} 条</el-tag></span></template>
                      <div class="history-record-list">
                        <article v-for="verification in event.versionCycle.issueVerifications" :key="verification.verificationId" class="history-record">
                          <header><span><strong>问题 #{{ verification.issueId }}</strong><el-tag :type="historyTagType(historyVerificationMeta(verification.result))" size="small" effect="plain" round>{{ historyVerificationMeta(verification.result).label }}</el-tag></span><time>{{ formatHistoryDateTime(verification.createTime) }}</time></header>
                          <p v-if="verification.comment">{{ verification.comment }}</p>
                          <small>{{ actorDisplayName(verification.reviewer) }} · 在 {{ verification.checkedVersionNumber }} 核验</small>
                        </article>
                      </div>
                    </el-collapse-item>
                    </div>
                  </el-collapse>
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
.history-stage__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.history-stage__heading > div { display: flex; min-width: 0; align-items: baseline; gap: 10px; }
.history-stage__heading strong { overflow: hidden; font-size: 16px; text-overflow: ellipsis; white-space: nowrap; }
.history-stage__heading span { color: var(--sg-text-muted); font-size: 11px; }
.history-stage__tags { flex: 0 0 auto; }
.history-stage__steps { --el-color-primary: var(--sg-accent); }
.history-stage__steps:deep(.el-step__icon) { width: 28px; height: 28px; background: var(--sg-surface-raised); border-width: 2px; }
.history-stage__steps:deep(.el-step__icon-inner) { font-size: 11px; font-weight: 700; }
.history-stage__steps:deep(.el-step__line) { top: 13px; height: 2px; background: var(--sg-border-strong); }
.history-stage__steps:deep(.el-step__line-inner) { border-width: 1px !important; }
.history-stage__steps:deep(.el-step__main) { padding-top: 8px; }
.history-stage__steps:deep(.el-step__title) { color: var(--sg-text-secondary); font-size: 12px; line-height: 1.35; }
.history-stage__steps:deep(.el-step__title.is-process),
.history-stage__steps:deep(.el-step__title.is-success) { color: var(--sg-text); }
.history-stage__steps:deep(.el-step__head.is-process),
.history-stage__steps:deep(.el-step__head.is-success) { color: var(--sg-accent); border-color: var(--sg-accent); }
.history-metrics { display: grid; margin-top: 20px; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.history-metrics:deep(.el-statistic) { padding: 12px 14px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: 9px; }
.history-metrics:deep(.el-statistic__head) { margin-bottom: 5px; color: var(--sg-text-muted); font-size: 10px; }
.history-metrics:deep(.el-statistic__number) { color: var(--sg-text); font-size: 21px; }
.history-lane-summary,
.history-timeline { margin-top: 20px; }
.history-lane-summary:deep(.el-table) { --el-table-bg-color: var(--sg-surface); --el-table-tr-bg-color: var(--sg-surface); --el-table-header-bg-color: var(--sg-surface-raised); --el-table-border-color: var(--sg-border); --el-table-text-color: var(--sg-text-secondary); --el-table-header-text-color: var(--sg-text-muted); }
.history-timeline:deep(.el-timeline) { margin: 0; padding: 2px 0 0 8px; }
.history-timeline:deep(.el-timeline-item) { padding-bottom: 18px; }
.history-timeline:deep(.el-timeline-item:last-child) { padding-bottom: 0; }
.history-timeline:deep(.el-timeline-item__tail) { left: 5px; border-left: 2px solid var(--sg-border-strong); }
.history-timeline:deep(.el-timeline-item__node--large) { left: -1px; width: 13px; height: 13px; box-shadow: 0 0 0 4px var(--sg-surface); }
.history-timeline:deep(.el-timeline-item__wrapper) { top: -5px; padding-left: 25px; }
.history-timeline:deep(.el-timeline-item__timestamp) { margin-bottom: 7px; color: var(--sg-text-muted); font-size: 10px; font-variant-numeric: tabular-nums; line-height: 1.4; }
.history-event { --el-card-bg-color: var(--sg-surface-raised); --el-card-border-color: var(--sg-border); border-left: 3px solid var(--sg-border-strong); border-radius: 10px; }
.history-event:deep(.el-card__body) { padding: 14px 16px; }
.history-event--version { --el-card-border-color: color-mix(in srgb, var(--sg-accent) 32%, var(--sg-border)); }
.history-event--version.el-card { border-left-color: var(--sg-accent); }
.history-event__heading,
.version-cycle__heading,
.history-record > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.history-event__title-row,
.history-record > header > span,
.version-cycle__heading > div { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.history-event__heading small,
.version-cycle__heading > span,
.history-record small,
.history-record time { color: var(--sg-text-muted); font-size: 9px; }
.history-event__description { margin: 10px 0 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.6; }
.event-import { margin-top: 13px; }
.event-import:deep(.el-descriptions__body),
.event-import:deep(.el-descriptions__cell) { background: var(--sg-surface) !important; border-color: var(--sg-border) !important; }
.event-import:deep(.el-descriptions__label) { color: var(--sg-text-muted); font-size: 9px; }
.event-import:deep(.el-descriptions__content) { color: var(--sg-text-secondary); font-size: 10px; overflow-wrap: anywhere; }
.version-cycle { display: grid; margin-top: 13px; gap: 12px; }
.version-cycle__heading strong { font-size: 20px; }
.version-cycle > p { margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.7; }
.version-cycle__file { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 14px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: 9px; }
.version-cycle__file > div:first-child { display: grid; min-width: 0; gap: 4px; }
.version-cycle__file strong { overflow: hidden; color: var(--sg-text); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.version-cycle__file small { color: var(--sg-text-muted); font-size: 9px; }
.version-cycle__actions { display: flex; flex: 0 0 auto; }
.version-cycle__details { padding-top: 12px; border-top: 1px solid var(--sg-border); border-bottom: 0; }
.version-cycle__details:deep(.el-collapse-item) { display: block; width: 100%; min-width: 0; overflow: hidden; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: 9px; transition: border-color 160ms ease, background 160ms ease; }
.version-cycle__detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 10px; align-items: start; }
.version-cycle__details:deep(.el-collapse-item.is-active) { border-color: color-mix(in srgb, var(--sg-accent) 38%, var(--sg-border)); }
.version-cycle__details:deep(.el-collapse-item__header) { display: flex; width: 100%; min-width: 0; min-height: 46px; height: 46px; padding: 0 12px 0 14px; align-items: center; color: var(--sg-text); background: transparent; border-bottom: 0; font-weight: 600; line-height: 1.35; }
.version-cycle__details:deep(.el-collapse-item__header:hover) { background: var(--sg-surface-soft); }
.version-cycle__details:deep(.el-collapse-item__arrow) { flex: 0 0 auto; margin: 0 0 0 10px; color: var(--sg-accent); font-size: 13px; }
.version-cycle__details:deep(.el-collapse-item__wrap) { background: transparent; border-top: 1px solid var(--sg-border); border-bottom: 0; }
.version-cycle__details:deep(.el-collapse-item__content) { padding: 12px; color: var(--sg-text-secondary); }
.version-cycle__detail-title { display: grid; width: auto; height: 100%; min-width: 0; flex: 1 1 0%; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; }
.version-cycle__detail-title > span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-cycle__detail-title:deep(.el-tag) { flex: 0 0 auto; }
.history-record-list { display: grid; gap: 8px; }
.history-record { display: grid; gap: 7px; padding: 11px 12px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: 8px; }
.history-record p { margin: 0; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.6; white-space: pre-wrap; }
.history-record > .el-button { justify-self: start; padding-left: 0; }

@media (max-width: 850px) {
  .history-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .version-cycle__file { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 620px) {
  .production-history__heading,
  .history-stage__heading,
  .history-event__heading,
  .version-cycle__heading { align-items: stretch; flex-direction: column; }
  .history-stage__heading > div { align-items: flex-start; flex-direction: column; }
  .history-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .history-timeline:deep(.el-timeline) { padding-left: 2px; }
}
</style>
