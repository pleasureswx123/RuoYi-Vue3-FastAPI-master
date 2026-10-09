<script setup>
import RevisionTransferDialog from '@/components/version/RevisionTransferDialog.vue'
import { showWorkflowSuccess } from '@/utils/workflowSuccess'
import { useVersionRealtime } from '@/composables/useVersionRealtime'
import CandidateGenerationPrompt from '@/components/version/CandidateGenerationPrompt.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDetailNavigation } from '@/composables/useDetailNavigation'
import { ArrowLeft, ArrowRight, Refresh } from '@element-plus/icons-vue'
import { ElAffix, ElTabs, ElTabPane, ElMessage, ElMessageBox, ElRadio, ElRadioGroup } from 'element-plus'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'

import {
  addVersionIssueDraft,
  appendVersionIssue,
  updatePublishedVersionIssue,
  createReviewAction,
  deleteVersionIssueDraft,
  getReviewActions,
  getTaskIssues,
  getReviewListDetail,
  getVersionReviewContext,
  retryFinalDelivery,
  transitionManualReviewList,
  updateVersionIssueDraft
} from '@/api/shot-grid/reviews'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { getVersionDetail } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'
import VersionHistoryPanel from '@/components/version/VersionHistoryPanel.vue'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'
import { useSessionStore } from '@/store/modules/session'
import { createIdempotencyState } from '@/utils/idempotency'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ReviewCandidateThumbnail from '@/views/review/components/ReviewCandidateThumbnail.vue'
import ReviewMediaWorkspace from '@/views/review/components/ReviewMediaWorkspace.vue'
import ReviewProductionTarget from '@/views/review/components/ReviewProductionTarget.vue'
import { taskVersionStatusMeta } from '@/views/task/taskPresentation'
import {
  formatMediaTime,
  formatReviewDateTime,
  reviewActionMeta,
  reviewErrorState,
  reviewModeMeta,
  reviewStatusMeta
} from './reviewPresentation'

const props = defineProps({ targetReviewListId: { type: [Number, String], default: null }, embedded: { type: Boolean, default: false } })
const route = useRoute()
const navigate = useDetailNavigation()
const emit = defineEmits(['completed'])
const sessionStore = useSessionStore()
const transferDialog = ref(null)
const review = ref(null)
const version = ref(null)
const reviewContext = ref(null)
const actions = ref([])
const loading = ref(false)
const pageError = ref(null)
const realtimeConflict = ref(false)
const issueBusy = ref(false)
const draftActionBusyId = ref(null)
const actionBusy = ref('')
const finalDeliveryRetryBusy = ref(false)
const previewCandidateId = ref(null)
const manualBusy = ref('')
const activeManualVersionId = ref(null)
const selectedIssueId = ref(null)
const mediaWorkspace = ref(null)
const historyVisible = ref(false)
const historySelection = ref(null)
const versionOrder = value => Number(value?.versionNo ?? String(value?.versionNumber || '').match(/\d+/)?.[0] ?? 0)
const canCompareHistory = computed(() => canListVersions.value && canQueryVersion.value
  && Number(historySelection.value?.taskId) === Number(version.value?.taskId)
  && versionOrder(historySelection.value) > 0 && versionOrder(historySelection.value) < versionOrder(version.value))
async function compareHistory() {
  if (!canCompareHistory.value || !mediaWorkspace.value?.compareWithVersion(historySelection.value)) return
  historyVisible.value = false
  await nextTick()
  reviewWorkStep.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}
watch(() => version.value?.versionId, () => {
  historyVisible.value = false
  historySelection.value = null
})
const reviewWorkStep = ref(null)
const candidatePreviewPulse = ref(false)
const issueFormRef = ref(null)
const issueComposer = ref(null)
const assistantTab = ref('current')
const issueContentInput = ref(null)
const issueDraftPulse = ref(false)
const editingDraftId = ref(null)
const editingPublishedId = ref(null)
const editingPublishedLockVersion = ref(null)
const editingDraftLockVersion = ref(null)
const assistantAffixed = ref(false)
const reviewPage = ref(null)
const drawerSidebarHeight = ref('calc(100dvh - 96px)')
let drawerResizeObserver
const decisionReason = ref('')
const issueScope = ref('candidate')
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({
  canEdit: () => !issueBusy.value && !actionBusy.value,
  isCurrent: () => !disposed
})
const issueDraft = reactive({ content: '', mediaSeconds: null, annotations: null, referenceFiles: referenceAttachments })
const verificationDraft = reactive({})
let pageController = null
let pageGeneration = 0
let disposed = false
let actionIdempotency = createIdempotencyState('review-action')
let issueDraftPulseTimer = null
let candidatePreviewPulseTimer = null
let finalDeliveryPollTimer = null
let finalDeliveryPollCount = 0
const reviewListId = computed(() => assertPositiveId(props.targetReviewListId ?? route.params.reviewListId, '审核单'))
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canDownload = computed(() => hasPermission('shotgrid:file:download'))
const canQueryReview = computed(() => hasPermission('shotgrid:reviewList:query'))
const canQueryVersion = computed(() => hasPermission('shotgrid:version:query'))
const canListVersions = computed(() => hasPermission('shotgrid:version:list'))
const candidates = computed(() => reviewContext.value?.candidates || version.value?.candidates || [])
const selectedCandidateId = computed(() => reviewContext.value?.currentVersion?.selectedCandidateId ?? version.value?.selectedCandidateId ?? null)
const finalDelivery = computed(() => reviewContext.value?.currentVersion?.finalDelivery || version.value?.finalDelivery || null)
const finalDeliveryAlert = computed(() => {
  const delivery = finalDelivery.value
  if (!delivery) return null
  if (delivery.deliveryStatus === 'published') {
    return {
      type: 'success',
      title: '最终版本已发布到 NAS',
      path: delivery.finalNasRelativePath,
      description: '同目录 FINAL.json 记录最终候选和文件摘要。'
    }
  }
  if (delivery.deliveryStatus === 'failed') {
    return {
      type: 'error',
      title: '审核已通过，但最终版本发布失败',
      description: delivery.lastErrorMessage || '请联系管理员检查版本发布 Worker 和 NAS 状态。'
    }
  }
  return {
    type: 'warning',
    title: delivery.deliveryStatus === 'publishing' ? '正在发布最终版本到 NAS' : '最终版本已进入 NAS 发布队列',
    description: '候选原文件保持不变；发布完成后会在同一任务目录生成 FINAL 文件夹和 FINAL.json。'
  }
})
const activeCandidate = computed(() => candidates.value.find(item => Number(item.candidateId) === Number(previewCandidateId.value)) || candidates.value[0] || null)
const reviewVersion = computed(() => activeCandidate.value
  ? { ...version.value, candidateId: activeCandidate.value.candidateId, files: activeCandidate.value.files || [], mediaDerivationStatus: activeCandidate.value.mediaDerivationStatus }
  : version.value)
const canAppendIssue = computed(() => canReview.value && hasPermission('shotgrid:note:add') && Boolean(reviewContext.value?.canAppendIssues))
const canAddIssue = computed(() => hasPermission('shotgrid:note:add') && (canSubmitDecision.value || canAppendIssue.value) && (issueScope.value === 'version' || Boolean(activeCandidate.value)))
const canReview = computed(() => hasPermission('shotgrid:version:review'))
const canRetryFinalDelivery = computed(() => hasPermission('shotgrid:version:retry'))
const canActivateManual = computed(() => hasPermission('shotgrid:reviewList:activate'))
const canCompleteManual = computed(() => hasPermission('shotgrid:reviewList:complete'))
const canArchiveManual = computed(() => hasPermission('shotgrid:reviewList:archive'))
const carriedIssues = computed(() => reviewContext.value?.carriedIssues || [])
const carriedFileTab = ref('')
const carriedFilePanes = computed(() => {
  const groups = new Map()
  for (const issue of carriedIssues.value) {
    const name = `${issue.originVersionId}:${issue.originCandidateId ?? 'unknown'}`
    if (!groups.has(name)) groups.set(name, {
      name,
      label: issue.originCandidateId == null ? `${issue.originVersionNumber} · 整体反馈` : issue.originCandidateNumber || `${issue.originVersionNumber} · 文件待确认`,
      issues: []
    })
    groups.get(name).issues.push(issue)
  }
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))
})
watch(carriedFilePanes, panes => {
  if (!panes.some(pane => pane.name === carriedFileTab.value)) carriedFileTab.value = panes[0]?.name || ''
}, { immediate: true })
function carriedFileProgress(pane) {
  const completed = pane.issues.filter(issue => {
    const draft = verificationDraft[issue.issueId]
    return draft?.result && (draft.result !== 'still_present' || draft.comment?.trim())
  }).length
  return `${completed}/${pane.issues.length}`
}

const currentVersionIssues = computed(() => reviewContext.value?.currentVersionIssues || [])
const currentVersionDrafts = computed(() => reviewContext.value?.currentVersionDrafts || [])
const currentIssueCount = computed(() => currentVersionDrafts.value.length + currentVersionIssues.value.length)
const savedIssuePanes = computed(() => [...candidates.value.map(candidate => ({
  name: String(candidate.candidateId),
  label: candidate.candidateNumber,
  drafts: currentVersionDrafts.value.filter(item => Number(item.candidateId) === Number(candidate.candidateId)),
  issues: currentVersionIssues.value.filter(item => Number(item.originCandidateId) === Number(candidate.candidateId))
})), { name: 'overall', label: '整体反馈', drafts: currentVersionDrafts.value.filter(item => item.candidateId == null), issues: currentVersionIssues.value.filter(item => item.originCandidateId == null) }].filter(pane => !canAddIssue.value || (issueScope.value === 'version' ? pane.name === 'overall' : pane.name !== 'overall')))

const savedIssuesTab = ref('')
watch(() => activeCandidate.value?.candidateId, candidateId => {
  if (issueScope.value === 'candidate') savedIssuesTab.value = String(candidateId ?? '')
}, { immediate: true })

function canChangeIssueScope(scope) {
  if (scope !== issueScope.value && (hasUnsavedIssueDraft.value || editingDraftId.value || editingPublishedId.value || issueBusy.value || actionBusy.value)) {
    ElMessage.warning('请先保存或清空当前意见再切换反馈范围')
    return false
  }
  return true
}

function changeIssueScope(scope) {
  if (!canChangeIssueScope(scope)) return
  issueScope.value = scope
  savedIssuesTab.value = scope === 'version' ? 'overall' : String(activeCandidate.value?.candidateId ?? '')
}

function canLeaveSavedIssueTab(candidateId) {
  if (savedIssuesTab.value !== String(candidateId) && hasUnsavedIssueDraft.value) {
    ElMessage.warning('请先保存或清空当前问题草稿，再切换候选预览')
    return false
  }
  return true
}

async function switchSavedIssueCandidate(candidateId) {
  if (candidateId === 'overall') { changeIssueScope('version'); return }
  changeIssueScope('candidate')
  if (String(activeCandidate.value?.candidateId) === String(candidateId)) return
  const candidate = candidates.value.find(item => String(item.candidateId) === String(candidateId))
  if (candidate) await previewCandidate(candidate)
}
const isReviewDecisionOpen = computed(() => (
  review.value?.reviewStatus === 'active' && version.value?.versionStatus === 'pending_review'
))
const draftAnnotationCount = computed(() => issueDraft.annotations?.items?.length || 0)
const issueDraftMediaTimeMs = computed(() => issueDraft.mediaSeconds === null
  ? null
  : Math.round(Number(issueDraft.mediaSeconds) * 1000))
