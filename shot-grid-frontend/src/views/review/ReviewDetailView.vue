<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { ElAffix, ElMessage, ElMessageBox } from 'element-plus'

import {
  addVersionIssueDraft,
  createReviewAction,
  deleteVersionIssueDraft,
  getReviewActions,
  getReviewListDetail,
  getVersionReviewContext,
  transitionManualReviewList,
  updateVersionIssueDraft
} from '@/api/shot-grid/reviews'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { getVersionDetail } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'
import { useSessionStore } from '@/store/modules/session'
import { createIdempotencyState } from '@/utils/idempotency'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
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

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const review = ref(null)
const version = ref(null)
const reviewContext = ref(null)
const actions = ref([])
const loading = ref(false)
const pageError = ref(null)
const issueBusy = ref(false)
const draftActionBusyId = ref(null)
const actionBusy = ref('')
const manualBusy = ref('')
const activeManualVersionId = ref(null)
const selectedIssueId = ref(null)
const mediaWorkspace = ref(null)
const issueFormRef = ref(null)
const issueComposer = ref(null)
const issueProblemInput = ref(null)
const issueDraftPulse = ref(false)
const editingDraftId = ref(null)
const editingDraftLockVersion = ref(null)
const assistantAffixed = ref(false)
const decisionReason = ref('')
const issueDraft = reactive({ problem: '', target: '', mediaSeconds: null, annotations: null })
const verificationDraft = reactive({})
let pageController = null
let pageGeneration = 0
let actionIdempotency = createIdempotencyState('review-action')
let issueDraftPulseTimer = null

const reviewListId = computed(() => assertPositiveId(route.params.reviewListId, '审核单'))
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canDownload = computed(() => hasPermission('shotgrid:file:download'))
const canQueryReview = computed(() => hasPermission('shotgrid:reviewList:query'))
const canQueryVersion = computed(() => hasPermission('shotgrid:version:query'))
const canListVersions = computed(() => hasPermission('shotgrid:version:list'))
const canAddIssue = computed(() => hasPermission('shotgrid:note:add') && canSubmitDecision.value)
const canReview = computed(() => hasPermission('shotgrid:version:review'))
const canActivateManual = computed(() => hasPermission('shotgrid:reviewList:activate'))
const canCompleteManual = computed(() => hasPermission('shotgrid:reviewList:complete'))
const canArchiveManual = computed(() => hasPermission('shotgrid:reviewList:archive'))
const carriedIssues = computed(() => reviewContext.value?.carriedIssues || [])
const currentVersionIssues = computed(() => reviewContext.value?.currentVersionIssues || [])
const currentVersionDrafts = computed(() => reviewContext.value?.currentVersionDrafts || [])
const currentIssueCount = computed(() => currentVersionDrafts.value.length + currentVersionIssues.value.length)
const draftAnnotationCount = computed(() => issueDraft.annotations?.items?.length || 0)
const issueDraftMediaTimeMs = computed(() => issueDraft.mediaSeconds === null
  ? null
  : Math.round(Number(issueDraft.mediaSeconds) * 1000))
const hasUnsavedIssueDraft = computed(() => Boolean(
  issueDraft.problem.trim()
  || issueDraft.target.trim()
  || issueDraft.mediaSeconds !== null
  || draftAnnotationCount.value
))
const assistantShell = computed(() => assistantAffixed.value ? ElAffix : 'div')
const assistantShellProps = computed(() => assistantAffixed.value ? { offset: 92 } : {})
const manualVersions = computed(() => review.value?.versions || [])
const canSubmitDecision = computed(() => (
  canReview.value && review.value?.reviewStatus === 'active' && version.value?.versionStatus === 'pending_review'
))
const issueRules = {
  problem: [
    { validator: validateIssueContent, trigger: 'change' },
    { max: 1000, message: '问题描述不能超过 1000 个字符', trigger: 'blur' }
  ],
  target: [{ max: 1000, message: '修改目标不能超过 1000 个字符', trigger: 'blur' }],
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
  const [versionResponse, contextResponse, actionResponse] = await Promise.all([
    getVersionDetail(versionId, options),
    canReview.value
      ? getVersionReviewContext(versionId, options)
      : Promise.resolve({ data: { currentVersion: null, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } }),
    getReviewActions(versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }, options)
  ])
  return {
    version: versionResponse.data,
    context: contextResponse.data,
    actions: actionResponse.rows || []
  }
}

