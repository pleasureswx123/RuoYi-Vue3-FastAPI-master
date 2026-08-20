<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import { getReviewActions, getTaskIssues } from '@/api/shot-grid/reviews'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import { tagTypeFromTone } from '@/utils/tag'
import ReviewMediaWorkspace from '@/views/review/components/ReviewMediaWorkspace.vue'
import { formatMediaTime, formatReviewDateTime, reviewActionMeta, reviewErrorState } from '@/views/review/reviewPresentation'
import VersionDetailCard from './VersionDetailCard.vue'
import { formatVersionDateTime, versionErrorState, versionStatusMeta } from './versionPresentation'

const props = defineProps({
  taskId: { type: Number, required: true },
  operationGeneration: { type: Number, default: 0 },
  refreshKey: { type: [Number, String], default: 0 },
  pageSize: { type: Number, default: 10 },
  canList: { type: Boolean, default: false },
  canQuery: { type: Boolean, default: false },
  canDownload: { type: Boolean, default: false },
  canListNotes: { type: Boolean, default: false }
})
const emit = defineEmits(['version-selected'])

const versions = ref([])
const total = ref(0)
const pageNum = ref(1)
const statusFilter = ref('')
const selectedVersionId = ref(null)
const versionDetail = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const listError = ref(null)
const detailError = ref(null)
const feedbackNotes = ref([])
const feedbackActions = ref([])
const selectedFeedback = ref(null)
const feedbackLoading = ref(false)
const feedbackError = ref(null)
const feedbackPanel = ref(null)

let disposed = false
let contextGeneration = 0
let listController = null
let detailController = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / props.pageSize)))
const historyFilters = computed(() => ({ versionStatus: statusFilter.value }))
const latestDecision = computed(() => feedbackActions.value.find(item => ['approve', 'reject', 'defer'].includes(item.actionType)) || null)
const hasFeedback = computed(() => Boolean(feedbackNotes.value.length || latestDecision.value))
const pendingFeedbackCount = computed(() => feedbackNotes.value.filter(item => item.displayScope === 'pending').length)

function latestVerification(issue) {
  const items = issue?.verifications || []
  return items.length ? items[items.length - 1] : null
}

function latestResponse(issue) {
  const items = issue?.responses || []
  return items.length ? items[items.length - 1] : null
}

function verificationForVersion(issue, versionId = selectedVersionId.value) {
  return (issue?.verifications || []).find(item => Number(item.checkedVersionId) === Number(versionId)) || null
}

function responseForVersion(issue, versionId = selectedVersionId.value) {
  return (issue?.responses || []).find(item => Number(item.versionId) === Number(versionId)) || null
}

function displayedResponse(issue) {
  return responseForVersion(issue) || (Number(issue?.originVersionId) === selectedVersionId.value ? latestResponse(issue) : null)
}

function pendingVersionId(issue) {
  if (issue?.status !== 'open') return null
  return Number(issue.pendingVersionId || issue.originVersionId) || null
}

function buildVersionFeedback(issues, versionId) {
  return issues
    .map(issue => {
      const pendingHere = pendingVersionId(issue) === versionId
      const originHere = Number(issue.originVersionId) === versionId
      const touchedHere = (issue.verifications || []).some(item => Number(item.checkedVersionId) === versionId)
        || (issue.responses || []).some(item => Number(item.versionId) === versionId)
      if (!pendingHere && !originHere && !touchedHere) return null
      return {
        ...issue,
        noteId: issue.issueId,
        noteStatus: issue.status,
        displayScope: pendingHere ? 'pending' : originHere ? 'origin_history' : 'version_history'
      }
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (left.displayScope !== right.displayScope) return left.displayScope === 'pending' ? -1 : 1
      return Number(left.issueId) - Number(right.issueId)
    })
}