const hasUnsavedIssueDraft = computed(() => Boolean(
  issueDraft.content.trim()
  || issueDraft.mediaSeconds !== null
  || draftAnnotationCount.value
  || referenceAttachments.value.length
))
const assistantShell = computed(() => assistantAffixed.value ? ElAffix : 'div')
const assistantShellProps = computed(() => assistantAffixed.value ? { offset: 92 } : {})
const manualVersions = computed(() => review.value?.versions || [])
const canSubmitDecision = computed(() => (
  canReview.value && isReviewDecisionOpen.value
))
const issueRules = {
  content: [
    { validator: validateIssueContent, trigger: 'change' },
    { max: 10000, message: '修改意见不能超过 10000 个字符', trigger: 'blur' }
  ],
  mediaSeconds: [{ validator: validateMediaSeconds, trigger: 'change' }]
}
const verificationItems = computed(() => carriedIssues.value.map(issue => {
  const result = verificationDraft[issue.issueId]?.result || ''
  return {
    issueId: issue.issueId,
    result,
    comment: result === 'still_present' ? verificationDraft[issue.issueId]?.comment?.trim() || null : null
  }
}))
const verificationComplete = computed(() => verificationItems.value.every(item => (
  item.result && (item.result !== 'still_present' || item.comment)
)))
const completedVerificationCount = computed(() => verificationItems.value.filter(item => (
  item.result && (item.result !== 'still_present' || item.comment)
)).length)
const unresolvedVerificationCount = computed(() => verificationItems.value.filter(item => item.result === 'still_present').length)
const canApprove = computed(() => (
  canSubmitDecision.value
  && verificationComplete.value
  && unresolvedVerificationCount.value === 0
  && currentIssueCount.value === 0
))
const canReject = computed(() => (
  canSubmitDecision.value
  && verificationComplete.value
  && (unresolvedVerificationCount.value > 0 || currentIssueCount.value > 0)
))
const mediaIssues = computed(() => [...carriedIssues.value, ...currentVersionIssues.value].map(issue => ({
  ...issue,
  noteId: issue.issueId,
  noteStatus: issue.status,
  versionId: issue.originVersionId
})).concat(currentVersionDrafts.value.map(draft => ({
  ...draft,
  issueId: `draft-${draft.draftId}`,
  noteId: `draft-${draft.draftId}`,
  noteStatus: 'draft',
  versionId: draft.versionId
}))))
const selectedIssue = computed(() => mediaIssues.value.find(issue => issue.issueId === selectedIssueId.value) || null)

function isCurrent(controller, generation) {
  return pageController === controller && !controller.signal.aborted && pageGeneration === generation
}

function initializeVerificationDraft() {
  const activeIds = new Set(carriedIssues.value.map(issue => String(issue.issueId)))
  Object.keys(verificationDraft).forEach(issueId => {
    if (!activeIds.has(issueId)) delete verificationDraft[issueId]
  })
  carriedIssues.value.forEach(issue => {
    if (!verificationDraft[issue.issueId]) verificationDraft[issue.issueId] = { result: '', comment: '' }
  })
}

async function loadVersionReview(versionId, options = {}) {
  const versionResponse = await getVersionDetail(versionId, options)
  const [contextResponse, actionResponse] = await Promise.all([
    canReview.value
      ? getVersionReviewContext(versionId, options)
      : hasPermission('shotgrid:note:list')
        ? getTaskIssues(versionResponse.data.taskId, {}, options).then(response => ({ data: {
          currentVersion: versionResponse.data,
          carriedIssues: [],
          currentVersionIssues: (response.data || []).filter(issue => Number(issue.originVersionId) === Number(versionId)),
          currentVersionDrafts: []
        } }))
        : Promise.resolve({ data: { currentVersion: versionResponse.data, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } }),
    getReviewActions(versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }, options)
  ])
  return { version: versionResponse.data, context: contextResponse.data, actions: actionResponse.rows || [] }
}

function applyVersionReview(payload, versionId) {
  const sameVersion = Number(versionId) === Number(version.value?.versionId)
  realtimeConflict.value = false
  version.value = payload.version
  reviewContext.value = payload.context
  actions.value = payload.actions
  activeManualVersionId.value = versionId
  selectedIssueId.value = null
  decisionReason.value = ''
  previewCandidateId.value = (sameVersion && payload.context?.candidates?.some(item => Number(item.candidateId) === Number(previewCandidateId.value)) ? previewCandidateId.value : null)
    || payload.context?.currentVersion?.selectedCandidateId
    || payload.context?.candidates?.[0]?.candidateId
    || payload.version?.candidates?.[0]?.candidateId
    || null
  clearIssueDraft()
  initializeVerificationDraft()
  if (!sameVersion || !carriedIssues.value.length) {
    assistantTab.value = carriedIssues.value.length ? 'carried' : 'current'
  }
  scheduleFinalDeliveryRefresh()
}

const { connectionStatus } = useVersionRealtime(computed(() => version.value?.versionId), async versionId => {
  if (loading.value || actionBusy.value || issueBusy.value || draftActionBusyId.value) return
  const expectedGeneration = pageGeneration
  const before = new Set(candidates.value.map(item => item.candidateId))
  const [response, appendContext] = await Promise.all([
    getVersionDetail(versionId),
    canReview.value && version.value?.versionStatus === 'rejected'
      ? getVersionReviewContext(versionId) : Promise.resolve(null)
  ])
  if (expectedGeneration !== pageGeneration || version.value?.versionId !== versionId
    || loading.value || actionBusy.value || issueBusy.value || draftActionBusyId.value) return
  const latest = response.data
  if (appendContext && reviewContext.value) {
    const wasAllowed = reviewContext.value.canAppendIssues
    reviewContext.value = { ...reviewContext.value, canAppendIssues: appendContext.data.canAppendIssues }
    if (wasAllowed && !appendContext.data.canAppendIssues) {
      ElMessage.info('上一版追加入口已关闭，请返回列表查看最新任务状态。')
    }
  }
  if (Number(latest.lockVersion) < Number(version.value.lockVersion)) return
  if (latest.versionStatus !== version.value.versionStatus
    || latest.selectedCandidateId !== selectedCandidateId.value) {
    realtimeConflict.value = true
    return
  }
  // 仅同步候选数据；不更换播放器、不清空问题、附件和未保存的审核意见。
  version.value = latest
  if (reviewContext.value) {
    reviewContext.value = { ...reviewContext.value, candidates: latest.candidates,
      currentVersion: { ...reviewContext.value.currentVersion,
        lockVersion: latest.lockVersion, selectedCandidateId: latest.selectedCandidateId,
        versionStatus: latest.versionStatus } }
  }
  const added = (latest.candidates || []).filter(item => !before.has(item.candidateId)).length
  if (added) ElMessage.success(`制作人新增了 ${added} 个候选，已更新候选列表`)
})

function scheduleFinalDeliveryRefresh() {
  if (finalDeliveryPollTimer) clearTimeout(finalDeliveryPollTimer)
  finalDeliveryPollTimer = null
  if (!['pending', 'publishing'].includes(finalDelivery.value?.deliveryStatus) || finalDeliveryPollCount >= 12) return
  finalDeliveryPollCount += 1
  finalDeliveryPollTimer = setTimeout(() => loadReview(), 5000)
}

async function loadReview() {
  pageController?.abort()
  const controller = new AbortController()
  const generation = ++pageGeneration
  pageController = controller
  loading.value = true
  pageError.value = null
  if (!canQueryReview.value || !canQueryVersion.value) {
    loading.value = false
    pageError.value = reviewErrorState({ httpStatus: 403, message: '当前账号没有审核单或版本详情权限' })
    return
  }
  try {
    const detailResponse = await getReviewListDetail(reviewListId.value, { signal: controller.signal })
    const detail = detailResponse.data
    const versionId = detail.autoVersionId || detail.version?.versionId || detail.versions?.[0]?.versionId
    if (!versionId && detail.reviewStatus !== 'draft') throw new Error('审核单未关联可审核版本')
    if (!versionId) {
      if (!isCurrent(controller, generation)) return
      review.value = detail
      version.value = null
      reviewContext.value = null
      actions.value = []
      return
    }
    const payload = await loadVersionReview(versionId, { signal: controller.signal })
    if (!isCurrent(controller, generation)) return
    review.value = detail
    applyVersionReview(payload, versionId)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
      pageError.value = reviewErrorState(error, '审核单加载失败')
    }
  } finally {
    if (isCurrent(controller, generation)) loading.value = false
  }
}

async function selectManualVersion(item) {
  if (Number(item.versionId) === Number(version.value?.versionId)) return
  loading.value = true
  try {
    applyVersionReview(await loadVersionReview(item.versionId), item.versionId)
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '切换审核版本失败').message)
  } finally {
    loading.value = false
  }
}

async function transitionManual(action) {
  manualBusy.value = action
  try {
    await transitionManualReviewList(review.value.reviewListId, action, { lockVersion: review.value.lockVersion })
    ElMessage.success(action === 'activate' ? '审核单已激活' : action === 'complete' ? '审核单已完成' : '审核单已归档')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '审核单状态更新失败').message)
  } finally {
    manualBusy.value = ''
  }
}

function issueContent() {
  return issueDraft.content.trim() || null
}

function validateIssueContent(_rule, _value, callback) {
  if (issueContent() || draftAnnotationCount.value) callback()
  else callback(new Error('请填写修改意见，或在画面上添加至少一个标注'))
}

function validateMediaSeconds(_rule, value, callback) {
  if (value === null || value === '') return callback()
  const seconds = Number(value)
  if (Number.isFinite(seconds) && seconds >= 0) callback()
  else callback(new Error('时间点必须是大于等于 0 的秒数'))
}

function clearIssueDraft() {
  editingDraftId.value = null
  editingPublishedId.value = null
  editingPublishedLockVersion.value = null
  editingDraftLockVersion.value = null
  Object.assign(issueDraft, { content: '', mediaSeconds: null, annotations: null })
  resetReferenceAttachments()
  issueFormRef.value?.clearValidate()
  mediaWorkspace.value?.clearDraft()
}

function cloneIssueAnnotations(annotations) {
  return annotations ? JSON.parse(JSON.stringify(annotations)) : null
}

watch(assistantTab, tab => {
  if (tab !== 'current') return
  if (carriedIssues.value.some(issue => issue.issueId === selectedIssueId.value)) {
    selectedIssueId.value = null
  }
  mediaWorkspace.value?.exitAutomaticComparison()
})

async function focusIssueDraft() {
  if (!canAddIssue.value) return
  assistantTab.value = 'current'
  issueDraftPulse.value = false
  if (issueDraftPulseTimer) clearTimeout(issueDraftPulseTimer)
  await nextTick()
  issueDraftPulse.value = true
  issueComposer.value?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
  issueContentInput.value?.focus?.()
  issueDraftPulseTimer = setTimeout(() => { issueDraftPulse.value = false }, 1500)
}