function applyVersionReview(payload, versionId) {
  version.value = payload.version
  reviewContext.value = payload.context
  actions.value = payload.actions
  activeManualVersionId.value = versionId
  selectedIssueId.value = null
  decisionReason.value = ''
  clearIssueDraft()
  initializeVerificationDraft()
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
  const problem = issueDraft.problem.trim()
  const target = issueDraft.target.trim()
  return [problem ? `问题：${problem}` : '', target ? `修改目标：${target}` : ''].filter(Boolean).join('\n') || null
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
  editingDraftLockVersion.value = null
  Object.assign(issueDraft, { problem: '', target: '', mediaSeconds: null, annotations: null })
  issueFormRef.value?.clearValidate()
  mediaWorkspace.value?.clearDraft()
}

function parseIssueContent(content) {
  const text = String(content || '').trim()
  if (!text) return { problem: '', target: '' }
  const problemMatch = text.match(/(?:^|\n)问题：([\s\S]*?)(?=\n修改目标：|$)/)
  const targetMatch = text.match(/(?:^|\n)修改目标：([\s\S]*)$/)
  return {
    problem: problemMatch?.[1]?.trim() || (targetMatch ? '' : text),
    target: targetMatch?.[1]?.trim() || ''
  }
}

function cloneIssueAnnotations(annotations) {
  return annotations ? JSON.parse(JSON.stringify(annotations)) : null
}

async function focusIssueDraft() {
  if (!canAddIssue.value) return
  issueDraftPulse.value = false
  if (issueDraftPulseTimer) clearTimeout(issueDraftPulseTimer)
  await nextTick()
  issueDraftPulse.value = true
  issueComposer.value?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
  issueProblemInput.value?.focus?.()
  issueDraftPulseTimer = setTimeout(() => { issueDraftPulse.value = false }, 1500)
}

async function submitIssue() {
  if (issueBusy.value) return
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
      content,
      mediaTimeMs: seconds === null ? null : Math.round(seconds * 1000),
      annotations: issueDraft.annotations
    }
    if (editingDraftId.value) {
      await updateVersionIssueDraft(version.value.versionId, editingDraftId.value, {
        ...payload,
        lockVersion: editingDraftLockVersion.value
      })
    } else {
      await addVersionIssueDraft(version.value.versionId, payload)
    }
    const wasEditing = Boolean(editingDraftId.value)
    clearIssueDraft()
    ElMessage.success(wasEditing ? '问题草稿已更新，制作人仍不可见' : '问题已保存为草稿，点击“退回并发送问题”后才会发送给制作人')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, editingDraftId.value ? '更新问题草稿失败' : '保存问题草稿失败').message)
  } finally {
    issueBusy.value = false
  }
}

async function editIssueDraft(draft) {
  const content = parseIssueContent(draft.content)
  editingDraftId.value = draft.draftId
  editingDraftLockVersion.value = draft.lockVersion
  Object.assign(issueDraft, {
    ...content,
    mediaSeconds: draft.mediaTimeMs === null || draft.mediaTimeMs === undefined
      ? null
      : Number((Number(draft.mediaTimeMs) / 1000).toFixed(3)),
    annotations: cloneIssueAnnotations(draft.annotations)
  })
  selectedIssueId.value = `draft-${draft.draftId}`
  await nextTick()
  mediaWorkspace.value?.loadDraft(draft.annotations, draft.mediaTimeMs)
  await focusIssueDraft()
}

async function removeIssueDraft(draft) {
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
  issueDraft.mediaSeconds = Number((Number(milliseconds) / 1000).toFixed(3))
  focusIssueDraft()
}

function updateAnnotations(annotations) {
  issueDraft.annotations = annotations
  if (draftAnnotationCount.value) {
    issueFormRef.value?.clearValidate('problem')
    focusIssueDraft()
  }
}

function returnToDraftPosition() {
  mediaWorkspace.value?.seekToDraft(issueDraftMediaTimeMs.value)
}

async function focusIssue(issue) {
  selectedIssueId.value = issue.issueId
  await nextTick()
  mediaWorkspace.value?.seekToNote()
}

