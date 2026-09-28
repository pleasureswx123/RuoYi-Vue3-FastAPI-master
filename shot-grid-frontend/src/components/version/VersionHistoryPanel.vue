<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElTabs, ElTabPane, ElDrawer } from 'element-plus'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import { Refresh } from '@element-plus/icons-vue'

import { getReviewActions, getTaskIssues } from '@/api/shot-grid/reviews'
import { useVersionRealtime } from '@/composables/useVersionRealtime'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import { tagTypeFromTone } from '@/utils/tag'
import ReviewCandidateThumbnail from '@/views/review/components/ReviewCandidateThumbnail.vue'
import ReviewMediaWorkspace from '@/views/review/components/ReviewMediaWorkspace.vue'
import { formatMediaTime, formatReviewDateTime, reviewErrorState } from '@/views/review/reviewPresentation'
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
const emit = defineEmits(['version-selected', 'selection-loading'])

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
const feedbackRealtimeId = computed(() => props.canListNotes && props.canQuery ? selectedVersionId.value : null)
useVersionRealtime(feedbackRealtimeId, async versionId => {
  const targetTaskId = Number(props.taskId)
  const generation = contextGeneration
  const operation = Number(props.operationGeneration)
  const response = await getTaskIssues(targetTaskId, {})
  if (!stillCurrent(generation, targetTaskId, operation) || versionId !== selectedVersionId.value || detailLoading.value || !versionDetail.value) return
  // 仅替换问题数据，保留当前文件、预览位置和页签。
  feedbackNotes.value = buildVersionFeedback(response.data || [], Number(versionId))
})
const feedbackActions = ref([])
const selectedFeedback = ref(null)
const feedbackCategory = ref('files')
const selectedFeedbackGroupKey = ref('')
const feedbackScope = ref('pending')
const opinionTab = ref('current')
const previousFileTabs = ref({})
const previousSourceDetails = ref({})
let previousSourcesController = null
const sourceDrawerOpen = ref(false)
const sourceNote = ref(null)
const sourceMedia = ref(null)
const feedbackSourceDetail = ref(null)
const feedbackSourceLoading = ref(false)
const feedbackSourceError = ref(null)
const feedbackMedia = ref(null)
let sourceController = null