async function submitIssue() {
  if (realtimeConflict.value) return ElMessage.warning('审核状态已变化，请先保留当前意见，再刷新页面')
  if (!canAddIssue.value || issueBusy.value || actionBusy.value) return
  const isAppending = canAppendIssue.value
  issueBusy.value = true
  try {
    let valid = false
    await issueFormRef.value?.validate(result => {
      valid = result
    })
    if (!valid) return
    const content = issueContent()
    const seconds = issueDraft.mediaSeconds === null ? null : Number(issueDraft.mediaSeconds)
    if (seconds !== null && (!Number.isFinite(seconds) || seconds < 0)) {
      ElMessage.error('作品时间点无效，请重新从播放器记录')
      return
    }
    const payload = {
      issueScope: issueScope.value,
      candidateId: issueScope.value === 'version' ? null : activeCandidate.value.candidateId,
      content,
      mediaTimeMs: seconds === null ? null : Math.round(seconds * 1000),
      annotations: issueDraft.annotations,
      referenceFileIds: []
    }
    if (isAppending) {
      try {
        await ElMessageBox.confirm(
          editingPublishedId.value ? '修改将立即同步给制作人，并保留修改记录。确认保存吗？' : '追加问题将立即发送给制作人，制作人提交下一版前可编辑本人意见。确认追加吗？',
          editingPublishedId.value ? '修改已发布意见' : '确认追加问题',
          { type: 'warning', confirmButtonText: editingPublishedId.value ? '保存并同步' : '追加并发送', cancelButtonText: '继续补充' }
        )
      } catch {
        return
      }
    }
    await uploadPendingReferenceFiles()
    payload.referenceFileIds = referenceAttachments.value.map(file => file.fileId)
    if (editingPublishedId.value) {
      await updatePublishedVersionIssue(version.value.versionId, editingPublishedId.value, {
        ...payload, lockVersion: editingPublishedLockVersion.value
      })
    } else if (isAppending) {
      await appendVersionIssue(version.value.versionId, {
        ...payload,
        lockVersion: reviewContext.value?.currentVersion?.lockVersion ?? version.value.lockVersion
      })
    } else if (editingDraftId.value) {
      await updateVersionIssueDraft(version.value.versionId, editingDraftId.value, {
        ...payload,
        lockVersion: editingDraftLockVersion.value
      })
    } else {
      await addVersionIssueDraft(version.value.versionId, payload)
    }
    const wasPublishedEditing = Boolean(editingPublishedId.value)
    const wasEditing = Boolean(editingDraftId.value)
    clearIssueDraft()
    if (wasPublishedEditing) ElMessage.success('修改已保存并同步给制作人')
    else if (isAppending) showWorkflowSuccess('issueAppended')
    else ElMessage.success(wasEditing ? '问题草稿已更新，制作人仍不可见' : '问题已保存为草稿，点击“退回并发送问题”后才会发送给制作人')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, isAppending ? '追加问题失败' : editingDraftId.value ? '更新问题草稿失败' : '保存问题草稿失败').message)
  } finally {
    issueBusy.value = false
  }
}

async function editIssueDraft(draft) {
  if (hasUnsavedIssueDraft.value) return ElMessage.warning('请先保存或清空当前草稿')
  if (draft.candidateId != null && !candidates.value.some(item => Number(item.candidateId) === Number(draft.candidateId))) return ElMessage.warning('问题所属文件不可用')
  issueScope.value = draft.candidateId == null ? 'version' : 'candidate'
  if (draft.candidateId != null) previewCandidateId.value = draft.candidateId
  savedIssuesTab.value = draft.candidateId == null ? 'overall' : String(draft.candidateId)
  await nextTick()
  editingDraftId.value = draft.draftId
  editingDraftLockVersion.value = draft.lockVersion
  Object.assign(issueDraft, {
    content: draft.content || '',
    mediaSeconds: draft.mediaTimeMs === null || draft.mediaTimeMs === undefined
      ? null
      : Number((Number(draft.mediaTimeMs) / 1000).toFixed(3)),
    annotations: cloneIssueAnnotations(draft.annotations)
  })
  resetReferenceAttachments((draft.referenceFiles || []).map(file => ({ ...file })))
  selectedIssueId.value = `draft-${draft.draftId}`
  await nextTick()
  mediaWorkspace.value?.loadDraft(draft.annotations, draft.mediaTimeMs)
  await focusIssueDraft()
}

function canEditPublishedIssue(issue) {
  return !realtimeConflict.value && canAddIssue.value && canAppendIssue.value && issue.status === 'open'
    && Number(issue.reviewerUserId) === Number(sessionStore.user?.userId)
}

async function editPublishedIssue(issue) {
  if (!canEditPublishedIssue(issue) || issueBusy.value || hasUnsavedIssueDraft.value) return
  await editIssueDraft({ ...issue, candidateId: issue.originCandidateId, versionId: issue.originVersionId, draftId: null })
  editingPublishedId.value = issue.issueId
  editingPublishedLockVersion.value = reviewContext.value?.currentVersion?.lockVersion ?? version.value.lockVersion
  selectedIssueId.value = issue.issueId
}

async function removeIssueDraft(draft) {
  if (realtimeConflict.value) return ElMessage.warning('审核状态已变化，请先保留当前意见，再刷新页面')
  if (draftActionBusyId.value) return
  try {
    await ElMessageBox.confirm(
      '删除后该问题草稿不会发送给制作人，且无法恢复。确认删除吗？',
      '删除问题草稿',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  draftActionBusyId.value = draft.draftId
  try {
    await deleteVersionIssueDraft(version.value.versionId, draft.draftId, { lockVersion: draft.lockVersion })
    if (editingDraftId.value === draft.draftId) clearIssueDraft()
    ElMessage.success('问题草稿已删除')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '删除问题草稿失败').message)
  } finally {
    draftActionBusyId.value = null
  }
}

function captureMediaTime(milliseconds) {
  if (issueScope.value === 'version') return ElMessage.info('整体反馈不绑定视频时间点，请切换到当前文件反馈')
  issueDraft.mediaSeconds = Number((Number(milliseconds) / 1000).toFixed(3))
  focusIssueDraft()
}

function updateAnnotations(annotations) {
  if (issueScope.value === 'version') return
  issueDraft.annotations = annotations
  if (draftAnnotationCount.value) {
    issueFormRef.value?.clearValidate('content')
    focusIssueDraft()
  }
}

function returnToDraftPosition() {
  mediaWorkspace.value?.seekToDraft(issueDraftMediaTimeMs.value)
}

async function focusIssue(issue) {
  const sourceVersionId = Number(issue.originVersionId ?? issue.versionId)
  const isCurrentVersionIssue = sourceVersionId === Number(version.value?.versionId)
  const boundCandidateId = issue.originCandidateId ?? issue.candidateId
  if (isCurrentVersionIssue && boundCandidateId !== null && boundCandidateId !== undefined) {
    const targetCandidate = candidates.value.find(candidate => (
      Number(candidate.candidateId) === Number(boundCandidateId)
    ))
    if (!targetCandidate) {
      ElMessage.warning('该问题绑定的候选作品当前不可用，无法定位到对应画面')
      return
    }
    if (Number(activeCandidate.value?.candidateId) !== Number(targetCandidate.candidateId)) {
      if (hasUnsavedIssueDraft.value) {
        ElMessage.warning('请先保存或清空当前问题草稿，再查看其他候选的问题')
        return
      }
      previewCandidateId.value = targetCandidate.candidateId
      clearIssueDraft()
    }
  }
  selectedIssueId.value = issue.issueId
  await nextTick()
  reviewWorkStep.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  mediaWorkspace.value?.seekToNote()
}

function openTask() {
  if (review.value?.taskId) navigate(`/tasks/${review.value.taskId}#version-workspace`)
}

function candidateMediaName(candidate) {
  return candidate.files?.find(item => item.role === 'review_media')?.businessFileName || '尚无可播放文件'
}

async function previewCandidate(candidate) {
  const isSwitching = Number(activeCandidate.value?.candidateId) !== Number(candidate.candidateId)
  if (isSwitching && hasUnsavedIssueDraft.value) {
    ElMessage.warning('请先保存或清空当前问题草稿，再切换候选预览')
    return
  }
  if (isSwitching) {
    previewCandidateId.value = candidate.candidateId
    selectedIssueId.value = null
    clearIssueDraft()
  }
  await nextTick()
  reviewWorkStep.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  candidatePreviewPulse.value = false
  await nextTick()
  candidatePreviewPulse.value = true
  if (candidatePreviewPulseTimer) clearTimeout(candidatePreviewPulseTimer)
  candidatePreviewPulseTimer = setTimeout(() => {
    candidatePreviewPulse.value = false
  }, 900)
}

const approvalVisible = ref(false)
const approvalFormRef = ref(null)
const approvalForm = reactive({ candidateId: null })
const approvalRules = { candidateId: [{ required: true, message: '请选择最终交付文件', trigger: 'change' }] }

function openApproval() {
  if (!canApprove.value || actionBusy.value || issueBusy.value) return
  if (hasUnsavedIssueDraft.value) return ElMessage.warning('请先保存或清空未保存的问题草稿')
  approvalForm.candidateId = null
  approvalVisible.value = true
  nextTick(() => approvalFormRef.value?.clearValidate())
}

async function confirmApproval() {
  if (actionBusy.value) return
  if (!await approvalFormRef.value?.validate().catch(() => false)) return
  await submitDecision('approve')
}

function candidateIssueCount(candidate) {
  return currentVersionDrafts.value.filter(item => Number(item.candidateId) === Number(candidate.candidateId)).length
    + currentVersionIssues.value.filter(item => Number(item.originCandidateId) === Number(candidate.candidateId)).length
}