function feedbackBadgeMeta(note) {
  if (note.displayScope === 'pending') {
    return {
      label: Number(note.originVersionId) === selectedVersionId.value
        ? '待处理'
        : `${note.originVersionNumber} 遗留 · 待处理`,
      tone: 'warning'
    }
  }
  const verification = verificationForVersion(note)
  if (verification?.result === 'resolved') return { label: '本版确认已修复', tone: 'success' }
  if (verification?.result === 'still_present') {
    return {
      label: `本版确认仍存在${note.pendingVersionNumber ? ` · 已转入 ${note.pendingVersionNumber}` : ''}`,
      tone: 'danger'
    }
  }
  if (note.noteStatus === 'resolved') {
    return { label: `已在 ${note.resolvedInVersionNumber || '后续版本'} 修复`, tone: 'success' }
  }
  return {
    label: `已处理但未通过 · 转入 ${note.pendingVersionNumber || '最新版本'}`,
    tone: 'warning'
  }
}

function alertTypeFromTone(tone) {
  if (tone === 'success') return 'success'
  if (tone === 'danger') return 'error'
  if (tone === 'warning') return 'warning'
  return 'info'
}

function feedbackContext(note) {
  const verification = latestVerification(note)
  if (note.displayScope === 'pending' && Number(note.originVersionId) !== selectedVersionId.value) {
    return `来源 ${note.originVersionNumber}；审核人在 ${note.pendingVersionNumber || '当前版'} 确认仍然存在`
  }
  if (note.displayScope === 'origin_history' && note.noteStatus === 'open') {
    return `已随 ${note.pendingVersionNumber || '后续版本'} 提交处理，但审核确认仍未解决；当前待处理已转入 ${note.pendingVersionNumber || '最新版本'}`
  }
  if (note.displayScope === 'version_history') {
    return `该问题来源于 ${note.originVersionNumber}；此处保留本版处理与确认记录`
  }
  if (note.noteStatus === 'resolved') return `该问题已在 ${note.resolvedInVersionNumber || '后续版本'} 关闭`
  return verification ? `最近一次确认：${verification.checkedVersionNumber}` : `提出于 ${note.originVersionNumber}`
}

function feedbackVerificationComment(note) {
  const verification = verificationForVersion(note) || latestVerification(note)
  return verification?.result === 'still_present' ? verification.comment : ''
}

function canceled(error, controller) {
  return error?.code === 'ERR_CANCELED' || controller?.signal.aborted
}

function stillCurrent(generation, targetTaskId, targetOperationGeneration) {
  return !disposed &&
    contextGeneration === generation &&
    Number(props.taskId) === targetTaskId &&
    Number(props.operationGeneration) === targetOperationGeneration
}

async function loadDetail(versionId, generation = contextGeneration) {
  detailController?.abort()
  versionDetail.value = null
  detailError.value = null
  feedbackNotes.value = []
  feedbackActions.value = []
  selectedFeedback.value = null
  feedbackError.value = null
  const normalizedVersionId = Number(versionId)
  if (!props.canQuery || !normalizedVersionId) return
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const controller = new AbortController()
  detailController = controller
  detailLoading.value = true
  try {
    const response = await getVersionDetail(normalizedVersionId, { signal: controller.signal })
    if (
      detailController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      selectedVersionId.value !== normalizedVersionId
    ) return
    if (Number(response.data?.taskId) !== targetTaskId) {
      throw new Error('版本详情与当前任务不匹配')
    }
    versionDetail.value = response.data
    feedbackLoading.value = true
    const [noteResult, actionResult] = await Promise.allSettled([
      props.canListNotes
        ? getTaskIssues(targetTaskId, {}, { signal: controller.signal })
        : Promise.resolve({ data: [] }),
      getReviewActions(normalizedVersionId, {
        pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending'
      }, { signal: controller.signal })
    ])
    if (
      detailController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      selectedVersionId.value !== normalizedVersionId
    ) return
    if (noteResult.status === 'fulfilled') {
      feedbackNotes.value = buildVersionFeedback(noteResult.value.data || [], normalizedVersionId)
      selectedFeedback.value = feedbackNotes.value.find(item => (
        Number(item.originVersionId) === normalizedVersionId && item.displayScope === 'pending'
      )) || feedbackNotes.value.find(item => Number(item.originVersionId) === normalizedVersionId) || null
    } else if (!canceled(noteResult.reason, controller)) {
      feedbackError.value = reviewErrorState(noteResult.reason, '审核意见加载失败')
    }
    if (actionResult.status === 'fulfilled') {
      feedbackActions.value = actionResult.value.rows || []
    } else if (!feedbackError.value && !canceled(actionResult.reason, controller)) {
      feedbackError.value = reviewErrorState(actionResult.reason, '审核结果加载失败')
    }
    emit('version-selected', response.data, Object.freeze({
      taskId: targetTaskId,
      versionId: normalizedVersionId,
      operationGeneration: targetOperationGeneration
    }))
  } catch (error) {
    if (!canceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      detailError.value = versionErrorState(error, '版本详情加载失败')
    }
  } finally {
    if (detailController === controller) {
      detailController = null
      detailLoading.value = false
      feedbackLoading.value = false
    }
  }
}