function issueFileKey(note) {
  return `${Number(note.originVersionId)}:${note.originCandidateId ?? 'legacy'}`
}
const feedbackGroups = computed(() => {
  const groups = new Map()
  const detail = versionDetail.value
  const addGroup = (versionId, candidate, key, label) => groups.set(key, {
    key, versionId: Number(versionId), candidateId: candidate?.candidateId ?? null,
    candidate: candidate || { files: [] }, label, notes: [], pendingCount: 0, historyCount: 0
  })
  for (const candidate of detail?.candidates || []) {
    addGroup(detail.versionId, candidate, `${detail.versionId}:${candidate.candidateId}`, candidate.candidateNumber)
  }
  for (const note of feedbackNotes.value) {
    const key = issueFileKey(note)
    if (!groups.has(key)) {
      const source = Number(note.originVersionId) === Number(detail?.versionId) ? detail : feedbackSourceDetail.value
      const candidate = Number(source?.versionId) === Number(note.originVersionId)
        ? source?.candidates?.find(item => Number(item.candidateId) === Number(note.originCandidateId)) : null
      addGroup(note.originVersionId, candidate || { candidateId: note.originCandidateId, files: [] }, key,
        candidate?.candidateNumber || `${note.originVersionNumber || `来源版本 #${note.originVersionId}`} · ${note.originCandidateId ? `文件 #${note.originCandidateId}` : '整体反馈'}`)
    }
    const group = groups.get(key)
    group.notes.push(note)
    if (note.displayScope === 'pending') group.pendingCount += 1
    else group.historyCount += 1
  }
  return [...groups.values()]
})
const currentFeedbackGroups = computed(() => feedbackGroups.value.filter(group => group.versionId === Number(versionDetail.value?.versionId) && group.candidateId != null))
const overallFeedbackNotes = computed(() => feedbackNotes.value.filter(note => Number(note.originVersionId) === Number(versionDetail.value?.versionId) && note.originCandidateId == null))
watch(overallFeedbackNotes, notes => {
  if (!notes.length) feedbackCategory.value = 'files'
})
const overallPendingCount = computed(() => overallFeedbackNotes.value.filter(note => note.displayScope === 'pending').length)
const fileFeedbackPendingCount = computed(() => pendingFeedbackCount.value - overallPendingCount.value)
const currentFilePendingCount = computed(() => currentFeedbackGroups.value.reduce((total, group) => total + group.pendingCount, 0))
const previousNotes = computed(() => feedbackNotes.value.filter(note => Number(note.originVersionId) !== Number(versionDetail.value?.versionId)))
const previousPending = computed(() => previousNotes.value.filter(note => note.displayScope === 'pending'))
const newPendingCount = computed(() => feedbackNotes.value.filter(note => note.displayScope === 'pending' && Number(note.originVersionId) === Number(selectedVersionId.value)).length)
const transferredNotes = computed(() => feedbackNotes.value.filter(note => note.displayScope === 'origin_history' && note.noteStatus === 'open' && note.pendingVersionId && Number(note.pendingVersionId) !== Number(selectedVersionId.value)))
const transferredTargets = computed(() => [...new Map(transferredNotes.value.map(note => [note.pendingVersionId, { id: note.pendingVersionId, label: note.pendingVersionNumber || '后续版本' }])).values()])
const previousPanes = computed(() => [
  { name: 'previous', label: '上轮未修复', notes: previousPending.value },
  { name: 'resolved', label: '已修复', notes: previousNotes.value.filter(note => note.noteStatus === 'resolved') },
  { name: 'other', label: '其他记录', notes: previousNotes.value.filter(note => note.displayScope !== 'pending' && note.noteStatus !== 'resolved') }
].filter(pane => pane.notes.length))
function showPreviousPending() {
  feedbackCategory.value = 'files'
  opinionTab.value = 'previous'
  feedbackPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}
function groupsForPreviousPane(pane) {
  const ids = new Set(pane.notes.map(note => note.noteId))
  return previousGroups.value.map(group => ({ ...group, notes: group.notes.filter(note => ids.has(note.noteId)) })).filter(group => group.notes.length)
}
watch(previousPanes, panes => {
  if (opinionTab.value !== 'current' && !panes.some(pane => pane.name === opinionTab.value)) opinionTab.value = panes[0]?.name || 'current'
})
const previousGroups = computed(() => feedbackGroups.value.filter(group => group.versionId !== Number(versionDetail.value?.versionId)).map(group => {
  const source = previousSourceDetails.value[group.versionId]
  const candidate = source?.candidates?.find(item => Number(item.candidateId) === Number(group.candidateId))
  return { ...group, label: candidate?.candidateNumber || `${source?.versionNumber || group.notes[0]?.originVersionNumber || '历史版本'} · ${group.candidateId == null ? '整体反馈' : '原文件'}`, unavailable: !source }
}))
watch([previousPanes, previousGroups], ([panes]) => {
  const next = {}
  for (const pane of panes) {
    const groups = groupsForPreviousPane(pane)
    const selected = previousFileTabs.value[pane.name]
    next[pane.name] = groups.some(group => group.key === selected) ? selected : groups[0]?.key || ''
  }
  previousFileTabs.value = next
}, { immediate: true })
async function loadPreviousSources() {
  previousSourcesController?.abort()
  const controller = new AbortController()
  previousSourcesController = controller
  previousSourceDetails.value = {}
  const taskId = Number(props.taskId)
  const generation = contextGeneration
  await Promise.all([...new Set(previousNotes.value.map(note => Number(note.originVersionId)))].map(async id => {
    try {
      const response = await getVersionDetail(id, { signal: controller.signal })
      if (!controller.signal.aborted && generation === contextGeneration && Number(response.data?.taskId) === taskId && Number(response.data?.versionId) === id) previousSourceDetails.value = { ...previousSourceDetails.value, [id]: response.data }
    } catch { /* 来源名称失败时保留原始版本提示，原画抽屉仍提供重试。 */ }
  }))
}
watch(previousNotes, () => {
  if (!previousNotes.value.length) opinionTab.value = 'current'
  loadPreviousSources()
})
const previousAwaitingCount = computed(() => previousNotes.value.filter(note => responseForVersion(note) && !verificationForVersion(note) && note.noteStatus !== 'resolved').length)
const sourceMediaVersion = computed(() => {
  const detail = feedbackSourceDetail.value
  if (!detail || !sourceNote.value) return null
  const candidate = detail.candidates?.find(item => Number(item.candidateId) === Number(sourceNote.value.originCandidateId))
  return { ...detail, candidateId: sourceNote.value.originCandidateId, versionNumber: candidate?.candidateNumber || detail.versionNumber,
    files: candidate?.files || [],
    mediaDerivationStatus: candidate?.mediaDerivationStatus || detail.mediaDerivationStatus }
})
const activeFeedbackGroup = computed(() => feedbackGroups.value.find(item => item.key === selectedFeedbackGroupKey.value) || null)
const pendingFileCount = computed(() => feedbackGroups.value.filter(item => item.candidateId != null && item.pendingCount).length)
const visibleFeedbackNotes = computed(() => (activeFeedbackGroup.value?.notes || []).filter(note =>
  feedbackScope.value === 'pending' ? note.displayScope === 'pending' : note.displayScope !== 'pending'
))
const feedbackMediaVersion = computed(() => {
  const group = activeFeedbackGroup.value
  const detail = versionDetail.value
  if (!detail || !group) return null
  const candidate = detail.candidates?.find(item => Number(item.candidateId) === Number(group.candidateId))
  return { ...detail, candidateId: group.candidateId, versionNumber: candidate?.candidateNumber || detail.versionNumber,
    files: candidate?.files || (group.candidateId ? [] : detail.files || []),
    mediaDerivationStatus: candidate?.mediaDerivationStatus || detail.mediaDerivationStatus }
})

function selectFeedbackGroup(key) {
  selectedFeedbackGroupKey.value = key
  selectedFeedback.value = visibleFeedbackNotes.value[0] || null
  opinionTab.value = !activeFeedbackGroup.value?.notes.length && previousNotes.value.length ? (previousPanes.value[0]?.name || 'current') : 'current'
}
function selectFeedbackScope() {
  selectedFeedback.value = visibleFeedbackNotes.value[0] || null
}
async function loadFeedbackSource() {
  sourceController?.abort()
  feedbackSourceDetail.value = null
  feedbackSourceError.value = null
  feedbackSourceLoading.value = false
  const note = sourceNote.value
  if (!note || !sourceDrawerOpen.value) return
  const group = { versionId: Number(note.originVersionId), candidateId: note.originCandidateId }
  const controller = new AbortController()
  sourceController = controller
  const generation = contextGeneration
  const taskId = Number(props.taskId)
  feedbackSourceLoading.value = true
  try {
    const response = await getVersionDetail(group.versionId, { signal: controller.signal })
    if (controller.signal.aborted || generation !== contextGeneration || sourceNote.value !== note || !sourceDrawerOpen.value || disposed) return
    if (Number(response.data?.taskId) !== taskId || Number(response.data?.versionId) !== group.versionId) throw new Error('来源文件与当前任务不匹配')
    if (group.candidateId && !response.data.candidates?.some(item => Number(item.candidateId) === Number(group.candidateId))) throw new Error('问题来源文件不可用')
    feedbackSourceDetail.value = response.data
  } catch (error) {
    if (!controller.signal.aborted && generation === contextGeneration && sourceNote.value === note && sourceDrawerOpen.value) feedbackSourceError.value = reviewErrorState(error, '来源文件加载失败')
  } finally {
    if (sourceController === controller) feedbackSourceLoading.value = false
  }
}
async function openSourceNote(note) {
  sourceNote.value = note
  sourceDrawerOpen.value = true
  await loadFeedbackSource()
  await nextTick()
  sourceMedia.value?.seekToNote()
}
function closeSourceNote() {
  sourceController?.abort()
  sourceDrawerOpen.value = false
  sourceNote.value = null
  feedbackSourceDetail.value = null
  feedbackSourceError.value = null
  feedbackSourceLoading.value = false
}
const feedbackLoading = ref(false)
const feedbackError = ref(null)
const feedbackPanel = ref(null)
const historyPanel = ref(null)

let disposed = false
let contextGeneration = 0
let listController = null
let detailController = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / props.pageSize)))
const historyFilters = computed(() => ({ versionStatus: statusFilter.value }))
const historyFormRef = ref(null)
const latestDecision = computed(() => feedbackActions.value.find(item => ['approve', 'reject', 'defer'].includes(item.actionType)) || null)
const hasFeedback = computed(() => Boolean(feedbackNotes.value.length || latestDecision.value))
const pendingFeedbackCount = computed(() => feedbackNotes.value.filter(item => item.displayScope === 'pending').length)
const decisionPresentation = computed(() => {
  const decision = latestDecision.value
  if (!decision) return null
  const reason = String(decision.reason || '').trim()
  if (decision.actionType === 'approve') {
    return {
      title: '本版审核已通过',
      badge: '审核完成',
      tone: 'success',
      message: reason || '本版已确认符合要求，无需继续修改。'
    }
  }
  if (decision.actionType === 'defer') {
    return {
      title: '本版暂缓决定',
      badge: '等待审核',
      tone: 'info',
      message: reason || '审核人将在稍后继续处理，本版暂不需要制作人操作。'
    }
  }
  return {
    title: '已退回修改',
    badge: '需要继续修改',
    tone: 'warning',
    usePendingHint: !reason,
    message: reason
  }
})
const historyPanelId = computed(() => `version-history-panel-${Number(props.taskId)}`)
const feedbackPanelId = computed(() => `version-feedback-panel-${Number(props.taskId)}`)
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