async function submitDecision(actionType, revisionTransfer = null, confirmed = false) {
  if (realtimeConflict.value) return ElMessage.warning('审核状态已变化，请先保留当前意见，再刷新页面')
  if (!canSubmitDecision.value || actionBusy.value || issueBusy.value) return
  if (hasUnsavedIssueDraft.value) {
    ElMessage.warning('还有未保存的问题草稿，请先保存或清空后再提交审核结论')
    return
  }
  if (actionType !== 'defer' && !verificationComplete.value) {
    ElMessage.warning('请逐条确认上一版问题；选择“仍然存在”时必须填写未解决原因')
    return
  }
  if (actionType === 'approve' && !canApprove.value) {
    ElMessage.warning('只有上一版问题全部修复且当前版没有新问题时才能通过')
    return
  }
  if (actionType === 'reject' && !canReject.value) {
    ElMessage.warning('退回前需要存在仍未修复的历史问题，或至少一条当前版新问题')
    return
  }
  if (actionType === 'reject' && !confirmed && hasPermission('shotgrid:task:assign')) {
    transferDialog.value.open(version.value.versionId, transfer => submitDecision('reject', transfer, true))
    return
  }
  actionBusy.value = actionType
  try {
    if (actionType === 'reject' && !confirmed) {
      try {
        await ElMessageBox.confirm(
          `是否已检查完所有问题，还有没有需要补充的内容？目前有 ${currentVersionDrafts.value.length} 条新问题。`,
          '确认退回并发布问题',
          { type: 'warning', confirmButtonText: '已检查完，退回并发送', cancelButtonText: '继续检查和补充' }
        )
      } catch {
        return
      }
    }
    const payload = {
      actionType,
      ...(revisionTransfer ? { revisionTransfer } : {}),
      selectedCandidateId: actionType === 'approve' ? approvalForm.candidateId : null,
      reason: decisionReason.value.trim() || null,
      lockVersion: reviewContext.value?.currentVersion?.lockVersion ?? version.value.lockVersion,
      issueVerifications: actionType === 'defer' ? [] : verificationItems.value
    }
    const context = { reviewListId: reviewListId.value, versionId: version.value.versionId, ...payload }
    const response = await createReviewAction(version.value.versionId, payload, actionIdempotency.forPayload(context))
    actionIdempotency.reset()
    approvalVisible.value = false
    let successPrompt
    if (actionType === 'approve' && response.data?.finalDelivery) {
      finalDeliveryPollCount = 0
      successPrompt = showWorkflowSuccess('approvedPublishing')
    } else {
      successPrompt = showWorkflowSuccess({ approve: 'approved', reject: 'rejected', defer: 'deferred' }[actionType])
    }
    successPrompt.then(confirmed => {
      if (confirmed && !disposed && props.embedded && ['approve', 'reject'].includes(actionType) &&
          reviewListId.value === context.reviewListId) emit('completed')
    })
    await loadReview()
    return true
  } catch (error) {
    const state = reviewErrorState(error, '审核决定提交失败')
    ElMessage.error(state.status === 409 ? `${state.message}，页面正在刷新` : state.message)
    if (state.status === 409) await loadReview()
  } finally {
    actionBusy.value = ''
  }
}

async function retryFailedFinalDelivery() {
  if (finalDeliveryRetryBusy.value || finalDelivery.value?.deliveryStatus !== 'failed') return
  finalDeliveryRetryBusy.value = true
  try {
    await retryFinalDelivery(version.value.versionId)
    finalDeliveryPollCount = 0
    ElMessage.success('最终版本已重新进入 NAS 发布队列')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '最终版本重试失败').message)
  } finally {
    finalDeliveryRetryBusy.value = false
  }
}

function updateAssistantMode() {
  assistantAffixed.value = !props.embedded && typeof window !== 'undefined' && window.innerWidth > 1100
}

onMounted(() => {
  updateAssistantMode()
  const drawerBody = props.embedded && reviewPage.value?.closest('.el-drawer__body')
  if (drawerBody) {
    // 抽屉独立滚动，两侧高度以抽屉可视区域为准。
    const updateDrawerHeight = () => {
      drawerSidebarHeight.value = `${Math.max(0, drawerBody.clientHeight - 24)}px`
    }
    updateDrawerHeight()
    drawerResizeObserver = new ResizeObserver(updateDrawerHeight)
    drawerResizeObserver.observe(drawerBody)
  }
  window.addEventListener('resize', updateAssistantMode)
  loadReview()
})
onBeforeUnmount(() => {
  disposed = true
  drawerResizeObserver?.disconnect()
  pageGeneration += 1
  pageController?.abort()
  if (issueDraftPulseTimer) clearTimeout(issueDraftPulseTimer)
  if (candidatePreviewPulseTimer) clearTimeout(candidatePreviewPulseTimer)
  if (finalDeliveryPollTimer) clearTimeout(finalDeliveryPollTimer)
  resetReferenceAttachments()
  window.removeEventListener('resize', updateAssistantMode)
})
</script>