async function loadVersions({ preserveSelection = true } = {}) {
  listController?.abort()
  detailController?.abort()
  const generation = contextGeneration
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const controller = new AbortController()
  listController = controller
  loading.value = true
  listError.value = null
  if (!props.canList) {
    controller.abort()
    if (listController === controller) {
      listController = null
      loading.value = false
    }
    return
  }
  try {
    const params = {
      pageNum: pageNum.value,
      pageSize: props.pageSize,
      orderByColumn: 'versionNo',
      isAsc: 'descending'
    }
    if (statusFilter.value) params.versionStatus = statusFilter.value
    const response = await getTaskVersions(targetTaskId, params, { signal: controller.signal })
    if (listController !== controller || !stillCurrent(generation, targetTaskId, targetOperationGeneration)) return
    const rows = Array.isArray(response.rows) ? response.rows : []
    versions.value = rows
    total.value = Number(response.total || 0)
    const currentStillExists = preserveSelection && rows.some(row => Number(row.versionId) === selectedVersionId.value)
    selectedVersionId.value = currentStillExists ? selectedVersionId.value : Number(rows[0]?.versionId) || null
    if (selectedVersionId.value) await loadDetail(selectedVersionId.value, generation)
    else versionDetail.value = null
  } catch (error) {
    if (!canceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      versions.value = []
      total.value = 0
      selectedVersionId.value = null
      versionDetail.value = null
      listError.value = versionErrorState(error, '版本历史加载失败')
    }
  } finally {
    if (listController === controller) {
      listController = null
      loading.value = false
    }
  }
}

function selectVersion(versionId) {
  const normalized = Number(versionId)
  if (!normalized || normalized === selectedVersionId.value) return
  selectedVersionId.value = normalized
  loadDetail(normalized)
}