function feedbackAuthor(note) {
  return note.reviewerName || (note.reviewerUserId ? `用户 #${note.reviewerUserId}` : '未知审核人')
}

function feedbackBadgeMeta(note) {
  if (note.displayScope === 'pending') {
    return {
      label: '待处理',
      tone: 'warning'
    }
  }
  const verification = verificationForVersion(note)
  if (verification?.result === 'resolved') return { label: '已修复', tone: 'success' }
  if (verification?.result === 'still_present') {
    return {
      label: '仍需修改',
      tone: 'danger'
    }
  }
  if (note.noteStatus === 'resolved') {
    return { label: '已修复', tone: 'success' }
  }
  if (responseForVersion(note)) return { label: '待审核', tone: 'warning' }
  const latest = latestVerification(note)
  if (latest?.result === 'still_present') {
    return { label: '仍需修改', tone: 'warning' }
  }
  return { label: '待审核', tone: 'warning' }
}

function feedbackCandidateLabel(note) {
  if (note.originCandidateId == null) return `${note.originVersionNumber || '来源版本'} · 整体反馈`
  return note.originCandidateNumber || versionDetail.value?.candidates?.find(item => Number(item.candidateId) === Number(note.originCandidateId))?.candidateNumber
    || `${note.originVersionNumber || '来源版本'} · 文件 #${note.originCandidateId}`
}