<template>
  <section ref="reviewPage" class="sg-page review-detail-page" :class="{ 'review-detail-page--embedded': embedded }" :style="embedded ? { '--drawer-sidebar-height': drawerSidebarHeight } : undefined">
    <RevisionTransferDialog ref="transferDialog" />
    <header class="sg-page-heading">
      <div class="review-detail-heading">
        <el-button v-if="!embedded" link :icon="ArrowLeft" @click="navigate('/reviews')">返回审核列表</el-button>
        <el-button v-if="version && canQueryVersion" link @click="navigate(`/versions/${version.versionId}`)">查看对应版本</el-button>
        <div v-if="review"><p class="sg-eyebrow">REVIEW DETAIL</p><h2>{{ review.reviewListName }}</h2><p>审核意见绑定提出时的版本；下一版必须逐条说明修改结果，并由审核人逐条确认。</p></div>
      </div>
      <div class="heading-actions"><span v-if="connectionStatus" class="realtime-status">{{ connectionStatus === 'connected' ? '实时同步已连接' : '连接恢复中，自动补查' }}</span><el-tag v-if="review" size="small" effect="plain" round :type="tagTypeFromTone(reviewModeMeta(review.reviewMode).tone)">{{ reviewModeMeta(review.reviewMode).label }}</el-tag><el-tag v-if="review" size="small" effect="light" round :type="tagTypeFromTone(reviewStatusMeta(review.reviewStatus).tone)">{{ reviewStatusMeta(review.reviewStatus).label }}</el-tag><el-button :icon="Refresh" :loading="loading" @click="loadReview">刷新</el-button></div>
    </header>

    <el-alert v-if="realtimeConflict" title="审核状态或候选文件已被其他人修改" description="当前意见已保留。请先复制未保存内容，再刷新页面核对最新审核状态。" type="warning" :closable="false" show-icon />
    <ProjectStatePanel v-if="pageError" :title="pageError.title" :message="pageError.message" :retryable="pageError.retryable" @retry="loadReview" />
    <el-card v-else-if="loading && !version" class="review-detail-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="9" /></el-card>
    <template v-else-if="review">
      <el-card v-if="version" class="review-identity" shadow="never">
        <strong>{{ version.taskName || review.reviewListName }} · {{ version.versionNumber }}</strong>
        <el-descriptions :column="3" size="small">
          <el-descriptions-item label="本版提交人"><strong>{{ version.submitterName || '—' }}</strong></el-descriptions-item>
          <el-descriptions-item label="审核记录">{{ actions.length ? `${actions[0].reviewerName || '审核人'} · ${reviewActionMeta(actions[0].actionType).label}` : '等待项目审核人处理' }}</el-descriptions-item>
          <el-descriptions-item label="正在查看">{{ activeCandidate?.candidateNumber || '—' }}</el-descriptions-item>
          <el-descriptions-item v-if="version.assigneeUserId && Number(version.assigneeUserId) !== Number(version.submittedBy)" label="当前修改负责人">{{ version.assigneeName }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
      <el-descriptions class="review-context-strip" :column="4" border>
        <el-descriptions-item label="当前版本">{{ version?.versionNumber || '—' }}</el-descriptions-item>
        <el-descriptions-item label="历史问题待确认">{{ carriedIssues.length }}</el-descriptions-item>
        <el-descriptions-item label="待发布问题草稿"><strong :class="{ danger: currentVersionDrafts.length }">{{ currentVersionDrafts.length }}</strong></el-descriptions-item>
        <el-descriptions-item label="关联任务">{{ version?.taskId ? `#${version.taskId}` : '批量队列' }}</el-descriptions-item>
      </el-descriptions>

      <el-card v-if="review.reviewMode === 'manual_batch'" class="manual-strip" shadow="never">
        <header><div><p class="sg-eyebrow">BATCH QUEUE</p><h3>审核版本队列</h3></div><div><el-button v-if="review.reviewStatus === 'draft' && canActivateManual" type="primary" :loading="manualBusy === 'activate'" @click="transitionManual('activate')">激活审核单</el-button><el-button v-if="review.reviewStatus === 'active' && canCompleteManual" type="success" :loading="manualBusy === 'complete'" @click="transitionManual('complete')">完成审核单</el-button><el-button v-if="review.reviewStatus !== 'archived' && canArchiveManual" :loading="manualBusy === 'archive'" @click="transitionManual('archive')">归档</el-button></div></header>
        <div v-if="manualVersions.length" class="manual-version-list"><el-button v-for="item in manualVersions" :key="item.versionId" :type="Number(activeManualVersionId) === Number(item.versionId) ? 'primary' : 'default'" :loading="loading && Number(activeManualVersionId) === Number(item.versionId)" :disabled="loading" @click="selectManualVersion(item)">{{ item.versionNumber }} · 任务 #{{ item.taskId }}</el-button></div><el-empty v-else class="empty-block" :image-size="48" description="当前草稿还没有版本，请返回审核列表添加版本" />
      </el-card>

      <div v-if="version" class="review-detail-grid">
        <aside class="candidate-navigation" aria-label="候选导航">
          <el-card class="candidate-selector" shadow="never">
            <header><div><p class="sg-eyebrow">CANDIDATES</p><h3>候选导航</h3><p>逐个查看文件，记录批注和修改意见。</p></div><el-tag effect="plain" round>{{ candidates.length }} 个文件</el-tag></header>
            <el-scrollbar class="candidate-navigation__scroll">
            <ElRadioGroup :model-value="activeCandidate?.candidateId" class="candidate-selector__list" aria-label="选择要预览的候选文件">
              <el-card v-for="candidate in candidates" :key="candidate.candidateId" class="candidate-choice" :class="{ 'is-previewing': Number(activeCandidate?.candidateId) === Number(candidate.candidateId), 'is-selected': version.versionStatus === 'final' && Number(selectedCandidateId) === Number(candidate.candidateId) }" shadow="never">
                <ElRadio class="candidate-choice__preview" :value="candidate.candidateId" @click="previewCandidate(candidate)">
                  <ReviewCandidateThumbnail :version-id="version.versionId" :candidate="candidate" :active="Number(activeCandidate?.candidateId) === Number(candidate.candidateId)" :can-preview="canDownload" />
                  <span class="candidate-choice__meta"><span><strong>{{ candidate.candidateNumber }}</strong><el-tag v-if="version.versionStatus === 'final' && Number(selectedCandidateId) === Number(candidate.candidateId)" size="small" type="success" effect="plain" round>最终交付</el-tag></span><small v-if="candidate.candidateNote?.trim()">{{ candidate.candidateNote }}</small><small class="candidate-choice__file">{{ candidateMediaName(candidate) }}</small></span>
                </ElRadio>
                <div class="candidate-choice__actions"><el-tag class="candidate-choice__issue-count" :class="{ 'has-issues': candidateIssueCount(candidate) > 0 }" :type="candidateIssueCount(candidate) > 0 ? 'warning' : 'info'" :effect="candidateIssueCount(candidate) > 0 ? 'dark' : 'plain'" size="small" round>{{ candidateIssueCount(candidate) }} 条问题</el-tag><el-tag v-if="Number(activeCandidate?.candidateId) === Number(candidate.candidateId)" size="small">正在审阅</el-tag></div>
              </el-card>
            </ElRadioGroup>
            </el-scrollbar>
          </el-card>

        </aside>
        <main class="review-main">
          <div class="review-version-context" aria-label="当前审核版本">
            <div><strong>当前审核 · {{ version.versionNumber }}</strong><p>{{ version.submitterName || '制作人' }} · {{ formatReviewDateTime(version.submittedTime) }}</p></div>
            <el-button v-if="canListVersions && canQueryVersion" type="primary" plain @click="historyVisible = true">版本记录</el-button>
          </div>
          <ReviewProductionTarget v-if="version.productionTarget" :target="version.productionTarget" :task-id="Number(version.taskId)" :project-id="Number(version.projectId)" :can-read-references="hasPermission('shotgrid:task:query')" />

          <section ref="reviewWorkStep" class="review-work-step" :class="{ 'is-candidate-focus': candidatePreviewPulse }">
            <header class="work-step-heading"><span class="step-number">1</span><div><strong>播放并检查 {{ activeCandidate?.candidateNumber || '当前候选' }}</strong><p>可对每个文件记录问题和画面批注；通过时再选择最终交付文件。</p></div></header>
            <ReviewMediaWorkspace
              ref="mediaWorkspace"
              :version="reviewVersion"
              :selected-note="selectedIssue"
              :can-download="canDownload"
              :can-compare="canListVersions"
              :can-annotate="canAddIssue && issueScope === 'candidate'"
              :draft-media-time-ms="issueDraftMediaTimeMs"
              :draft-annotation-count="draftAnnotationCount"
              @capture-time="captureMediaTime"
              @start-issue="focusIssueDraft"
              @annotations-change="updateAnnotations"
              @clear-note-focus="selectedIssueId = null"
            />
          </section>

          <CandidateGenerationPrompt :candidate="activeCandidate" :version="version" @saved="version = $event" />
          <VersionDetailCard :version="reviewVersion" :can-download="canDownload" :show-preview="false" />

          <el-card class="action-history" shadow="never">
            <header><div><p class="sg-eyebrow">HISTORY</p><h3>审核动作记录</h3></div><span>{{ actions.length }} 条</span></header>
            <el-timeline v-if="actions.length" class="action-list"><el-timeline-item v-for="item in actions" :key="item.actionId" :type="tagTypeFromTone(reviewActionMeta(item.actionType).tone)" :timestamp="formatReviewDateTime(item.createTime)" placement="top"><strong>{{ reviewActionMeta(item.actionType).label }}</strong><p>{{ item.reason || '未填写整体说明' }}</p><small>{{ item.reviewerName || `用户 #${item.reviewerUserId}` }}</small><span class="action-transition"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.fromStatus).tone)">{{ taskVersionStatusMeta(item.fromStatus).label }}</el-tag><span aria-hidden="true">→</span><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.toStatus).tone)">{{ taskVersionStatusMeta(item.toStatus).label }}</el-tag></span></el-timeline-item></el-timeline>
            <el-empty v-else class="empty-block" :image-size="44" description="尚无审核动作" />
          </el-card>
        </main>

        <component :is="assistantShell" v-bind="assistantShellProps" class="review-assistant-affix">
          <aside class="review-assistant">
            <header class="assistant-heading"><div><p class="sg-eyebrow">REVIEW NOTES</p><h3>审核记录</h3></div><el-tag size="small" effect="plain" round>随作品保持可见</el-tag></header>

            <ElTabs v-model="assistantTab" class="assistant-work-tabs" stretch aria-label="审核工作区">
              <ElTabPane v-if="carriedIssues.length" name="carried" :label="`上轮复核 ${completedVerificationCount}/${carriedIssues.length}`">
                  <el-alert class="verification-guidance" :type="verificationComplete ? 'success' : 'warning'" :closable="false" show-icon :title="verificationComplete ? '上轮问题已全部确认' : `请逐条复核，还剩 ${carriedIssues.length - completedVerificationCount} 条`" />
                <el-scrollbar class="assistant-body">
                <section class="assistant-section carried-panel">
                  <ElTabs v-model="carriedFileTab" type="border-card" class="carried-file-tabs" aria-label="按来源文件复核问题">
                    <ElTabPane v-for="pane in carriedFilePanes" :key="pane.name" :name="pane.name" :label="`${pane.label} ${carriedFileProgress(pane)}`">
                  <div class="issue-list carried-list">
                    <el-card v-for="issue in pane.issues" :key="issue.issueId" class="issue-card" :class="{ 'is-selected': selectedIssueId === issue.issueId }" shadow="never">
                      <header><span>{{ issue.originCandidateId == null ? `${issue.originVersionNumber} · 整体反馈` : issue.originCandidateNumber || `${issue.originVersionNumber} · 来源文件待确认` }} 问题</span><el-button v-if="issue.originCandidateId != null" size="small" class="carried-annotation-button" type="primary" @click="focusIssue(issue)">{{ issue.annotations?.items?.length ? `查看标注 ${issue.annotations.items.length} 处` : '定位原版意见' }}</el-button></header>
                      <p>{{ issue.content || '该问题仅包含画面标注' }}</p>
                      <ReviewReferenceFiles :files="issue.referenceFiles || []" compact />
                      <div class="maker-response"><span>制作人对 {{ version.versionNumber }} 的处理说明</span><strong>{{ issue.currentVersionResponse.responseText }}</strong></div>
                      <div class="verification-choice" :class="{ 'is-pending': !verificationDraft[issue.issueId].result }">
                        <p class="verification-choice__prompt">{{ verificationDraft[issue.issueId].result ? '已选择复核结果，可点击更改' : '请点击选择：这个问题修好了吗？' }}</p>
                        <el-radio-group v-model="verificationDraft[issue.issueId].result" class="verification-options" aria-label="选择本条问题的复核结果">
                          <el-radio-button value="resolved">{{ verificationDraft[issue.issueId].result === 'resolved' ? '✓ 已确认修复' : '确认已修复' }}</el-radio-button>
                          <el-radio-button value="still_present">{{ verificationDraft[issue.issueId].result === 'still_present' ? '✓ 问题仍存在' : '问题仍存在' }}</el-radio-button>
                        </el-radio-group>
                      </div>
                      <label v-if="verificationDraft[issue.issueId].result === 'still_present'" class="verification-comment">
                        <span>说明仍然存在的问题 <em>*</em></span>
                        <el-input v-model="verificationDraft[issue.issueId].comment" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="请具体说明哪里仍未达到要求，方便制作人下一轮准确修改。" />
                      </label>
                    </el-card>
                  </div>
                                  </ElTabPane>
                  </ElTabs>
                </section>

                </el-scrollbar>
              </ElTabPane>
              <ElTabPane name="current" :label="`本轮意见 ${currentIssueCount}`">
                <el-scrollbar class="assistant-body">
                <section ref="issueComposer" class="assistant-section current-panel" :class="{ 'is-draft-focus': issueDraftPulse }">
                  <header class="assistant-section-heading"><span class="step-number">2</span><div><div class="issue-compose-heading"><h3>{{ canReview ? '填写修改意见' : '已发送的修改意见' }}</h3></div><p>{{ !canReview ? '查看已正式发送的意见、画面标注和处理记录。' : canAppendIssue ? '制作人提交下一版前可追加问题；确认发送后制作人立即可见。' : isReviewDecisionOpen ? '先保存草稿，退回时统一发送给制作人。' : '本轮已结束。仅在任务待修改且制作人尚未提交下一版时可以追加问题。' }}</p></div></header>
                  <ElTabs v-if="canAddIssue" :model-value="issueScope" type="border-card" :before-leave="canChangeIssueScope" @update:model-value="changeIssueScope" class="issue-scope-tabs" aria-label="选择反馈范围">
                    <ElTabPane v-for="scope in [{ name: 'version', label: '整体反馈意见' }, { name: 'candidate', label: '填写修改意见' }]" :key="scope.name" :name="scope.name" :label="scope.label">
                      <template #label>
                        <span class="issue-scope-label">{{ scope.label }}<el-tag v-if="scope.name === 'candidate' && activeCandidate" class="issue-candidate-tag" size="small" effect="dark" round :aria-label="`当前文件：${activeCandidate.candidateNumber}`">{{ activeCandidate.candidateNumber }}</el-tag></span>
                      </template>
                  <el-form v-if="issueScope === scope.name" :ref="el => { if (el) issueFormRef = el }" :disabled="issueBusy || Boolean(actionBusy)" :model="issueDraft" :rules="issueRules" class="issue-compose" label-position="top" aria-label="记录当前版新问题">
                    <el-form-item label="修改意见" prop="content"><el-input :ref="el => { if (el) issueContentInput = el }" v-model="issueDraft.content" type="textarea" :rows="4" maxlength="10000" show-word-limit placeholder="请说明需要修改的内容，例如：降低眼睛红色饱和度，并保持肤色不变。" /></el-form-item>
                    <el-form-item label="参考内容（可选）" prop="referenceFiles">
                      <ReviewReferenceInput :files="referenceAttachments" :disabled="issueBusy || Boolean(actionBusy)" @add="addReferenceFile" @remove="removeReferenceFile" />
                    </el-form-item>
                    <el-form-item v-if="issueDraftMediaTimeMs !== null || draftAnnotationCount" label="作品定位">
                      <div class="issue-compose-meta">
                        <div class="issue-context-tags">
                          <el-button v-if="issueDraftMediaTimeMs !== null" class="issue-position-button" size="small" plain round @click="returnToDraftPosition">回到 {{ formatMediaTime(issueDraftMediaTimeMs) }}</el-button>
                          <el-button v-if="draftAnnotationCount" class="issue-position-button" size="small" type="warning" plain round @click="returnToDraftPosition">查看 {{ draftAnnotationCount }} 处标注</el-button>
                        </div>
                        <el-button link type="danger" @click="clearIssueDraft">清除定位</el-button>
                      </div>
                    </el-form-item>
                    <el-form-item class="issue-compose__actions"><el-button v-if="hasUnsavedIssueDraft" :disabled="issueBusy" @click="clearIssueDraft">{{ editingDraftId || editingPublishedId ? '取消编辑' : canAppendIssue ? '清空内容' : '清空草稿' }}</el-button><el-button type="primary" :loading="issueBusy" @click="submitIssue">{{ editingPublishedId ? '保存并同步修改' : canAppendIssue ? '追加并发送问题' : editingDraftId ? '更新问题草稿' : '保存问题草稿' }}</el-button></el-form-item>
                  </el-form>
                    </ElTabPane>
                  </ElTabs>
                  <section class="saved-issues-section" aria-label="已记录修改意见">
                  <ElTabs v-model="savedIssuesTab" type="border-card" :before-leave="canLeaveSavedIssueTab" @tab-click="pane => switchSavedIssueCandidate(pane.paneName)" class="saved-issues-tabs" aria-label="按文件查看修改意见">
                    <ElTabPane v-for="pane in savedIssuePanes" :key="pane.name" :name="pane.name" :label="pane.label">
                      <template v-if="savedIssuesTab === pane.name">
                        <el-empty v-if="!pane.drafts.length && !pane.issues.length" :image-size="32" :description="`${pane.label} 暂无意见`" />
                  <div v-if="pane.drafts.length" class="issue-list current-list">
                    <el-card v-for="draft in pane.drafts" :key="draft.draftId" class="issue-card issue-draft-card" :class="{ 'is-selected': selectedIssueId === `draft-${draft.draftId}` }" shadow="never">
                      <header>
                        <span>待提交草稿 #{{ currentVersionDrafts.indexOf(draft) + 1 }}</span>
                        <div class="issue-card-actions">
                          <el-button v-if="draft.candidateId != null" link type="primary" @click="focusIssue({ ...draft, issueId: `draft-${draft.draftId}`, originVersionId: draft.versionId })">{{ draft.annotations?.items?.length ? `查看标注 ${draft.annotations.items.length} 处` : '查看对应作品' }}</el-button>
                          <el-button link type="warning" :disabled="Boolean(draftActionBusyId)" @click="editIssueDraft(draft)">编辑</el-button>
                          <el-button link type="danger" :loading="draftActionBusyId === draft.draftId" :disabled="Boolean(draftActionBusyId)" @click="removeIssueDraft(draft)">删除</el-button>
                        </div>
                      </header>
                      <p>{{ draft.content || '该问题仅包含画面标注' }}</p>
                      <ReviewReferenceFiles :files="draft.referenceFiles || []" compact />
                      <small>{{ draft.reviewerName || `审核人 #${draft.reviewerUserId}` }} · {{ formatReviewDateTime(draft.updateTime) }}</small>
                    </el-card>
                  </div>
                  <div v-if="pane.issues.length" class="issue-list current-list">
                    <el-card v-for="(issue, index) in pane.issues" :key="issue.issueId" class="issue-card" :class="{ 'is-selected': selectedIssueId === issue.issueId }" shadow="never">
                      <header>
                        <span>已发布修改要求 #{{ index + 1 }}</span>
                        <div class="issue-card-actions"><el-button v-if="issue.originCandidateId != null" link type="primary" @click="focusIssue(issue)">查看对应作品</el-button><el-button v-if="canEditPublishedIssue(issue)" link type="warning" :disabled="issueBusy" @click="editPublishedIssue(issue)">编辑</el-button></div>
                      </header>
                      <p>{{ issue.content || '该问题仅包含画面标注' }}</p>
                      <ReviewReferenceFiles :files="issue.referenceFiles || []" compact />
                      <small>{{ issue.reviewerName || `审核人 #${issue.reviewerUserId}` }} · {{ formatReviewDateTime(issue.createTime) }}</small>
                      <p v-for="response in issue.responses || []" :key="response.versionId">{{ response.versionNumber }} 处理说明：{{ response.responseText }}</p>
                      <p v-for="verification in issue.verifications || []" :key="verification.checkedVersionId">{{ verification.checkedVersionNumber }} 审核确认：{{ verification.result === 'resolved' ? '已修复' : '仍然存在' }}<template v-if="verification.comment"> · {{ verification.comment }}</template></p>
                    </el-card>
                  </div>
                      </template>
                    </ElTabPane>
                  </ElTabs>
                  </section>
                </section>
                </el-scrollbar>
              </ElTabPane>
            </ElTabs>

            <section v-if="canReview" class="assistant-section decision-panel">
              <header class="assistant-section-heading"><span class="step-number">3</span><div><h3>提交审核结论</h3><p>确认所有问题后，再完成本轮审核。</p></div></header>
              <el-alert
                v-if="finalDeliveryAlert"
                class="final-delivery-alert"
                :type="finalDeliveryAlert.type"
                :title="finalDeliveryAlert.title"
                :closable="false"
                show-icon
              >
                <code v-if="finalDeliveryAlert.path" class="final-delivery-path" aria-label="NAS 发布路径">{{ finalDeliveryAlert.path }}</code>
                <span class="final-delivery-note">{{ finalDeliveryAlert.description }}</span>
              </el-alert>
              <el-button v-if="finalDelivery?.deliveryStatus === 'failed' && canRetryFinalDelivery" type="warning" plain :loading="finalDeliveryRetryBusy" @click="retryFailedFinalDelivery">重新发布最终版本</el-button>
              <div class="decision-summary">
                <template v-if="isReviewDecisionOpen">
                  <span v-if="carriedIssues.length">上轮已确认 {{ completedVerificationCount }}/{{ carriedIssues.length }} 条</span>
                  <span v-else>已保存草稿 {{ currentVersionDrafts.length }} 条</span>
                  <strong v-if="unresolvedVerificationCount || currentIssueCount" class="danger">退回将发送 {{ unresolvedVerificationCount + currentIssueCount }} 条</strong>
                  <strong v-else-if="verificationComplete" class="success">当前没有待修改问题</strong>
                </template>
                <template v-else>
                  <span v-if="version.versionStatus === 'rejected'">本轮已发布 {{ currentVersionIssues.length }} 条修改要求</span>
                  <span v-else>本轮审核已经结束</span>
                </template>
              </div>
              <el-input v-show="false" v-model="decisionReason" type="textarea" :rows="2" maxlength="1000" placeholder="本轮审核整体说明（可选）" />
              <el-button v-if="isReviewDecisionOpen && !verificationComplete" class="decision-review-cta" type="primary" size="large" @click="assistantTab = 'carried'">
                <span>去复核上轮问题（{{ carriedIssues.length - completedVerificationCount }} 条待确认）</span>
                <el-icon><ArrowRight /></el-icon>
              </el-button>
              <div class="decision-actions">
                <el-button type="success" :loading="actionBusy === 'approve'" :disabled="!canApprove || Boolean(actionBusy)" @click="openApproval">全部符合，确认通过</el-button>
                <el-button type="danger" plain :loading="actionBusy === 'reject'" :disabled="!canReject || Boolean(actionBusy)" @click="submitDecision('reject')">退回并发送问题{{ currentVersionDrafts.length ? `（${currentVersionDrafts.length}）` : '' }}</el-button>
                <el-button :loading="actionBusy === 'defer'" :disabled="!canSubmitDecision || Boolean(actionBusy)" @click="submitDecision('defer')">稍后决定</el-button>
              </div>
              <el-button v-if="version.versionStatus === 'rejected'" link type="primary" @click="openTask">查看制作任务</el-button>
            </section>
          </aside>
        </component>
      </div>
    </template>
    <el-dialog v-model="approvalVisible" title="选择最终交付文件并通过" width="520px" :close-on-click-modal="false" :close-on-press-escape="!actionBusy" :show-close="!actionBusy" destroy-on-close>
      <p>本轮审核通过后，所选文件将交付到 NAS 的 FINAL 目录。</p>
      <el-form ref="approvalFormRef" :model="approvalForm" :rules="approvalRules" label-position="top" :disabled="Boolean(actionBusy)">
        <el-form-item label="最终交付文件" prop="candidateId">
          <el-select v-model="approvalForm.candidateId" placeholder="选择最终交付文件" style="width:100%">
            <el-option v-for="candidate in candidates" :key="candidate.candidateId" :value="candidate.candidateId" :label="`${candidate.candidateNumber} · ${candidateMediaName(candidate)}`" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button :disabled="Boolean(actionBusy)" @click="approvalVisible = false">继续审核</el-button><el-button type="success" :loading="actionBusy === 'approve'" @click="confirmApproval">确认通过并交付</el-button></template>
    </el-dialog>
    <el-drawer v-model="historyVisible" title="版本记录" size="min(1100px, 94vw)" append-to-body destroy-on-close>
      <template #header><div><strong>版本记录 · 当前审核 {{ version?.versionNumber }}</strong><p class="review-history-hint">查看历史不会切换审核对象，当前未提交意见会保留。</p></div></template>
      <VersionHistoryPanel v-if="historyVisible && version?.taskId" :key="version.versionId" :task-id="Number(version.taskId)" :current-review-version-id="Number(version.versionId)" :can-list="canListVersions" :can-query="canQueryVersion" :can-download="canDownload" :can-list-notes="hasPermission('shotgrid:note:list')" @version-selected="historySelection = $event" @selection-loading="historySelection = null">
        <template #actions><el-button type="primary" :disabled="!canCompareHistory" @click="compareHistory">与当前审核版对比</el-button></template>
      </VersionHistoryPanel>
      <template #footer><el-button type="primary" plain @click="historyVisible = false">返回审核</el-button></template>
    </el-drawer>
  </section>