function openTask() {
  if (review.value?.taskId) router.push(`/tasks/${review.value.taskId}#version-workspace`)
}

async function submitDecision(actionType) {
  if (!canSubmitDecision.value || actionBusy.value) return
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
  if (actionType === 'reject' && currentVersionDrafts.value.length) {
    try {
      await ElMessageBox.confirm(
        `将退回当前版本，并把 ${currentVersionDrafts.value.length} 条问题草稿正式发送给制作人。发布后问题不可修改或删除。`,
        '确认退回并发布问题',
        { type: 'warning', confirmButtonText: '退回并发送', cancelButtonText: '继续检查' }
      )
    } catch {
      return
    }
  }
  const payload = {
    actionType,
    reason: decisionReason.value.trim() || null,
    lockVersion: reviewContext.value?.currentVersion?.lockVersion ?? version.value.lockVersion,
    issueVerifications: actionType === 'defer' ? [] : verificationItems.value
  }
  const context = { reviewListId: reviewListId.value, versionId: version.value.versionId, ...payload }
  actionBusy.value = actionType
  try {
    await createReviewAction(version.value.versionId, payload, actionIdempotency.forPayload(context))
    actionIdempotency.reset()
    ElMessage.success(`${reviewActionMeta(actionType).label}已提交`)
    await loadReview()
  } catch (error) {
    const state = reviewErrorState(error, '审核决定提交失败')
    ElMessage.error(state.status === 409 ? `${state.message}，页面正在刷新` : state.message)
    if (state.status === 409) await loadReview()
  } finally {
    actionBusy.value = ''
  }
}

function updateAssistantMode() {
  assistantAffixed.value = typeof window !== 'undefined' && window.innerWidth > 1100
}

onMounted(() => {
  updateAssistantMode()
  window.addEventListener('resize', updateAssistantMode)
  loadReview()
})
onBeforeUnmount(() => {
  pageGeneration += 1
  pageController?.abort()
  if (issueDraftPulseTimer) clearTimeout(issueDraftPulseTimer)
  window.removeEventListener('resize', updateAssistantMode)
})
</script>