function feedbackContext(note) {
  if (responseForVersion(note) && !verificationForVersion(note) && note.noteStatus !== 'resolved') {
    return `已随 ${versionDetail.value?.versionNumber || '本版'} 提交处理说明，等待审核人确认`
  }
  const verification = latestVerification(note)
  if (note.displayScope === 'pending' && Number(note.originVersionId) !== selectedVersionId.value) {
    return `来源 ${note.originVersionNumber}；审核人在 ${note.pendingVersionNumber || '当前版'} 确认仍然存在`
  }
  if (note.displayScope === 'origin_history' && note.noteStatus === 'open') {
    return `已转入 ${note.pendingVersionNumber || '最新版本'} 待处理`
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
  emit('selection-loading')
  detailController?.abort()
  closeSourceNote()
  previousSourcesController?.abort()
  selectedFeedbackGroupKey.value = ''
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
      const firstGroup = currentFeedbackGroups.value.find(item => item.pendingCount) || currentFeedbackGroups.value[0]
      feedbackScope.value = firstGroup?.pendingCount || !firstGroup?.notes.length ? 'pending' : 'history'
      selectFeedbackGroup(firstGroup?.key || '')
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
  emit('selection-loading')
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

async function openTransferredVersion(versionId) {
  selectedVersionId.value = Number(versionId)
  await loadDetail(Number(versionId))
  if (Number(versionDetail.value?.versionId) === Number(versionId) && !versions.value.some(item => Number(item.versionId) === Number(versionId))) {
    versions.value = [versionDetail.value, ...versions.value]
  }
  if (previousPending.value.length) showPreviousPending()
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
  const generation = contextGeneration
  if (!feedbackNotes.value.some(note => Number(note.issueId) === issueId)) {
    selectedVersionId.value = originVersionId
    await loadDetail(originVersionId)
  }
  if (generation !== contextGeneration || disposed) return
  const note = feedbackNotes.value.find(item => Number(item.issueId) === issueId)
  if (!note) return
  if (Number(note.originVersionId) !== Number(versionDetail.value?.versionId)) {
    await openSourceNote(note)
    return
  }
  feedbackScope.value = note.displayScope === 'pending' ? 'pending' : 'history'
  selectFeedbackGroup(issueFileKey(note))
  selectedFeedback.value = note
  opinionTab.value = 'current'
  await nextTick()
  feedbackPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  feedbackMedia.value?.seekToNote()
}

async function selectFeedback(issue) {
  selectedFeedback.value = issue
  await nextTick()
  feedbackMedia.value?.seekToNote()
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
  closeSourceNote()
  previousSourcesController?.abort()
  selectedFeedbackGroupKey.value = ''
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
  closeSourceNote()
  previousSourcesController?.abort()
  selectedFeedbackGroupKey.value = ''
  listController?.abort()
  detailController?.abort()
})

defineExpose({ focusIssue })
</script>

<template>
  <div :id="historyPanelId" ref="historyPanel" class="version-history-affix-target">
    <el-card class="version-history-panel" shadow="never">
    <header class="history-heading">
      <div><p class="sg-eyebrow">IMMUTABLE HISTORY</p><h3>版本历史</h3><p>版本按提交顺序自动编号；每次修订都会新增版本，历史文件始终保留。</p></div>
      <el-form ref="historyFormRef" :model="historyFilters" class="history-tools" size="large" inline aria-label="版本历史筛选">
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
      <el-skeleton v-if="loading && !versions.length" class="history-empty" :rows="4" animated />
      <el-empty v-else-if="!versions.length && !listError" class="history-empty" :image-size="56" description="该任务还没有正式版本" />
      <ElTabs v-if="versions.length" :model-value="selectedVersionId" type="border-card" class="version-tabs" :aria-busy="loading" @tab-change="selectVersion">
        <ElTabPane v-for="version in versions" :key="version.versionId" :name="Number(version.versionId)">
          <template #label>
            <span class="version-tab-label"><strong>{{ version.versionNumber }}</strong><el-tag size="small" effect="plain" round :type="tagTypeFromTone(versionStatusMeta(version.versionStatus).tone)">{{ versionStatusMeta(version.versionStatus).label }}</el-tag></span>
          </template>
      <main v-if="selectedVersionId === Number(version.versionId)" class="history-detail">
        <div class="version-tab-meta"><span>{{ version.submitterName || `用户 #${version.submittedBy}` }} · {{ formatVersionDateTime(version.submittedTime) }}</span><span>{{ version.changelog }}</span></div>
        <el-skeleton v-if="detailLoading" class="detail-placeholder" :rows="8" animated />
        <el-alert v-else-if="detailError" class="detail-placeholder is-error" :title="detailError.title" :description="detailError.message" type="error" :closable="false" show-icon />
        <template v-else-if="versionDetail">
          <section class="version-info-content" aria-label="版本信息与文件列表">
          <VersionDetailCard
            :show-header="false"
            :version="versionDetail"
            @prompt-saved="versionDetail = $event"
            :can-download="canDownload"
            :show-preview="!feedbackNotes.length"
            show-file-preview-action
          />
          </section>
          <div v-if="feedbackLoading || feedbackError || hasFeedback || currentFeedbackGroups.length" :id="feedbackPanelId" :ref="element => feedbackPanel = element" class="version-feedback-affix-target">
            <el-card class="version-feedback-panel" shadow="never">
              <header class="version-feedback-panel__heading feedback-summary" :class="latestDecision && decisionPresentation ? ['feedback-decision', `is-${latestDecision.actionType}`] : []" aria-label="本版审核结果">
                <div class="feedback-summary__top">
                  <h3>{{ versionDetail.versionNumber }} · 本轮提交 {{ versionDetail.candidates?.length || 0 }} 个文件</h3>
                  <el-tag size="small" effect="plain" :type="tagTypeFromTone(versionStatusMeta(versionDetail.versionStatus).tone)">{{ versionStatusMeta(versionDetail.versionStatus).label }}</el-tag>
                  <el-tag v-if="decisionPresentation" size="small" effect="plain" round :type="tagTypeFromTone(decisionPresentation.tone)">{{ decisionPresentation.title }}</el-tag>
                  <small v-if="latestDecision">审核人 {{ latestDecision.reviewerName || `用户 #${latestDecision.reviewerUserId}` }} · {{ formatReviewDateTime(latestDecision.createTime) }}</small>
                </div>
                <div class="feedback-summary__bottom">
                  <p v-if="decisionPresentation?.message">{{ decisionPresentation.message }}</p>
                  <span v-if="pendingFeedbackCount"><strong class="feedback-decision__count">{{ pendingFeedbackCount }} 条待处理问题</strong> = 本轮新增 {{ newPendingCount }} 条 + <el-button v-if="previousPending.length" type="warning" size="small" class="previous-pending-entry" @click="showPreviousPending">上轮未修复 {{ previousPending.length }} 条</el-button><span v-else>上轮未修复 0 条</span> · 涉及 {{ pendingFileCount }} 个来源文件</span>
                  <span v-else-if="!transferredNotes.length">{{ versionDetail.versionStatus === 'pending_review' ? '本轮已提交，等待审核人确认' : '本轮暂无待处理意见' }}</span>
                  <span v-if="transferredNotes.length" class="transferred-hint">本版问题仍有 <strong>{{ transferredNotes.length }} 条未解决</strong>，已转入后续版本 <el-button v-for="target in transferredTargets" :key="target.id" type="warning" plain size="small" @click="openTransferredVersion(target.id)">查看 {{ target.label }} 待修改问题</el-button></span>
                  <span class="feedback-summary__hint">点击意见定位画面和标注</span>
                </div>
              </header>
              <el-skeleton v-if="feedbackLoading" class="feedback-state" :rows="4" animated />
              <el-alert v-else-if="feedbackError" class="feedback-state is-error" :title="feedbackError.title" :description="feedbackError.message" type="error" :closable="false" show-icon />
              <ElTabs v-else-if="currentFeedbackGroups.length || previousNotes.length || overallFeedbackNotes.length" v-model="feedbackCategory" tab-position="left" type="border-card" class="feedback-category-tabs" :class="{ 'is-file-only': !overallFeedbackNotes.length }" aria-label="反馈类型">
                <ElTabPane v-if="overallFeedbackNotes.length" name="overall-feedback" label="本版整体反馈">
                  <template #label><span class="feedback-category-title"><span class="feedback-category-label">本版整体反馈</span><el-tag v-if="overallPendingCount" class="feedback-category-count" type="danger" effect="dark" round size="small" :aria-label="`整体反馈待处理 ${overallPendingCount} 条`">{{ overallPendingCount }}</el-tag></span></template>
                <section v-if="overallFeedbackNotes.length" class="overall-feedback" aria-label="本版整体反馈">
                  <header><strong>本版整体反馈</strong><el-tag size="small" type="warning" effect="plain" round>待处理 {{ overallPendingCount }} 条</el-tag></header>
                  <div class="overall-feedback__items">
                    <el-card v-for="note in overallFeedbackNotes" :key="note.noteId" class="feedback-item" shadow="never">
                      <p class="overall-feedback__content">{{ note.content }}</p>
                      <p v-if="displayedResponse(note)" class="feedback-response">制作人处理说明：{{ displayedResponse(note).responseText }}</p>
                      <p v-if="feedbackVerificationComment(note)" class="feedback-verification">审核人未通过原因：{{ feedbackVerificationComment(note) }}</p>
                      <small class="feedback-author">{{ feedbackAuthor(note) }} · {{ formatReviewDateTime(note.createTime) }} 提出</small>
                      <ReviewReferenceFiles :files="note.referenceFiles || []" compact />
                    </el-card>
                  </div>
                </section>
                </ElTabPane>
                <ElTabPane name="files" label="文件反馈">
                  <template #label><span class="feedback-category-title"><span class="feedback-category-label">文件反馈</span><el-tag v-if="fileFeedbackPendingCount" class="feedback-category-count" type="danger" effect="dark" round size="small" :aria-label="`文件反馈待处理 ${fileFeedbackPendingCount} 条`">{{ fileFeedbackPendingCount }}</el-tag></span></template>
                <div class="feedback-layout">
                <nav v-if="currentFeedbackGroups.length" class="feedback-file-nav" aria-label="按文件查看修改意见">
                  <el-button v-for="group in currentFeedbackGroups" :key="group.key" class="feedback-file" :title="group.candidate.files?.find(file => file.role === 'review_media')?.businessFileName" :class="{ active: group.key === selectedFeedbackGroupKey }" :aria-pressed="group.key === selectedFeedbackGroupKey" @click="selectFeedbackGroup(group.key)">
                    <span class="feedback-file__content">
                      <ReviewCandidateThumbnail :version-id="group.versionId" :candidate="group.candidate" :can-preview="canDownload" :active="group.key === selectedFeedbackGroupKey" />
                      <strong>{{ group.label }}</strong>

                      <el-tag :class="{ 'feedback-pending-tag': group.pendingCount > 0 }" :type="group.pendingCount ? 'warning' : 'info'" :effect="group.pendingCount ? 'dark' : 'plain'" round size="small">{{ group.pendingCount ? `待处理 ${group.pendingCount} 条` : group.notes.some(note => note.noteStatus === 'open') ? '仍有问题转入后续版' : '无待修改问题' }}</el-tag>
                      <small v-if="group.historyCount">历史记录 {{ group.historyCount }} 条</small>
                    </span>
                  </el-button>
                </nav>
                <div v-if="currentFeedbackGroups.length" class="feedback-media">
                  <ReviewMediaWorkspace v-if="feedbackMediaVersion" :ref="element => feedbackMedia = element" :version="feedbackMediaVersion" :selected-note="selectedFeedback" :can-download="canDownload" feedback-mode @clear-note-focus="selectedFeedback = null" />
                </div>
                <aside v-if="currentFeedbackGroups.length || previousNotes.length" class="feedback-list-panel">
                  <ElTabs v-model="opinionTab" type="border-card" class="opinion-tabs" stretch>
                    <ElTabPane name="current" :label="`本轮问题 ${currentFilePendingCount}`">
                  <h4>{{ activeFeedbackGroup?.label }} · 修改意见</h4>
                  <ElTabs v-model="feedbackScope" stretch @tab-change="selectFeedbackScope">
                    <ElTabPane v-for="scope in ['pending', 'history']" :key="scope" :name="scope" :label="scope === 'pending' ? `待处理（${activeFeedbackGroup?.pendingCount || 0}）` : `历史（${activeFeedbackGroup?.historyCount || 0}）`">
                  <div v-if="feedbackScope === scope" class="feedback-list">
                  <el-empty v-if="!visibleFeedbackNotes.length" :image-size="40" :description="feedbackScope === 'pending' ? '该文件暂无待处理意见' : '该文件暂无历史记录'" />
                  <el-card v-for="note in visibleFeedbackNotes" :key="note.noteId" class="feedback-item" :class="{ active: selectedFeedback?.noteId === note.noteId }" shadow="never">
                    <el-button text class="feedback-item__select" :aria-pressed="selectedFeedback?.noteId === note.noteId" @click="selectFeedback(note)">
                      <span class="feedback-item__content">
                        <span class="feedback-item__heading"><strong>来源文件 {{ feedbackCandidateLabel(note) }}</strong><el-tag size="small" effect="plain" round :type="tagTypeFromTone(feedbackBadgeMeta(note).tone)">{{ feedbackBadgeMeta(note).label }}</el-tag></span>
                        <p>{{ note.content || '该问题仅包含画面标注' }}</p>
                        <small class="feedback-context">{{ feedbackContext(note) }}</small>
                        <p v-if="displayedResponse(note)" class="feedback-response">制作人对 {{ displayedResponse(note).versionNumber || '后续版本' }} 的处理说明：{{ displayedResponse(note).responseText }}</p>
                        <p v-if="feedbackVerificationComment(note)" class="feedback-verification">审核人未通过原因：{{ feedbackVerificationComment(note) }}</p>
                        <small class="feedback-author">{{ feedbackAuthor(note) }} · {{ formatReviewDateTime(note.createTime) }} 提出</small>
                        <small v-if="note.annotations?.items?.length || (note.mediaTimeMs !== null && note.mediaTimeMs !== undefined)"><template v-if="note.annotations?.items?.length">{{ note.annotations.items.length }} 个画面标注</template><template v-if="note.mediaTimeMs !== null && note.mediaTimeMs !== undefined"> · {{ formatMediaTime(note.mediaTimeMs) }}</template></small>
                      </span>
                    </el-button>
                    <ReviewReferenceFiles :files="note.referenceFiles || []" compact />
                  </el-card>
                  </div>
                    </ElTabPane>
                  </ElTabs>
                    </ElTabPane>
                    <ElTabPane v-for="pane in previousPanes" :key="pane.name" :name="pane.name" :label="`${pane.label} ${pane.notes.length}`">
                  <section v-if="previousNotes.length" class="previous-issues" aria-label="上一轮修改意见">
                    <h4>{{ pane.label }} · {{ pane.notes.length }} 条<span v-if="previousAwaitingCount"> · {{ previousAwaitingCount }} 条待审核</span></h4>
                    <p>{{ pane.name === 'previous' ? '这些旧问题本轮复核仍未通过，请与新问题一起修改。' : '以下为上轮问题的处理记录。' }}点击意见查看原始标注。</p>
                    <ElTabs v-model="previousFileTabs[pane.name]" class="previous-issues__list" :aria-label="`${pane.label}来源文件`">
                      <ElTabPane v-for="group in groupsForPreviousPane(pane)" :key="group.key" :name="group.key" :label="`${group.label}（${group.notes.length}）`">
                        <small v-if="group.unavailable">来源名称暂不可用，可打开原始画面核对。</small>
                        <div class="feedback-list">
                  <el-card v-for="note in group.notes" :key="note.noteId" class="feedback-item" :class="{ active: sourceDrawerOpen && sourceNote?.noteId === note.noteId }" shadow="never">
                    <el-button text class="feedback-item__select" :aria-pressed="sourceDrawerOpen && sourceNote?.noteId === note.noteId" @click="openSourceNote(note)">
                      <span class="feedback-item__content">
                        <span class="feedback-item__heading"><strong>{{ note.originCandidateNumber || group.label }} → {{ versionDetail.versionNumber }}</strong><el-tag size="small" effect="plain" round :type="tagTypeFromTone(feedbackBadgeMeta(note).tone)">{{ feedbackBadgeMeta(note).label }}</el-tag></span>
                        <p>{{ note.content || '该问题仅包含画面标注' }}</p>
                        <p v-if="feedbackVerificationComment(note)" class="feedback-verification">审核人未通过原因：{{ feedbackVerificationComment(note) }}</p>
                        <p v-if="displayedResponse(note)" class="feedback-response">处理说明：{{ displayedResponse(note).responseText }}</p>
                        <small class="feedback-author">{{ feedbackAuthor(note) }} · {{ formatReviewDateTime(note.createTime) }} 提出</small>
                        <small v-if="note.annotations?.items?.length || (note.mediaTimeMs !== null && note.mediaTimeMs !== undefined)"><template v-if="note.annotations?.items?.length">{{ note.annotations.items.length }} 个画面标注</template><template v-if="note.mediaTimeMs !== null && note.mediaTimeMs !== undefined"> · {{ formatMediaTime(note.mediaTimeMs) }}</template></small>
                      </span>
                    </el-button>
                    <ReviewReferenceFiles :files="note.referenceFiles || []" compact />
                  </el-card>
                        </div>
                      </ElTabPane>
                    </ElTabs>
                  </section>
                  <el-empty v-else :image-size="40" description="暂无上一轮修改意见" />
                    </ElTabPane>
                  </ElTabs>
                </aside>
                </div>
                </ElTabPane>
              </ElTabs>
              <el-empty v-else class="feedback-state" :image-size="48" description="审核人没有在该版本提出修改问题" />
            </el-card>
          </div>
        </template>
        <el-empty v-else-if="!canQuery" class="detail-placeholder" :image-size="56" description="当前账号没有版本详情权限" />
        <el-empty v-else class="detail-placeholder" :image-size="56" description="选择版本页签查看文件和审核单信息" />
      </main>
        </ElTabPane>
      </ElTabs>
      <el-pagination v-if="total > pageSize" class="version-pagination" small background layout="prev, pager, next" :current-page="pageNum" :page-size="pageSize" :total="total" :disabled="loading" aria-label="版本历史分页" @current-change="changePage" />
    </div>
    </el-card>
    <ElDrawer v-model="sourceDrawerOpen" :title="sourceNote?.originCandidateId == null ? '上一轮整体反馈' : '上一轮意见 · 原始画面与标注'" size="min(960px, 92vw)" append-to-body destroy-on-close @close="closeSourceNote">
      <el-skeleton v-if="feedbackSourceLoading" :rows="6" animated />
      <el-alert v-else-if="feedbackSourceError" :title="feedbackSourceError.message" type="error" :closable="false"><el-button @click="loadFeedbackSource">重新加载来源文件</el-button></el-alert>
      <template v-else-if="sourceMediaVersion">
        <p>来源 {{ sourceMediaVersion.versionNumber }} · 当前主区域仍为 {{ versionDetail?.versionNumber }}</p>
        <p v-if="sourceNote?.originCandidateId == null">{{ sourceNote?.content }}</p>
        <ReviewMediaWorkspace v-else ref="sourceMedia" :version="sourceMediaVersion" :selected-note="sourceNote" :can-download="canDownload" feedback-mode />
        <ReviewReferenceFiles :files="sourceNote?.referenceFiles || []" />
      </template>
    </ElDrawer>
  </div>
</template>

<style scoped lang="scss">
.version-history-panel { --el-card-bg-color: var(--sg-surface); --el-card-border-color: var(--sg-border); overflow: visible; border-radius: var(--sg-radius-lg); }
.version-history-panel.el-card { border: 0; border-radius: 0; background: transparent; }
.version-history-panel:deep(> .el-card__body) { padding: 0; }
// 只让两侧列表内部滚动，卡片内容层不能截获整页滚动容器的识别。
.version-history-panel > :deep(.el-card__body),
.version-feedback-panel > :deep(.el-card__body) { overflow: visible; }
.history-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.history-heading h3 { margin: 3px 0 7px; font-size: 20px; }
.history-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.history-tools { display: flex; gap: 9px; }
.history-tools:deep(.el-form-item) { margin: 0; }
.history-tools .sg-select { width: 160px; }
.history-error { margin-top: 16px; }
.history-error code { color: inherit; font-size: 10px; }
.history-layout { display: grid; margin-top: 12px; grid-template-columns: minmax(250px, 0.32fr) minmax(0, 1fr); align-items: start; gap: 14px; }
.version-rail-affix,
.feedback-list-affix { width: 100%; min-width: 0; }
.version-rail-affix.el-affix,
.feedback-list-affix.el-affix { width: 100%; }
.version-rail { display: grid; max-height: calc(100dvh - 116px); align-content: start; overflow-x: hidden; overflow-y: auto; scrollbar-width: thin; gap: 8px; }
.version-rail > .el-button {  width: 100%; min-width: 0; height: auto; margin: 0; padding: 14px; color: var(--sg-text); text-align: left; white-space: normal; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; }
.version-rail__content { display: grid; width: 100%; min-width: 0; box-sizing: border-box; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.version-rail :deep(.el-button > span),
.feedback-list :deep(.feedback-item__select > span) { width: 100%; min-width: 0; }

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
.version-feedback-affix-target { margin-top: 14px; }
.version-feedback-panel { --el-card-bg-color: rgba(104, 181, 255, 0.035); --el-card-border-color: rgba(104, 181, 255, 0.18); overflow: visible; border-radius: var(--sg-radius-md); }
.version-feedback-panel.el-card { border: 0; border-radius: 0; background: transparent; }
.version-feedback-panel:deep(> .el-card__body) { display: grid; padding: 0; gap: 12px; }
.version-feedback-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.version-feedback-panel__heading h3 { margin: 3px 0 5px; font-size: 17px; }
.version-feedback-panel__heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 10px; }
.version-feedback-panel__heading > span { color: var(--sg-text-muted); font-size: 10px; white-space: nowrap; }
.feedback-decision { display: grid; padding: 10px 12px; background: rgba(255, 182, 87, 0.055); border: 1px solid rgba(255, 182, 87, 0.24); border-radius: 10px; grid-template-columns: auto minmax(0, 1fr); gap: 12px; align-items: center; }
.feedback-decision.is-approve { background: rgba(103, 194, 58, 0.055); border-color: rgba(103, 194, 58, 0.24); }
.feedback-decision.is-defer { background: rgba(104, 181, 255, 0.055); border-color: rgba(104, 181, 255, 0.24); }
.feedback-decision__icon { display: grid; width: 30px; height: 30px; color: var(--sg-accent); background: var(--sg-accent-soft); border-radius: 50%; place-items: center; }
.feedback-decision.is-approve .feedback-decision__icon { color: #7bd84b; background: rgba(103, 194, 58, 0.1); }
.feedback-decision.is-defer .feedback-decision__icon { color: #68b5ff; background: rgba(104, 181, 255, 0.1); }
.feedback-decision__content { display: flex; min-width: 0; align-items: center; gap: 16px; flex-wrap: wrap; }
.feedback-decision__heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.feedback-decision__heading strong { font-size: 12px; }
.feedback-decision p { flex: 1; min-width: 180px; margin: 0; overflow-wrap: anywhere; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.55; }
.feedback-decision small { margin-left: auto; color: var(--sg-text-muted); font-size: 12px; white-space: nowrap; }
.feedback-decision__count { color: var(--sg-accent); font-size: 13px; font-weight: 700; }
.overall-feedback { min-width: 0; padding: 12px; border: 1px solid var(--sg-border); border-radius: 8px; background: var(--sg-accent-soft); }
.overall-feedback > header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.overall-feedback__items { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.overall-feedback__content { white-space: pre-wrap; overflow-wrap: anywhere; margin: 8px 0; }
.feedback-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 0.44fr); gap: 14px; align-items: start; }
.feedback-list { display: grid; max-height: min(620px, calc(100dvh - 116px)); align-content: start; overflow-x: hidden; overflow-y: auto; scrollbar-width: thin; gap: 10px; }
.feedback-list .feedback-item { width: 100%; min-width: 0; color: var(--sg-text); background: rgba(255, 255, 255, 0.025); border-color: var(--sg-border); border-radius: 9px; }
.feedback-item > :deep(.el-card__body) { display: grid; padding: 13px; gap: 10px; }
.feedback-item__select.el-button { width: 100%; min-width: 0; height: auto; margin: 0; padding: 0; color: inherit; text-align: left; white-space: normal; }
.feedback-item__select.el-button:hover { background: transparent; }
.feedback-item__content { display: grid; width: 100%; min-width: 0; box-sizing: border-box; gap: 8px; }
.feedback-list .feedback-item:hover,
.feedback-list .feedback-item.active { background: rgba(104, 181, 255, 0.07); border-color: rgba(104, 181, 255, 0.42); }
.feedback-item__heading { display: flex; min-width: 0; align-items: flex-start; justify-content: space-between; gap: 8px; }
.feedback-item__heading > strong { min-width: 0; overflow-wrap: anywhere; line-height: 1.5; }
.feedback-item__heading :deep(.el-tag) { flex-shrink: 0; white-space: nowrap; }
.feedback-list strong { font-size: 10px; }
.feedback-list p { margin: 0; color: var(--sg-text-secondary); overflow-wrap: anywhere; font-size: 11px; line-height: 1.6; white-space: pre-wrap; }
.feedback-list small { color: var(--sg-text-muted); overflow-wrap: anywhere; font-size: 9px; }
.feedback-list .feedback-context { color: #68b5ff; line-height: 1.5; }
.feedback-list .feedback-response { padding: 8px; color: var(--sg-text-secondary); font-size: 10px; background: rgba(104, 181, 255, 0.07); border-radius: 7px; }
.feedback-list .feedback-verification { padding: 8px; color: #ffbd82; font-size: 10px; background: rgba(255, 182, 87, 0.07); border-radius: 7px; }
.feedback-state { display: grid; min-height: 100px; padding: 18px; color: var(--sg-text-muted); text-align: center; background: rgba(255, 255, 255, 0.02); border: 1px dashed var(--sg-border); border-radius: 9px; place-items: center; }
.feedback-state.is-error { color: #ffb5ad; }
.feedback-state p { margin: 5px 0 0; font-size: 10px; }

.history-layout { grid-template-columns: minmax(0, 1fr); }
.version-rail { display: flex; flex-wrap: wrap; max-height: 160px; gap: 8px; }
.version-rail > .el-button { width: 180px; padding: 10px; }
.version-tabs { min-width: 0; box-shadow: none; border-color: var(--sg-border); }
.version-tabs > :deep(.el-tabs__header) { background: var(--sg-surface-soft, var(--sg-surface)); }
.version-tabs > :deep(.el-tabs__content) { padding: 12px; }
.version-tab-label { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; }
.version-tab-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--sg-text-muted); font-size: 12px; overflow-wrap: anywhere; }
.history-detail { min-width: 0; }
.version-info-content { margin-top: 8px; }
.version-info-content :deep(.version-detail-card) { border: 0; border-radius: 0; }
.version-info-content :deep(.version-detail-card > .el-card__body) { padding: 0; }
.version-info-content :deep(.version-facts:first-child) { margin-top: 0; }
.feedback-layout { grid-template-columns: 180px minmax(0, 1fr) 300px; gap: 12px; }
.feedback-file-nav { display: grid; gap: 8px; align-content: start; max-height: 680px; overflow-y: auto; }
.feedback-file.el-button { display: block; width: 100%; height: auto; margin: 0; padding: 8px; text-align: left; white-space: normal; }
.feedback-file :deep(.el-button__text), .feedback-file :deep(> span) { display: block; width: 100%; min-width: 0; }
.feedback-file__content { display: grid; width: 100%; min-width: 0; gap: 6px; }
.feedback-file__content small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--sg-text-muted); }
.feedback-file.active { border-color: var(--sg-accent); background: var(--sg-accent-soft); }
.feedback-file__content .el-tag { justify-self: start; }
.feedback-file__content .feedback-pending-tag.el-tag { --el-tag-bg-color: var(--sg-accent); --el-tag-border-color: var(--sg-accent); --el-tag-text-color: #fff; font-weight: 600; }
.feedback-media, .feedback-list-panel { min-width: 0; }
.feedback-list-panel { padding: 0; border-radius: 8px; }
.opinion-tabs { overflow: hidden; border-radius: 8px; box-shadow: none; border-color: var(--sg-border); }
.feedback-list-panel .opinion-tabs > :deep(.el-tabs__header) { margin-bottom: 0; }
.opinion-tabs > :deep(.el-tabs__content) { padding: 10px; }
.previous-issues { margin: 0; }
.previous-issues > p { font-size: 12px; color: var(--sg-text-muted); line-height: 1.6; }
.feedback-list-panel h4 { margin: 0 0 8px; font-size: 12px; }
.feedback-list-panel :deep(.el-tabs__header) { margin-bottom: 10px; }
.feedback-list-panel :deep(.el-tabs__item) { padding: 0 8px; height: 32px; font-size: 12px; }
.feedback-list .feedback-item { background: var(--sg-surface); }
.feedback-list :deep(:is(strong, p, small, .el-tag)) { font-size: 12px; }
.feedback-summary.version-feedback-panel__heading { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; padding: 12px; border: 1px solid var(--sg-border); border-radius: 10px; }
.feedback-summary__top, .feedback-summary__bottom { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; min-width: 0; }
.feedback-summary__top h3 { margin: 0; font-size: 15px; }
.feedback-summary__top small { margin-left: auto; color: var(--sg-text-muted); font-size: 12px; }
.feedback-summary__bottom { color: var(--sg-text-secondary); font-size: 12px; }
.feedback-summary__bottom p { flex: initial; margin: 0; font-size: 12px !important; }
.feedback-summary__hint { margin-left: auto; color: var(--sg-text-muted); }
.feedback-list-panel { max-height: min(560px, calc(100dvh - 160px)); overflow: auto; scrollbar-width: thin; }
.feedback-list-panel .feedback-list { max-height: none; overflow: visible; }
.previous-issues__list { min-width: 0; }
.previous-issues__list :deep(> .el-tabs__header) { margin: 0 0 8px; }
.previous-issues__list :deep(> .el-tabs__header .el-tabs__item) { height: 32px; padding: 0 10px; font-size: 12px; }
.previous-issues__list :deep(> .el-tabs__content) { overflow: visible; }
.previous-issues .feedback-item > :deep(.el-card__body) { padding: 10px; }
.feedback-media :deep(.media-workspace) { padding: 0; border: 0; background: transparent; }
.feedback-media :deep(.media-heading) { display: none; }
@media (max-width: 1250px) {
  .feedback-layout { grid-template-columns: 160px minmax(0, 1fr); }
  .feedback-list-panel { grid-column: 2; }
  .feedback-file-nav { grid-row: span 2; }
}
@media (max-width: 900px) {
  .history-heading { align-items: stretch; flex-direction: column; }
  .history-layout { grid-template-columns: 1fr; }
  .version-rail-affix,
  .feedback-list-affix { width: auto; }
  .version-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .version-rail footer,
  .version-pagination,
  .history-empty { grid-column: 1 / -1; }
  .feedback-layout { grid-template-columns: 1fr; }
  .feedback-file-nav { grid-row: auto; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); max-height: 240px; }
  .feedback-list-panel { grid-column: 1; }
  .version-rail,
  .feedback-list { max-height: none; overflow-y: visible; }
}

@media (max-width: 600px) {
  .version-rail { grid-template-columns: 1fr; }
}
</style>

<style scoped>
.feedback-category-tabs.is-file-only { border: 0; box-shadow: none; }
.feedback-category-tabs.is-file-only :deep(> .el-tabs__header) { display: none; }
.feedback-category-tabs.is-file-only :deep(> .el-tabs__content) { padding: 0; }
.feedback-category-tabs :deep(> .el-tabs__content) { min-width: 0; }
.feedback-category-tabs :deep(> .el-tabs__header .el-tabs__item) { height: auto; width: 36px; padding: 14px 8px; justify-content: center; font-size: 12px; }
.feedback-category-title { display: flex; flex-direction: column; align-items: center; gap: 5px; }
.feedback-category-count { min-width: 16px; height: 16px; padding: 0 3px; font-size: 10px; line-height: 14px; }
.feedback-category-label { writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 2px; line-height: 18px; }
.feedback-category-tabs .overall-feedback { background: transparent; }
.version-feedback-panel .feedback-author { font-size: 10px; }
</style>