</template>

<style scoped>
.review-version-context{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}
.review-version-context p,.review-history-hint{margin:6px 0 0;color:var(--sg-text-muted);font-size:12px}
:global(.app-content:has(.review-detail-page)){overflow:visible}
.review-detail-page.review-detail-page--embedded { padding: 0; }
.review-detail-page--embedded > .sg-page-heading { margin-bottom: 0; }
.review-detail-page{display:grid;gap:18px}.review-detail-heading,.heading-actions{display:flex;gap:13px;align-items:center}.review-detail-heading h2{margin:3px 0}.review-detail-heading p{margin:0;color:var(--sg-text-muted);font-size:11px}.review-detail-loading{display:grid;min-height:320px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg);place-items:center}
.review-context-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.review-context-strip>div{display:grid;gap:6px;padding:13px 15px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:10px}.review-context-strip span{color:var(--sg-text-muted);font-size:10px}.review-context-strip strong{font-size:13px}.danger{color:var(--sg-danger)!important}.success{color:var(--sg-success)!important}
.manual-strip{display:grid;gap:14px;padding:18px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.manual-strip>header{display:flex;gap:14px;align-items:center;justify-content:space-between}.manual-strip h3{margin:3px 0 0;font-size:16px}.manual-strip>header>div:last-child,.manual-version-list{display:flex;gap:8px;flex-wrap:wrap}
.review-detail-grid{display:grid;grid-template-columns:200px minmax(0,1fr) minmax(300px,340px);gap:18px;align-items:start}.review-main{display:grid;gap:18px;min-width:0}.review-work-step{display:grid;gap:12px;padding:4px;border-radius:var(--sg-radius-md);scroll-margin-top:92px;transition:background-color .2s ease,box-shadow .2s ease}.review-work-step.is-candidate-focus{background:var(--sg-accent-soft);box-shadow:0 0 0 3px color-mix(in srgb,var(--sg-accent) 24%,transparent)}.work-step-heading{display:flex;gap:10px;align-items:center;padding:0 3px}.work-step-heading div{display:grid;gap:2px}.work-step-heading strong{font-size:13px}.work-step-heading p{margin:0;color:var(--sg-text-muted);font-size:10px}.step-number{display:grid;flex:0 0 auto;width:24px;height:24px;color:var(--sg-accent);font-size:11px;font-weight:800;background:var(--sg-accent-soft);border:1px solid rgba(255,179,71,.35);border-radius:50%;place-items:center}
.candidate-selector{background:var(--sg-surface);border-color:var(--sg-border)}.candidate-selector:deep(> .el-card__body){display:grid;gap:14px}.candidate-selector>header{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.candidate-selector h3{margin:3px 0;font-size:16px}.candidate-selector header p:not(.sg-eyebrow){margin:0;color:var(--sg-text-muted);font-size:10px}.candidate-selector__list{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;width:100%}.candidate-choice{overflow:hidden;border-color:var(--sg-border);transition:border-color .18s ease,background-color .18s ease,box-shadow .18s ease,transform .18s ease}.candidate-choice:hover{border-color:var(--sg-border-strong);transform:translateY(-1px)}.candidate-choice.is-previewing{background:color-mix(in srgb,var(--sg-accent) 4%,var(--sg-surface));border-color:color-mix(in srgb,var(--sg-accent) 58%,var(--sg-border));box-shadow:0 8px 22px color-mix(in srgb,var(--sg-accent) 8%,transparent)}.candidate-choice.is-selected{box-shadow:inset 3px 0 0 var(--sg-success)}.candidate-choice.is-previewing.is-selected{box-shadow:inset 3px 0 0 var(--sg-success),0 8px 22px color-mix(in srgb,var(--sg-accent) 8%,transparent)}.candidate-choice:deep(.el-card__body){display:grid;gap:11px;padding:12px}.candidate-choice__preview{position:relative;display:grid;width:100%;height:auto;margin:0;white-space:normal}.candidate-choice__preview:deep(.el-radio__input){position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.candidate-choice__preview:deep(.el-radio__label){display:grid;min-width:0;width:100%;gap:10px;padding-left:0}.candidate-choice__preview:has(:focus-visible){outline:2px solid var(--sg-accent);outline-offset:4px;border-radius:8px}.candidate-choice__meta{display:grid;min-width:0;gap:5px;text-align:left}.candidate-choice__meta>span{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.candidate-choice__meta strong{font-size:14px}.candidate-choice__meta small{overflow:hidden;color:var(--sg-text-secondary);font-size:10px;line-height:1.45;text-overflow:ellipsis;white-space:nowrap}.candidate-choice__meta .candidate-choice__file{color:var(--sg-text-muted);font-size:9px}.candidate-choice__actions{display:flex;gap:10px;align-items:center;justify-content:space-between;padding-top:9px;border-top:1px solid var(--sg-border)}.candidate-choice__actions>span{color:var(--sg-text-muted);font-size:9px}.candidate-choice__actions .el-button{flex:0 0 auto;margin:0}
.review-assistant-affix{width:100%;min-width:0}.review-assistant-affix:deep(.el-affix){width:100%}.review-assistant{display:grid;grid-template-columns:minmax(0,1fr);width:100%;height:calc(100dvh - 108px);max-height:880px;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;background:var(--sg-surface);border:1px solid var(--sg-border-strong);border-radius:var(--sg-radius-md);box-shadow:0 16px 36px rgba(0,0,0,.16)}.assistant-heading{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--sg-border)}.assistant-heading h3{margin:3px 0 0;font-size:17px}.assistant-heading:deep(.el-tag){color:var(--sg-text-muted)}.assistant-body{min-height:0}.assistant-body:deep(.el-scrollbar__wrap){scrollbar-width:thin}.assistant-body__inner{display:grid}.assistant-section{display:grid;min-width:0;gap:12px;padding:15px 18px;border-top:1px solid var(--sg-border)}.assistant-body__inner>.assistant-section:first-child{border-top:0}.assistant-section-heading{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:start}.assistant-section-heading h3{margin:1px 0 0;font-size:14px}.assistant-section-heading p{margin:3px 0 0;color:var(--sg-text-muted);font-size:9px;line-height:1.45}.assistant-section-heading>strong{color:var(--sg-text-muted);font-size:10px}.assistant-section-kicker{align-self:center;padding:4px 7px;color:var(--sg-accent);font-size:8px;font-weight:800;letter-spacing:.08em;background:var(--sg-accent-soft);border-radius:999px;white-space:nowrap}
.issue-list{display:grid;gap:10px}.issue-card{display:grid;gap:9px;padding:12px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.issue-card.is-selected{border-color:var(--sg-accent);box-shadow:0 0 0 1px var(--sg-accent-soft)}.issue-card>header{display:flex;gap:8px;align-items:center;justify-content:space-between}.issue-card>header span{color:var(--sg-accent);font-size:9px;font-weight:700}.issue-card>header button{padding:0;color:#68b5ff;font:inherit;font-size:9px;background:transparent;border:0;cursor:pointer}.issue-card>p{margin:0;color:var(--sg-text-secondary);font-size:10px;line-height:1.65;white-space:pre-wrap}.issue-card>small{color:var(--sg-text-muted);font-size:8px}.maker-response{display:grid;gap:5px;padding:9px;color:var(--sg-text-secondary);background:rgba(104,181,255,.07);border-radius:8px}.maker-response span{font-size:8px}.maker-response strong{font-size:10px;line-height:1.55;white-space:pre-wrap}.verification-options{width:100%}.verification-options :deep(.el-radio-button){width:50%}.verification-options :deep(.el-radio-button__inner){width:100%}.verification-comment{display:grid;gap:6px}.verification-comment>span{color:var(--sg-text-secondary);font-size:9px}.verification-comment em{color:var(--sg-danger);font-style:normal}.current-panel{min-width:0;padding:0;gap:8px;transition:background-color .2s ease,box-shadow .2s ease}.current-panel.is-draft-focus{background:var(--sg-accent-soft);box-shadow:inset 3px 0 0 var(--sg-accent)}.issue-compose{display:grid;min-width:0;gap:9px;padding:10px;background:transparent;border-radius:10px}.issue-compose :deep(.el-form-item){margin-bottom:0}.issue-compose__actions :deep(.el-form-item__content){display:flex;gap:8px;justify-content:flex-end}.issue-compose-meta{display:flex;width:100%;gap:8px;align-items:center;justify-content:space-between}.issue-context-tags{display:flex;gap:6px;flex-wrap:wrap}.issue-position-button{margin:0}.empty-block{padding:20px 8px;margin:0;color:var(--sg-text-muted);font-size:10px;text-align:center}.empty-block.compact{padding:12px 8px}
.issue-card-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.issue-card-actions .el-button{margin:0}.issue-draft-card{border-style:dashed}.issue-draft-card>small{color:var(--sg-text-muted)}
.decision-panel{padding:12px 10px;position:relative;z-index:1;background:color-mix(in srgb,var(--sg-surface) 94%,var(--sg-accent) 6%);box-shadow:0 -12px 28px rgba(0,0,0,.09)}.decision-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:center;gap:8px;padding:10px;color:var(--sg-text-secondary);font-size:12px;background:rgba(255,255,255,.025);border-radius:8px}.decision-warning{display:flex;gap:6px;align-items:center;margin:0;color:var(--sg-danger);font-size:9px}.decision-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.decision-actions .el-button{min-width:0;height:auto;min-height:32px;margin:0;padding:8px 6px;white-space:normal}.decision-actions .el-button:last-child{grid-column:1/-1}.action-history{padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.action-history>header{display:flex;justify-content:space-between}.action-history h3{margin:3px 0 0;font-size:16px}.action-history>header>span{color:var(--sg-text-muted);font-size:10px}.action-list{display:grid;gap:12px;margin-top:15px}.action-list article{display:grid;grid-template-columns:auto 1fr;gap:10px}.action-dot{width:9px;height:9px;margin-top:4px;background:var(--sg-text-muted);border-radius:50%}.action-dot[data-tone=success]{background:var(--sg-success)}.action-dot[data-tone=danger]{background:var(--sg-danger)}.action-dot[data-tone=warning]{background:var(--sg-accent)}.action-list strong,.action-list p,.action-list small{display:block;margin:0}.action-list p{margin:4px 0;color:var(--sg-text-secondary);font-size:11px}.action-list small{color:var(--sg-text-muted);font-size:9px}
.final-delivery-alert {
  align-items: flex-start;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--sg-border);
  border-radius: 10px;
}
.final-delivery-alert.el-alert--success {
  color: var(--sg-success);
  background: color-mix(in srgb, var(--sg-success) 6%, var(--sg-surface));
  border-color: color-mix(in srgb, var(--sg-success) 25%, var(--sg-border));
}
.final-delivery-alert :deep(.el-alert__icon) {
  flex: 0 0 18px;
  width: 18px;
  margin-top: 1px;
  font-size: 18px;
}
.final-delivery-alert :deep(.el-alert__content) {
  flex: 1;
  min-width: 0;
  padding: 0 0 0 8px;
}
.final-delivery-alert :deep(.el-alert__title) {
  display: block;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.final-delivery-alert :deep(.el-alert__description) {
  display: grid;
  gap: 8px;
  margin: 8px 0 0;
}
.final-delivery-path {
  display: block;
  min-width: 0;
  padding: 8px 10px;
  color: var(--sg-text);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  user-select: text;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: 6px;
}
.final-delivery-note {
  color: var(--sg-text-secondary);
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.action-transition{display:flex;gap:6px;align-items:center;margin-top:7px;color:var(--sg-text-muted)}
@media(max-width:1100px){.review-detail-grid{grid-template-columns:200px minmax(0,1fr)}.review-assistant-affix{grid-column:2}.review-assistant{height:auto;max-height:none}.assistant-body{height:auto}}@media(max-width:700px){.review-context-strip{grid-template-columns:1fr 1fr}.sg-page-heading,.manual-strip>header{align-items:flex-start}.heading-actions,.manual-strip>header{flex-direction:column}.issue-compose-meta{align-items:flex-start;flex-direction:column}.decision-actions{grid-template-columns:1fr}.decision-actions .el-button:last-child{grid-column:auto}}
.review-detail-loading.el-card{display:block;padding:0}
.review-detail-loading:deep(.el-card__body){width:100%;box-sizing:border-box;padding:30px}
.review-context-strip.el-descriptions{display:block}
.review-context-strip:deep(.el-descriptions__body),.review-context-strip:deep(.el-descriptions__table){background:transparent}
.review-context-strip:deep(.el-descriptions__cell){padding:13px 15px!important;background:var(--sg-surface)!important;border-color:var(--sg-border)!important}
.review-context-strip:deep(.el-descriptions__label){color:var(--sg-text-muted)!important;font-size:10px}
.review-context-strip:deep(.el-descriptions__content){font-size:13px;font-weight:700}
.manual-strip.el-card,.action-history.el-card,.issue-card.el-card{padding:0;background:var(--sg-surface);border-color:var(--sg-border)}
.manual-strip:deep(.el-card__body){display:grid;gap:14px;padding:18px}
.manual-strip:deep(.el-card__body)>header{display:flex;gap:14px;align-items:center;justify-content:space-between}
.action-history:deep(.el-card__body){padding:20px}
.action-history:deep(.el-card__body)>header{display:flex;justify-content:space-between}
.action-history:deep(.el-card__body)>header h3{margin:3px 0 0;font-size:16px}
.action-history:deep(.el-card__body)>header>span{color:var(--sg-text-muted);font-size:10px}
.issue-card:deep(.el-card__body){display:grid;gap:9px;padding:12px}
.issue-card:deep(.el-card__body)>header{display:flex;gap:8px;align-items:center;justify-content:space-between}
.issue-card:deep(.el-card__body)>header span{color:var(--sg-accent);font-size:9px;font-weight:700}
.issue-card:deep(.el-card__body)>p{margin:0;color:var(--sg-text-secondary);font-size:10px;line-height:1.65;white-space:pre-wrap}
.issue-card:deep(.el-card__body)>small{color:var(--sg-text-muted);font-size:8px}
.action-list.el-timeline{margin:15px 0 0;padding-left:8px}
.action-list:deep(.el-timeline-item__timestamp){color:var(--sg-text-muted);font-size:9px}
.action-list:deep(.el-timeline-item__content)>p{margin:4px 0;color:var(--sg-text-secondary);font-size:11px}
.action-list:deep(.el-timeline-item__content)>small{color:var(--sg-text-muted);font-size:9px}
.decision-warning.el-alert{display:flex;color:var(--el-alert-text-color);font-size:inherit}
@media(max-width:700px){.manual-strip:deep(.el-card__body)>header{align-items:flex-start;flex-direction:column}}
.candidate-navigation {
  position: sticky;
  top: 92px;
  width: 200px;
  min-width: 0;
  height: calc(100dvh - 112px);
}
.candidate-navigation .candidate-selector { height: 100%; box-sizing: border-box; }
@media (min-width: 1101px) {
  .review-detail-page--embedded .candidate-navigation,
  .review-detail-page--embedded .review-assistant-affix {
    position: sticky;
    top: 12px;
    align-self: start;
  }
  .review-detail-page--embedded .candidate-navigation,
  .review-detail-page--embedded .review-assistant {
    height: var(--drawer-sidebar-height);
    max-height: none;
  }
}
.candidate-navigation .candidate-selector :deep(> .el-card__body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 0;
  gap: 0;
}
.candidate-navigation header { display: grid; gap: 6px; padding: 10px; border-bottom: 1px solid var(--sg-border); }
.candidate-navigation header .el-tag { justify-self: start; }
.candidate-navigation h3 { font-size: 15px; }
.candidate-navigation__scroll { flex: 1; min-height: 0; }
.candidate-navigation .candidate-selector__list { box-sizing: border-box; padding: 4px; gap: 8px; }
.candidate-navigation .candidate-choice :deep(.el-card__body) { padding: 6px; gap: 6px; }
.candidate-navigation .candidate-choice__actions { flex-direction: row; align-items: center; justify-content: space-between; gap: 6px; }
.candidate-navigation .candidate-choice__actions .el-button { width: 100%; }
.candidate-choice__actions > .candidate-choice__issue-count { align-self: flex-start; font-size: 10px; font-weight: 600; }
.candidate-choice__actions > .candidate-choice__issue-count.has-issues { color: var(--el-color-white); }
.candidate-navigation .candidate-choice__meta > span { flex-wrap: wrap; gap: 4px; }
.candidate-navigation .candidate-choice__file { overflow-wrap: anywhere; }
.current-panel > .assistant-section-heading { padding: 10px 10px 0; }
.current-panel .saved-issues-section .issue-list { padding: 0; gap: 8px; }
.current-panel .issue-card { min-width: 0; padding: 0; }
.current-panel .issue-card :deep(> .el-card__body) { display: grid; min-width: 0; gap: 8px; padding: 10px; }
.assistant-section-heading > div { min-width: 0; }
.assistant-heading { min-width: 0; padding: 12px 10px; gap: 8px; flex-wrap: wrap; }
.decision-actions :deep(.el-button > span) { white-space: normal; overflow-wrap: anywhere; }
.assistant-section-heading > strong { white-space: nowrap; }
.issue-compose :deep(.el-form-item__content) { min-width: 0; }
.issue-card-actions { flex-wrap: wrap; }
/* 当前文件意见区统一字号，通过字重与颜色区分层级。 */
.current-panel {
  font-size: 12px;
  --el-font-size-base: 12px;
  --el-font-size-small: 12px;
  --el-font-size-extra-small: 12px;
}
.current-panel :deep(:is(h3, p, small, strong, span, label, button, input, textarea, .el-form-item__error)) {
  font-size: 12px !important;
}
.current-panel > .assistant-section-heading { grid-template-columns: auto minmax(0, 1fr); gap: 8px; }
.current-panel .assistant-section-heading p { line-height: 1.5; }
.issue-compose-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }

.current-panel .issue-compose { padding-top: 4px; padding-bottom: 4px; gap: 10px; }
.current-panel .saved-issues-section {
  --saved-issues-background: color-mix(in srgb, var(--sg-surface) 85%, var(--sg-text-muted) 15%);
  min-width: 0;
  margin-top: 4px;
  padding: 8px;
  background: var(--saved-issues-background);
  border-top: 1px solid var(--sg-border);
}
.current-panel .saved-issues-tabs :deep(.el-tabs__header) { margin: 0 0 10px; }
.current-panel .saved-issues-tabs :deep(.el-tabs__item) { height: 34px; padding: 0 10px; font-size: 12px; }
.current-panel .saved-issues-tabs :deep(.el-tabs__content) { overflow: visible; }
.current-panel .saved-issues-tabs :deep(.el-tab-pane) { display: grid; gap: 8px; }
.current-panel .saved-issues-tabs :deep(.el-empty) { padding: 12px 0; }
.current-panel .saved-issues-section .issue-card {
  background: var(--sg-surface) !important;
  border-style: solid;
  border-radius: 8px;
}
.current-panel .saved-issues-section .issue-card :deep(.el-card__body > header) {
  padding-bottom: 6px;
  border-bottom: 1px solid var(--sg-border);
}
.current-panel .saved-issues-section .issue-card :deep(.el-card__body > header > span) { color: var(--sg-text-muted); font-weight: 400; }
.current-panel .saved-issues-section .issue-card :deep(.el-card__body > p) { color: var(--sg-text-primary, var(--sg-text-secondary)); }
.current-panel .saved-issues-empty { margin: 0; padding: 0 10px 12px; color: var(--sg-text-muted); }
.current-panel .issue-card :deep(.el-card__body > header) { display: flex; align-items: center; justify-content: space-between; flex-wrap: nowrap; gap: 6px; }
.current-panel .issue-card :deep(.el-card__body > header > span) { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.current-panel .issue-card-actions { flex: 0 0 auto; flex-wrap: nowrap; gap: 6px; margin-left: auto; }
.current-panel .issue-card :deep(.el-card__body > p) { line-height: 1.6; overflow-wrap: anywhere; }
.current-panel .issue-card :deep(.el-card__body > small) { line-height: 1.5; }
@media (max-width: 760px) {
  .review-detail-grid { grid-template-columns: minmax(0,1fr); }
  .candidate-navigation { position: static; width: 100%; height: 300px; }
  .candidate-navigation .candidate-selector__list { grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); }
  .review-assistant-affix { grid-column: 1; }
}
.decision-summary > :nth-child(2) { text-align: right; }
.decision-summary > :only-child { grid-column: 1 / -1; }
</style>

<style scoped>
.assistant-work-tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.assistant-work-tabs :deep(> .el-tabs__header) { flex: none; margin: 0; padding: 0 12px; }
.assistant-work-tabs :deep(> .el-tabs__header .el-tabs__item) { height: 44px; font-size: 13px; font-weight: 600; }
.assistant-work-tabs :deep(> .el-tabs__content) { flex: 1; min-height: 0; }
.assistant-work-tabs :deep(> .el-tabs__content > .el-tab-pane) { height: 100%; }
.assistant-work-tabs .assistant-body { height: 100%; }
.assistant-work-tabs :deep(#pane-current .el-scrollbar__view) { min-height: 100%; display: flex; flex-direction: column; }
.assistant-work-tabs .current-panel { flex: 1; display: flex; flex-direction: column; }
.assistant-work-tabs .current-panel .saved-issues-section { flex: 1; margin-bottom: 0; }
.review-assistant .decision-panel { background: var(--sg-surface); box-shadow: none; }
.assistant-work-tabs :deep(#pane-carried) { display: flex; flex-direction: column; }
.verification-guidance { flex: none; width: auto; margin: 8px 12px; padding: 7px 8px; }
.verification-guidance.el-alert--warning { background: var(--el-color-warning-light-8); border: 1px solid var(--el-color-warning-light-5); color: var(--el-color-warning-dark-2); }
.verification-guidance :deep(.el-alert__icon) { font-size: 14px; width: 14px; margin-right: 6px; }
.verification-guidance :deep(.el-alert__content) { min-width: 0; padding: 0; }
.verification-guidance :deep(.el-alert__title) { font-size: 11px; font-weight: 600; line-height: 1.5; }
.carried-panel { padding: 8px 12px 10px; gap: 8px; border-top: 0; }
.carried-list { gap: 8px; }
.carried-file-tabs { min-width: 0; box-shadow: none; }
.carried-file-tabs :deep(> .el-tabs__header) { position: sticky; top: 0; z-index: 1; margin: 0; }
.carried-file-tabs :deep(> .el-tabs__header .el-tabs__item) { height: 32px; padding: 0 10px; font-size: 11px; }
.carried-file-tabs :deep(> .el-tabs__content) { padding: 8px; overflow: visible; }
.carried-panel .carried-annotation-button { flex-shrink: 0; height: 20px; min-height: 20px; padding: 0 6px; font-size: 10px; font-weight: 600; }
.carried-panel .issue-card :deep(.el-card__body > header .carried-annotation-button span) { color: var(--el-color-white); font-size: inherit; }
.carried-panel .issue-card { border-radius: 8px; }
.carried-panel .issue-card :deep(> .el-card__body) { padding: 8px 10px; gap: 6px; }
.carried-panel .issue-card :deep(.el-card__body > header) { gap: 6px; }
.carried-panel .issue-card :deep(.el-card__body > p) { line-height: 1.5; overflow-wrap: anywhere; }
.carried-panel .maker-response { gap: 3px; padding: 6px 8px; border-radius: 6px; }
.carried-panel .maker-response strong { line-height: 1.4; overflow-wrap: anywhere; }
.carried-panel .verification-comment { gap: 4px; }
.carried-panel .verification-comment :deep(.el-textarea__inner) { font-size: 12px; }
.decision-panel > .decision-review-cta { width: 100%; margin: 0; padding: 12px; white-space: normal; height: auto; min-height: 46px; line-height: 1.5; font-size: 14px; font-weight: 700; }
.decision-review-cta :deep(> span) { display: flex; justify-content: center; gap: 8px; white-space: normal; }
.decision-review-cta .el-icon { flex-shrink: 0; font-size: 16px; }
.verification-choice { padding: 6px; border: 1px solid var(--sg-border); border-radius: 6px; }
.verification-choice.is-pending { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.verification-choice__prompt { margin: 0 0 5px; color: var(--sg-text-secondary); font-size: 10px; line-height: 1.4; }
.is-pending > .verification-choice__prompt { color: var(--el-color-primary); font-weight: 700; }
.verification-choice .verification-options { display: flex; gap: 6px; }
.verification-choice .verification-options :deep(.el-radio-button) { flex: 1; width: auto; min-width: 0; }
.verification-choice .verification-options :deep(.el-radio-button__inner) { display: flex; align-items: center; justify-content: center; min-height: 28px; padding: 4px; border: 1px solid var(--el-color-primary); border-radius: 4px; font-size: 11px; font-weight: 600; white-space: normal; line-height: 1.4; box-shadow: none; }
.verification-choice .verification-options :deep(.el-radio-button:not(.is-active) .el-radio-button__inner) { color: var(--el-color-primary); background: var(--el-bg-color); }
@media (max-width: 1100px) { .assistant-work-tabs { flex: none; } .assistant-work-tabs .assistant-body { max-height: 560px; } }
</style>

<style scoped>
.issue-scope-tabs { margin: 0 10px; box-shadow: none; }
.issue-scope-tabs :deep(.el-tabs__content) { padding: 8px; }
.issue-scope-tabs :deep(.el-tabs__item) { padding: 0 12px; font-size: 12px; }
.issue-scope-tabs .issue-compose { padding: 0; }
.issue-scope-label { display: inline-flex; align-items: center; gap: 4px; }
.issue-candidate-tag.el-tag { height: 16px; padding: 0 5px; font-size: 10px; line-height: 14px; transform: scale(.8); transform-origin: left center; margin-right: -10px; }
</style>