async function focusIssue(issue) {
  const originVersionId = Number(issue?.originVersionId)
  const issueId = Number(issue?.issueId)
  if (!originVersionId || !issueId || !props.canQuery) return
  selectedVersionId.value = originVersionId
  await loadDetail(originVersionId)
  selectedFeedback.value = feedbackNotes.value.find(item => Number(item.issueId) === issueId) || null
  await nextTick()
  const feedbackElement = feedbackPanel.value?.$el || feedbackPanel.value
  feedbackElement?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

function selectFeedback(issue) {
  if (Number(issue?.originVersionId) !== selectedVersionId.value) {
    void focusIssue(issue)
    return
  }
  selectedFeedback.value = issue
}

function applyStatusFilter() {
  pageNum.value = 1
  selectedVersionId.value = null
  loadVersions({ preserveSelection: false })
}

function changePage(targetPage) {
  const next = Math.min(totalPages.value, Math.max(1, Number(targetPage) || 1))
  if (next === pageNum.value) return
  pageNum.value = next
  loadVersions({ preserveSelection: false })
}

function resetForContext() {
  contextGeneration += 1
  listController?.abort()
  detailController?.abort()
  listController = null
  detailController = null
  loading.value = false
  detailLoading.value = false
  versions.value = []
  total.value = 0
  pageNum.value = 1
  statusFilter.value = ''
  selectedVersionId.value = null
  versionDetail.value = null
  listError.value = null
  detailError.value = null
  feedbackNotes.value = []
  feedbackActions.value = []
  selectedFeedback.value = null
  feedbackLoading.value = false
  feedbackError.value = null
  loadVersions({ preserveSelection: false })
}

watch(
  () => [props.taskId, props.operationGeneration, props.canList, props.canQuery, props.canListNotes],
  resetForContext,
  { immediate: true }
)
watch(() => props.refreshKey, () => loadVersions({ preserveSelection: true }))

onBeforeUnmount(() => {
  disposed = true
  contextGeneration += 1
  listController?.abort()
  detailController?.abort()
})

defineExpose({ focusIssue })
</script>

<template>
  <el-card class="version-history-panel" shadow="never">
    <header class="history-heading">
      <div><p class="sg-eyebrow">IMMUTABLE HISTORY</p><h3>版本历史</h3><p>版本按提交顺序自动编号；每次修订都会新增版本，历史文件始终保留。</p></div>
      <el-form :model="historyFilters" class="history-tools" size="large" inline aria-label="版本历史筛选">
        <el-form-item prop="versionStatus">
          <el-select v-model="statusFilter" class="sg-select" placeholder="全部状态" aria-label="筛选版本状态" @change="applyStatusFilter">
            <el-option label="全部状态" value="" />
            <el-option label="待审核" value="pending_review" />
            <el-option label="已退回" value="rejected" />
            <el-option label="最终版本" value="final" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button v-if="canList" :icon="Refresh" :loading="loading" @click="loadVersions()">刷新</el-button></el-form-item>
      </el-form>
    </header>

    <el-alert v-if="!canList" class="history-error" title="当前账号没有版本列表权限" description="请联系项目管理人或管理员开通访问权限。" type="warning" :closable="false" show-icon />
    <el-alert v-else-if="listError" class="history-error" :title="listError.title" :description="listError.message" type="error" :closable="false" show-icon />

    <div class="history-layout">
      <aside class="version-rail" :aria-busy="loading">
        <el-button
          v-for="version in versions"
          :key="version.versionId"
          text
          class="version-rail__item"
          :class="{ active: selectedVersionId === Number(version.versionId) }"
          @click="selectVersion(version.versionId)"
        >
          <span class="version-rail__content">
            <span><strong>{{ version.versionNumber }}</strong><small>{{ version.submitterName || `用户 #${version.submittedBy}` }}</small></span>
            <el-tag class="version-rail__status" size="small" effect="plain" round :type="tagTypeFromTone(versionStatusMeta(version.versionStatus).tone)">{{ versionStatusMeta(version.versionStatus).label }}</el-tag>
            <p>{{ version.changelog }}</p>
            <time>{{ formatVersionDateTime(version.submittedTime) }}</time>
          </span>
        </el-button>
        <el-skeleton v-if="loading && !versions.length" class="history-empty" :rows="4" animated />
        <el-empty v-else-if="!versions.length && !listError" class="history-empty" :image-size="56" description="该任务还没有正式版本" />
        <el-pagination v-if="total > pageSize" class="version-pagination" small background layout="prev, pager, next" :current-page="pageNum" :page-size="pageSize" :total="total" :disabled="loading" aria-label="版本历史分页" @current-change="changePage" />
      </aside>

      <main class="history-detail">
        <el-skeleton v-if="detailLoading" class="detail-placeholder" :rows="8" animated />
        <el-alert v-else-if="detailError" class="detail-placeholder is-error" :title="detailError.title" :description="detailError.message" type="error" :closable="false" show-icon />
        <template v-else-if="versionDetail">
          <VersionDetailCard :version="versionDetail" :can-download="canDownload" :show-preview="!feedbackNotes.length" />
          <el-card v-if="feedbackLoading || feedbackError || hasFeedback" ref="feedbackPanel" class="version-feedback-panel" shadow="never">
            <header class="version-feedback-panel__heading"><div><p class="sg-eyebrow">REVIEW FEEDBACK</p><h3>本版待处理问题与审核记录</h3><p>待处理工作始终归属最近一次退回的版本；原始问题与标注仍保留在最初提出版本中供追溯。</p></div><span>{{ pendingFeedbackCount }} 条待处理 · {{ feedbackNotes.length - pendingFeedbackCount }} 条历史</span></header>
            <el-alert v-if="latestDecision" class="feedback-decision" :type="alertTypeFromTone(reviewActionMeta(latestDecision.actionType).tone)" :title="reviewActionMeta(latestDecision.actionType).label" :description="`${latestDecision.reason || '审核人未填写额外说明。'} · ${latestDecision.reviewerName || `用户 #${latestDecision.reviewerUserId}`} · ${formatReviewDateTime(latestDecision.createTime)}`" :closable="false" show-icon />
            <el-skeleton v-if="feedbackLoading" class="feedback-state" :rows="4" animated />
            <el-alert v-else-if="feedbackError" class="feedback-state is-error" :title="feedbackError.title" :description="feedbackError.message" type="error" :closable="false" show-icon />
            <div v-else-if="feedbackNotes.length" class="feedback-layout">
              <ReviewMediaWorkspace :version="versionDetail" :selected-note="selectedFeedback" :can-download="canDownload" feedback-mode @clear-note-focus="selectedFeedback = null" />
              <aside class="feedback-list">
                <el-button v-for="note in feedbackNotes" :key="note.noteId" text class="feedback-item" :class="{ active: selectedFeedback?.noteId === note.noteId }" @click="selectFeedback(note)">
                  <span class="feedback-item__content">
                    <span class="feedback-item__heading"><strong>{{ note.displayScope === 'pending' ? '本版待处理问题' : note.displayScope === 'origin_history' ? '来源版本历史问题' : '本版处理确认记录' }}</strong><el-tag size="small" effect="plain" round :type="tagTypeFromTone(feedbackBadgeMeta(note).tone)">{{ feedbackBadgeMeta(note).label }}</el-tag></span>
                    <p>{{ note.content || '该问题仅包含画面标注' }}</p>
                    <small class="feedback-context">{{ feedbackContext(note) }}</small>
                    <p v-if="displayedResponse(note)" class="feedback-response">制作人对 {{ displayedResponse(note).versionNumber || '后续版本' }} 的处理说明：{{ displayedResponse(note).responseText }}</p>
                    <p v-if="feedbackVerificationComment(note)" class="feedback-verification">审核人未通过原因：{{ feedbackVerificationComment(note) }}</p>
                    <small><template v-if="note.annotations?.items?.length">{{ note.annotations.items.length }} 个画面标注 · </template><template v-if="note.mediaTimeMs !== null && note.mediaTimeMs !== undefined">{{ formatMediaTime(note.mediaTimeMs) }} · </template>{{ formatReviewDateTime(note.createTime) }}</small>
                  </span>
                </el-button>
              </aside>
            </div>
            <el-empty v-else class="feedback-state" :image-size="48" description="审核人没有在该版本提出修改问题" />
          </el-card>
        </template>
        <el-empty v-else-if="!canQuery" class="detail-placeholder" :image-size="56" description="当前账号没有版本详情权限" />
        <el-empty v-else class="detail-placeholder" :image-size="56" description="选择左侧版本查看文件和审核单信息" />
      </main>
    </div>
  </el-card>
</template>

<style scoped lang="scss">
.version-history-panel { --el-card-bg-color: var(--sg-surface); --el-card-border-color: var(--sg-border); border-radius: var(--sg-radius-lg); }
.version-history-panel:deep(.el-card__body) { padding: 24px; }
.history-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.history-heading h3 { margin: 3px 0 7px; font-size: 20px; }
.history-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.history-tools { display: flex; gap: 9px; }
.history-tools:deep(.el-form-item) { margin: 0; }
.history-tools .sg-select { width: 160px; }
.history-error { margin-top: 16px; }
.history-error code { color: inherit; font-size: 10px; }
.history-layout { display: grid; margin-top: 20px; grid-template-columns: minmax(230px, 0.34fr) minmax(0, 1fr); gap: 14px; }
.version-rail { display: grid; align-content: start; gap: 8px; }
.version-rail > .el-button { display: grid; width: 100%; height: auto; margin: 0; padding: 14px; color: var(--sg-text); text-align: left; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; }
.version-rail__content { display: grid; width: 100%; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.version-rail > .el-button:hover,
.version-rail > .el-button.active { background: rgba(255, 182, 87, 0.06); border-color: rgba(255, 182, 87, 0.35); }
.version-rail strong,
.version-rail small { display: block; }
.version-rail strong { font-size: 14px; }
.version-rail small { margin-top: 4px; color: var(--sg-text-muted); font-size: 10px; }
.version-rail__status { align-self: start; }
.version-rail p { display: -webkit-box; grid-column: 1 / -1; margin: 2px 0 0; overflow: hidden; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.version-rail time { grid-column: 1 / -1; color: var(--sg-text-muted); font-size: 9px; }
.version-pagination { justify-content: center; padding: 8px 2px; }
.history-empty,
.detail-placeholder { display: grid; min-height: 180px; padding: 24px; color: var(--sg-text-muted); text-align: center; background: rgba(255, 255, 255, 0.018); border: 1px dashed var(--sg-border); border-radius: var(--sg-radius-md); place-items: center; }
.detail-placeholder.is-error { color: #ffb5ad; }
.detail-placeholder p { margin: 5px 0 0; font-size: 11px; }
.detail-placeholder code { font-size: 10px; }
.version-feedback-panel { --el-card-bg-color: rgba(104, 181, 255, 0.035); --el-card-border-color: rgba(104, 181, 255, 0.18); margin-top: 14px; border-radius: var(--sg-radius-md); }
.version-feedback-panel:deep(.el-card__body) { display: grid; padding: 18px; gap: 14px; }
.version-feedback-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.version-feedback-panel__heading h3 { margin: 3px 0 5px; font-size: 17px; }
.version-feedback-panel__heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 10px; }
.version-feedback-panel__heading > span { color: var(--sg-text-muted); font-size: 10px; white-space: nowrap; }
.feedback-decision { padding: 12px 14px; }
.feedback-decision small { color: var(--sg-text-muted); font-size: 9px; }
.feedback-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 0.42fr); gap: 12px; align-items: start; }
.feedback-list { display: grid; max-height: 620px; overflow-y: auto; gap: 8px; }
.feedback-list .feedback-item { display: grid; width: 100%; height: auto; margin: 0; padding: 12px; color: var(--sg-text); text-align: left; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 9px; }
.feedback-item__content { display: grid; width: 100%; gap: 8px; }
.feedback-list .feedback-item:hover,
.feedback-list .feedback-item.active { background: rgba(104, 181, 255, 0.07); border-color: rgba(104, 181, 255, 0.42); }
.feedback-item__heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.feedback-list strong { font-size: 10px; }
.feedback-list p { margin: 0; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.6; white-space: pre-wrap; }
.feedback-list small { color: var(--sg-text-muted); font-size: 9px; }
.feedback-list .feedback-context { color: #68b5ff; line-height: 1.5; }
.feedback-list .feedback-response { padding: 8px; color: var(--sg-text-secondary); font-size: 10px; background: rgba(104, 181, 255, 0.07); border-radius: 7px; }
.feedback-list .feedback-verification { padding: 8px; color: #ffbd82; font-size: 10px; background: rgba(255, 182, 87, 0.07); border-radius: 7px; }
.feedback-state { display: grid; min-height: 100px; padding: 18px; color: var(--sg-text-muted); text-align: center; background: rgba(255, 255, 255, 0.02); border: 1px dashed var(--sg-border); border-radius: 9px; place-items: center; }
.feedback-state.is-error { color: #ffb5ad; }
.feedback-state p { margin: 5px 0 0; font-size: 10px; }

@media (max-width: 900px) {
  .history-heading { align-items: stretch; flex-direction: column; }
  .history-layout { grid-template-columns: 1fr; }
  .version-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .version-rail footer,
  .version-pagination,
  .history-empty { grid-column: 1 / -1; }
  .feedback-layout { grid-template-columns: 1fr; }
  .feedback-list { max-height: none; }
}

@media (max-width: 600px) {
  .version-rail { grid-template-columns: 1fr; }
}
</style>