<template>
  <section class="sg-page review-detail-page">
    <header class="sg-page-heading">
      <div class="review-detail-heading">
        <el-button link :icon="ArrowLeft" @click="router.push('/reviews')">返回审核列表</el-button>
        <div v-if="review"><p class="sg-eyebrow">REVIEW DETAIL</p><h2>{{ review.reviewListName }}</h2><p>审核意见绑定提出时的版本；下一版必须逐条说明修改结果，并由审核人逐条确认。</p></div>
      </div>
      <div class="heading-actions"><el-tag v-if="review" size="small" effect="plain" round :type="tagTypeFromTone(reviewModeMeta(review.reviewMode).tone)">{{ reviewModeMeta(review.reviewMode).label }}</el-tag><el-tag v-if="review" size="small" effect="light" round :type="tagTypeFromTone(reviewStatusMeta(review.reviewStatus).tone)">{{ reviewStatusMeta(review.reviewStatus).label }}</el-tag><el-button :icon="Refresh" :loading="loading" @click="loadReview">刷新</el-button></div>
    </header>

    <ProjectStatePanel v-if="pageError" :title="pageError.title" :message="pageError.message" :retryable="pageError.retryable" @retry="loadReview" />
    <el-card v-else-if="loading && !version" class="review-detail-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="9" /></el-card>
    <template v-else-if="review">
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
        <main class="review-main">
          <ReviewProductionTarget v-if="version.productionTarget" :target="version.productionTarget" />

          <section class="review-work-step">
            <header class="work-step-heading"><span class="step-number">1</span><div><strong>播放并检查作品</strong><p>发现问题时暂停画面，点击“记录这个画面的问题”，右侧会立即准备好问题草稿。</p></div></header>
            <ReviewMediaWorkspace
              ref="mediaWorkspace"
              :version="version"
              :selected-note="selectedIssue"
              :can-download="canDownload"
              :can-compare="canListVersions"
              :can-annotate="canAddIssue"
              :draft-media-time-ms="issueDraftMediaTimeMs"
              :draft-annotation-count="draftAnnotationCount"
              @capture-time="captureMediaTime"
              @start-issue="focusIssueDraft"
              @annotations-change="updateAnnotations"
              @clear-note-focus="selectedIssueId = null"
            />
          </section>

          <VersionDetailCard :version="version" :can-download="canDownload" :show-preview="false" />

          <el-card class="action-history" shadow="never">
            <header><div><p class="sg-eyebrow">HISTORY</p><h3>审核动作记录</h3></div><span>{{ actions.length }} 条</span></header>
            <el-timeline v-if="actions.length" class="action-list"><el-timeline-item v-for="item in actions" :key="item.actionId" :type="tagTypeFromTone(reviewActionMeta(item.actionType).tone)" :timestamp="formatReviewDateTime(item.createTime)" placement="top"><strong>{{ reviewActionMeta(item.actionType).label }}</strong><p>{{ item.reason || '未填写整体说明' }}</p><small>{{ item.reviewerName || `用户 #${item.reviewerUserId}` }}</small><span class="action-transition"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.fromStatus).tone)">{{ taskVersionStatusMeta(item.fromStatus).label }}</el-tag><span aria-hidden="true">→</span><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.toStatus).tone)">{{ taskVersionStatusMeta(item.toStatus).label }}</el-tag></span></el-timeline-item></el-timeline>
            <el-empty v-else class="empty-block" :image-size="44" description="尚无审核动作" />
          </el-card>
        </main>

        <component :is="assistantShell" v-bind="assistantShellProps" class="review-assistant-affix">
          <aside class="review-assistant">
            <header class="assistant-heading"><div><p class="sg-eyebrow">REVIEW NOTES</p><h3>审核记录</h3></div><el-tag size="small" effect="plain" round>随作品保持可见</el-tag></header>

            <el-scrollbar class="assistant-body">
              <div class="assistant-body__inner">
                <section v-if="carriedIssues.length" class="assistant-section carried-panel">
                  <header class="assistant-section-heading"><div class="assistant-section-kicker">上轮问题</div><div><h3>先确认是否已修复</h3><p>对照当前作品，逐条确认制作人的处理结果。</p></div><strong>{{ carriedIssues.length }} 条</strong></header>
                  <div class="issue-list carried-list">
                    <el-card v-for="issue in carriedIssues" :key="issue.issueId" class="issue-card" :class="{ 'is-selected': selectedIssueId === issue.issueId }" shadow="never">
                      <header><span>{{ issue.originVersionNumber }} 问题</span><el-button link type="primary" @click="focusIssue(issue)">{{ issue.annotations?.items?.length ? `查看标注 ${issue.annotations.items.length} 处` : '定位原版意见' }}</el-button></header>
                      <p>{{ issue.content || '该问题仅包含画面标注' }}</p>
                      <div class="maker-response"><span>制作人对 {{ version.versionNumber }} 的处理说明</span><strong>{{ issue.currentVersionResponse.responseText }}</strong></div>
                      <el-radio-group v-model="verificationDraft[issue.issueId].result" class="verification-options">
                        <el-radio-button value="resolved">已修复</el-radio-button>
                        <el-radio-button value="still_present">仍然存在</el-radio-button>
                      </el-radio-group>
                      <label v-if="verificationDraft[issue.issueId].result === 'still_present'" class="verification-comment">
                        <span>说明仍然存在的问题 <em>*</em></span>
                        <el-input v-model="verificationDraft[issue.issueId].comment" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="请具体说明哪里仍未达到要求，方便制作人下一轮准确修改。" />
                      </label>
                    </el-card>
                  </div>
                </section>

                <section ref="issueComposer" class="assistant-section current-panel" :class="{ 'is-draft-focus': issueDraftPulse }">
                  <header class="assistant-section-heading"><span class="step-number">2</span><div><h3>记录发现的问题</h3><p>先保存为审核草稿；只有点击“退回并发送问题”后，制作人才会看到。</p></div><strong>{{ currentVersionDrafts.length }} 条草稿</strong></header>
                  <el-form v-if="canAddIssue" ref="issueFormRef" :model="issueDraft" :rules="issueRules" class="issue-compose" label-position="top" aria-label="记录当前版新问题">
                    <el-form-item label="问题描述" prop="problem"><el-input ref="issueProblemInput" v-model="issueDraft.problem" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="看到什么问题？例如：眼睛红色饱和度过高。" /></el-form-item>
                    <el-form-item label="修改目标" prop="target"><el-input v-model="issueDraft.target" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="希望如何修改？例如：降低红色饱和度，并保持肤色不变。" /></el-form-item>
                    <el-form-item v-if="issueDraftMediaTimeMs !== null || draftAnnotationCount" label="作品定位">
                      <div class="issue-compose-meta">
                        <div class="issue-context-tags">
                          <el-button v-if="issueDraftMediaTimeMs !== null" class="issue-position-button" size="small" plain round @click="returnToDraftPosition">回到 {{ formatMediaTime(issueDraftMediaTimeMs) }}</el-button>
                          <el-button v-if="draftAnnotationCount" class="issue-position-button" size="small" type="warning" plain round @click="returnToDraftPosition">查看 {{ draftAnnotationCount }} 处标注</el-button>
                        </div>
                        <el-button link type="danger" @click="clearIssueDraft">清除定位</el-button>
                      </div>
                    </el-form-item>
                    <el-form-item class="issue-compose__actions"><el-button v-if="hasUnsavedIssueDraft" :disabled="issueBusy" @click="clearIssueDraft">{{ editingDraftId ? '取消编辑' : '清空草稿' }}</el-button><el-button type="primary" :loading="issueBusy" @click="submitIssue">{{ editingDraftId ? '更新问题草稿' : '保存问题草稿' }}</el-button></el-form-item>
                  </el-form>
                  <div v-if="currentVersionDrafts.length" class="issue-list current-list">
                    <el-card v-for="(draft, index) in currentVersionDrafts" :key="draft.draftId" class="issue-card issue-draft-card" :class="{ 'is-selected': selectedIssueId === `draft-${draft.draftId}` }" shadow="never">
                      <header>
                        <span>待提交草稿 #{{ index + 1 }}</span>
                        <div class="issue-card-actions">
                          <el-button link type="primary" @click="focusIssue({ ...draft, issueId: `draft-${draft.draftId}`, originVersionId: draft.versionId })">{{ draft.annotations?.items?.length ? `查看标注 ${draft.annotations.items.length} 处` : '查看对应作品' }}</el-button>
                          <el-button link type="warning" :disabled="Boolean(draftActionBusyId)" @click="editIssueDraft(draft)">编辑</el-button>
                          <el-button link type="danger" :loading="draftActionBusyId === draft.draftId" :disabled="Boolean(draftActionBusyId)" @click="removeIssueDraft(draft)">删除</el-button>
                        </div>
                      </header>
                      <p>{{ draft.content || '该问题仅包含画面标注' }}</p>
                      <small>{{ draft.reviewerName || `审核人 #${draft.reviewerUserId}` }} · {{ formatReviewDateTime(draft.updateTime) }}</small>
                    </el-card>
                  </div>
                  <el-alert v-if="currentVersionIssues.length" type="warning" :closable="false" show-icon title="检测到旧版已提前发布的问题数据；这些问题只读，建议完成本轮审核后不再沿用旧流程。" />
                </section>
              </div>
            </el-scrollbar>

            <section class="assistant-section decision-panel">
              <header class="assistant-section-heading"><span class="step-number">3</span><div><h3>提交审核结论</h3><p>确认所有问题后，再完成本轮审核。</p></div></header>
              <div class="decision-summary">
                <span v-if="carriedIssues.length">上轮问题 {{ carriedIssues.length }} 条，已确认 {{ completedVerificationCount }} 条</span>
                <span v-else>当前版本已保存 {{ currentVersionDrafts.length }} 条问题草稿</span>
                <strong v-if="unresolvedVerificationCount || currentIssueCount" class="danger">退回时将发送 {{ unresolvedVerificationCount + currentIssueCount }} 条修改要求</strong>
                <strong v-else-if="verificationComplete" class="success">当前没有待修改问题</strong>
              </div>
              <el-input v-model="decisionReason" type="textarea" :rows="2" maxlength="1000" placeholder="本轮审核整体说明（可选）" />
              <el-alert v-if="!verificationComplete" class="decision-warning" type="warning" :closable="false" show-icon title="请先逐条确认全部上轮问题；“仍然存在”必须说明原因。" />
              <div class="decision-actions">
                <el-button type="success" :loading="actionBusy === 'approve'" :disabled="!canApprove || Boolean(actionBusy)" @click="submitDecision('approve')">全部符合，确认通过</el-button>
                <el-button type="danger" plain :loading="actionBusy === 'reject'" :disabled="!canReject || Boolean(actionBusy)" @click="submitDecision('reject')">退回并发送问题{{ currentVersionDrafts.length ? `（${currentVersionDrafts.length}）` : '' }}</el-button>
                <el-button :loading="actionBusy === 'defer'" :disabled="!canSubmitDecision || Boolean(actionBusy)" @click="submitDecision('defer')">稍后决定</el-button>
              </div>
              <el-button v-if="version.versionStatus === 'rejected'" link type="primary" @click="openTask">查看制作任务</el-button>
            </section>
          </aside>
        </component>
      </div>
    </template>
  </section>
</template>

<style scoped>
:global(.app-content:has(.review-detail-page)){overflow:visible}
.review-detail-page{display:grid;gap:18px}.review-detail-heading,.heading-actions{display:flex;gap:13px;align-items:center}.review-detail-heading h2{margin:3px 0}.review-detail-heading p{margin:0;color:var(--sg-text-muted);font-size:11px}.review-detail-loading{display:grid;min-height:320px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg);place-items:center}
.review-context-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.review-context-strip>div{display:grid;gap:6px;padding:13px 15px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:10px}.review-context-strip span{color:var(--sg-text-muted);font-size:10px}.review-context-strip strong{font-size:13px}.danger{color:var(--sg-danger)!important}.success{color:var(--sg-success)!important}
.manual-strip{display:grid;gap:14px;padding:18px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.manual-strip>header{display:flex;gap:14px;align-items:center;justify-content:space-between}.manual-strip h3{margin:3px 0 0;font-size:16px}.manual-strip>header>div:last-child,.manual-version-list{display:flex;gap:8px;flex-wrap:wrap}
.review-detail-grid{display:grid;grid-template-columns:minmax(0,3fr) minmax(380px,1fr);gap:18px;align-items:start}.review-main{display:grid;gap:18px}.review-work-step{display:grid;gap:12px}.work-step-heading{display:flex;gap:10px;align-items:center;padding:0 3px}.work-step-heading div{display:grid;gap:2px}.work-step-heading strong{font-size:13px}.work-step-heading p{margin:0;color:var(--sg-text-muted);font-size:10px}.step-number{display:grid;flex:0 0 auto;width:24px;height:24px;color:var(--sg-accent);font-size:11px;font-weight:800;background:var(--sg-accent-soft);border:1px solid rgba(255,179,71,.35);border-radius:50%;place-items:center}
.review-assistant-affix{width:100%;min-width:0}.review-assistant-affix:deep(.el-affix){width:100%}.review-assistant{display:grid;width:100%;height:calc(100dvh - 108px);max-height:880px;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;background:var(--sg-surface);border:1px solid var(--sg-border-strong);border-radius:var(--sg-radius-md);box-shadow:0 16px 36px rgba(0,0,0,.16)}.assistant-heading{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--sg-border)}.assistant-heading h3{margin:3px 0 0;font-size:17px}.assistant-heading:deep(.el-tag){color:var(--sg-text-muted)}.assistant-body{min-height:0}.assistant-body:deep(.el-scrollbar__wrap){scrollbar-width:thin}.assistant-body__inner{display:grid}.assistant-section{display:grid;gap:12px;padding:15px 18px;border-top:1px solid var(--sg-border)}.assistant-body__inner>.assistant-section:first-child{border-top:0}.assistant-section-heading{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:start}.assistant-section-heading h3{margin:1px 0 0;font-size:14px}.assistant-section-heading p{margin:3px 0 0;color:var(--sg-text-muted);font-size:9px;line-height:1.45}.assistant-section-heading>strong{color:var(--sg-text-muted);font-size:10px}.assistant-section-kicker{align-self:center;padding:4px 7px;color:var(--sg-accent);font-size:8px;font-weight:800;letter-spacing:.08em;background:var(--sg-accent-soft);border-radius:999px;white-space:nowrap}
.issue-list{display:grid;gap:10px}.issue-card{display:grid;gap:9px;padding:12px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.issue-card.is-selected{border-color:var(--sg-accent);box-shadow:0 0 0 1px var(--sg-accent-soft)}.issue-card>header{display:flex;gap:8px;align-items:center;justify-content:space-between}.issue-card>header span{color:var(--sg-accent);font-size:9px;font-weight:700}.issue-card>header button{padding:0;color:#68b5ff;font:inherit;font-size:9px;background:transparent;border:0;cursor:pointer}.issue-card>p{margin:0;color:var(--sg-text-secondary);font-size:10px;line-height:1.65;white-space:pre-wrap}.issue-card>small{color:var(--sg-text-muted);font-size:8px}.maker-response{display:grid;gap:5px;padding:9px;color:var(--sg-text-secondary);background:rgba(104,181,255,.07);border-radius:8px}.maker-response span{font-size:8px}.maker-response strong{font-size:10px;line-height:1.55;white-space:pre-wrap}.verification-options{width:100%}.verification-options :deep(.el-radio-button){width:50%}.verification-options :deep(.el-radio-button__inner){width:100%}.verification-comment{display:grid;gap:6px}.verification-comment>span{color:var(--sg-text-secondary);font-size:9px}.verification-comment em{color:var(--sg-danger);font-style:normal}.current-panel{transition:background-color .2s ease,box-shadow .2s ease}.current-panel.is-draft-focus{background:var(--sg-accent-soft);box-shadow:inset 3px 0 0 var(--sg-accent)}.issue-compose{display:grid;gap:9px;padding:11px;background:rgba(0,0,0,.12);border-radius:10px}.issue-compose :deep(.el-form-item){margin-bottom:0}.issue-compose__actions :deep(.el-form-item__content){display:flex;gap:8px;justify-content:flex-end}.issue-compose-meta{display:flex;width:100%;gap:8px;align-items:center;justify-content:space-between}.issue-context-tags{display:flex;gap:6px;flex-wrap:wrap}.issue-position-button{margin:0}.empty-block{padding:20px 8px;margin:0;color:var(--sg-text-muted);font-size:10px;text-align:center}.empty-block.compact{padding:12px 8px}
.issue-card-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.issue-card-actions .el-button{margin:0}.issue-draft-card{border-style:dashed}.issue-draft-card>small{color:var(--sg-text-muted)}
.decision-panel{position:relative;z-index:1;background:color-mix(in srgb,var(--sg-surface) 94%,var(--sg-accent) 6%);box-shadow:0 -12px 28px rgba(0,0,0,.09)}.decision-summary{display:grid;gap:5px;padding:10px;color:var(--sg-text-secondary);font-size:9px;background:rgba(255,255,255,.025);border-radius:8px}.decision-warning{display:flex;gap:6px;align-items:center;margin:0;color:var(--sg-danger);font-size:9px}.decision-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.decision-actions .el-button{margin:0}.decision-actions .el-button:last-child{grid-column:1/-1}.action-history{padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.action-history>header{display:flex;justify-content:space-between}.action-history h3{margin:3px 0 0;font-size:16px}.action-history>header>span{color:var(--sg-text-muted);font-size:10px}.action-list{display:grid;gap:12px;margin-top:15px}.action-list article{display:grid;grid-template-columns:auto 1fr;gap:10px}.action-dot{width:9px;height:9px;margin-top:4px;background:var(--sg-text-muted);border-radius:50%}.action-dot[data-tone=success]{background:var(--sg-success)}.action-dot[data-tone=danger]{background:var(--sg-danger)}.action-dot[data-tone=warning]{background:var(--sg-accent)}.action-list strong,.action-list p,.action-list small{display:block;margin:0}.action-list p{margin:4px 0;color:var(--sg-text-secondary);font-size:11px}.action-list small{color:var(--sg-text-muted);font-size:9px}
.action-transition{display:flex;gap:6px;align-items:center;margin-top:7px;color:var(--sg-text-muted)}
@media(max-width:1100px){.review-detail-grid{grid-template-columns:1fr}.review-assistant{height:auto;max-height:none}.assistant-body{height:auto}}@media(max-width:700px){.review-context-strip{grid-template-columns:1fr 1fr}.sg-page-heading,.manual-strip>header{align-items:flex-start}.heading-actions,.manual-strip>header{flex-direction:column}.issue-compose-meta{align-items:flex-start;flex-direction:column}.decision-actions{grid-template-columns:1fr}.decision-actions .el-button:last-child{grid-column:auto}}
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
</style>
