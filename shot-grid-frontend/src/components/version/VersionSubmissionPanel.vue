<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Refresh, UploadFilled } from '@element-plus/icons-vue'

import {
  createVersionSubmission,
  getCurrentTaskVersionSubmission,
  getVersionSubmissionStatus,
  preflightVersionSubmission,
  retryVersionSubmission,
  uploadProtectedVersionFile
} from '@/api/shot-grid/versions'
import { createIdempotencyState } from '@/utils/idempotency'
import VersionSubmissionStatus from './VersionSubmissionStatus.vue'
import {
  acceptedToSubmissionStatus,
  isSubmissionTerminal,
  versionErrorState
} from './versionPresentation'

const MAX_VERSION_FILE_SIZE = 100 * 1024 * 1024
const MAX_VERSION_BATCH_SIZE = 500 * 1024 * 1024
const MAX_VERSION_CANDIDATES = 10
const MAX_AUTOMATIC_POLL_ATTEMPTS = 30
const MAX_CONSECUTIVE_POLL_ERRORS = 3
const MAX_POLL_BACKOFF_MS = 30_000

const props = defineProps({
  taskId: { type: Number, required: true },
  taskKind: { type: String, required: true },
  taskStatus: { type: String, required: true },
  versionCount: { type: Number, default: 0 },
  productionDescription: { type: String, default: '' },
  openIssues: { type: Array, default: () => [] },
  allowedActions: { type: Array, default: () => [] },
  hasUncommittedSubmission: { type: Boolean, default: false },
  hasAddPermission: { type: Boolean, default: false },
  canQuery: { type: Boolean, default: false },
  canRetry: { type: Boolean, default: false },
  operationGeneration: { type: Number, default: 0 },
  pollInterval: { type: Number, default: 2000 }
})
const emit = defineEmits(['committed', 'submission-change', 'focus-issue'])

const selectedCandidates = ref([])
const changelog = ref('')
const issueHandlingStates = ref({})
const issueUnhandledReasons = ref({})
const submissionFormRef = ref(null)
const fileUploadRef = ref(null)
const formValidating = ref(false)
const openIssueSnapshotHash = ref('')
const uploadResults = ref({})
const uploadProgress = ref(0)
const submission = ref(null)
const phase = ref('idle')
const recovering = ref(false)
const recoveryResolved = ref(false)
const requestError = ref(null)
const pollError = ref(null)
const validationMessage = ref('')

let disposed = false
let contextGeneration = 0
let fileGeneration = 0
let recoveryController = null
let workflowController = null
let pollController = null
let pollTimer = null
let pollAttemptCount = 0
let consecutivePollErrors = 0
let idempotency = createIdempotencyState(`version-${props.taskId}`)

const acceptedExtensions = computed(() => props.taskKind === 'asset_image' ? ['jpg', 'png'] : ['mp4', 'mov'])
const acceptAttribute = computed(() => acceptedExtensions.value.map(item => `.${item}`).join(','))
const isRevisionSubmission = computed(() => props.taskStatus === 'revision' || Number(props.versionCount) > 0)
const nextVersionNumber = computed(() => `V${String(Math.max(1, Number(props.versionCount || 0) + 1)).padStart(3, '0')}`)
const submissionCopy = computed(() => isRevisionSubmission.value
  ? {
      eyebrow: 'REVISE & RESUBMIT',
      title: '提交修改成果',
      description: `根据审核意见上传修改后的候选成果，提交后将生成 ${nextVersionNumber.value} 并重新进入审核。`,
      uploadPrompt: '选择修改后的候选成果',
      changelogLabel: '本轮修改说明',
      footerHint: `提交后可在此查看文件保存、${nextVersionNumber.value} 生成和重新送审进度。`,
      submitLabel: '提交修改成果并重新送审',
      retryLabel: '重试提交修改成果'
    }
  : {
      eyebrow: 'FIRST DELIVERY',
      title: '提交首版成果',
      description: `上传第一轮候选成果，提交后将生成 ${nextVersionNumber.value} 并进入审核。`,
      uploadPrompt: '选择首版候选成果',
      changelogLabel: '首版交付说明',
      footerHint: `提交后可在此查看文件保存、${nextVersionNumber.value} 生成和审核准备进度。`,
      submitLabel: '提交首版并进入审核',
      retryLabel: '重试提交首版成果'
    })
const canSubmit = computed(() => (
  recoveryResolved.value &&
  props.allowedActions.includes('version.add') &&
  props.hasAddPermission
))
const changelogPlaceholder = computed(() => {
  const description = String(props.productionDescription || '').trim()
  if (Number(props.versionCount) === 0 && description) {
    const excerpt = description.length > 120 ? `${description.slice(0, 120)}…` : description
    return `首次提交可参考制作内容：“${excerpt}”。请说明本版本实际完成情况和需要审核人关注的内容。`
  }
  return isRevisionSubmission.value
    ? '概括本轮针对审核意见完成的修改，以及仍需审核人关注的内容。'
    : '说明首版实际完成情况和需要审核人关注的内容。'
})
const issueResponses = computed(() => props.taskStatus === 'revision'
  ? props.openIssues.map(issue => ({
      issueId: Number(issue.issueId),
      responseText: issueHandlingStates.value[issue.issueId] === 'unhandled'
        ? `未处理：${String(issueUnhandledReasons.value[issue.issueId] || '').trim()}`
        : '已处理'
    }))
  : [])
const submissionFormModel = computed(() => ({
  candidates: selectedCandidates.value,
  changelog: changelog.value,
  issueHandlingStates: issueHandlingStates.value,
  issueUnhandledReasons: issueUnhandledReasons.value
}))
const submissionFormRules = {
  candidates: [{ validator: validateSelectedCandidates, trigger: 'change' }],
  changelog: [{ validator: validateChangelog, trigger: 'blur' }]
}
const issueHandlingStateRules = [
  { required: true, message: '请选择该问题的处理情况', trigger: 'change' }
]
const hasActiveSubmission = computed(() => Boolean(submission.value && submission.value.submissionStatus !== 'committed'))
const isBusy = computed(() => formValidating.value || recovering.value || ['preflighting', 'uploading', 'submitting', 'retrying'].includes(phase.value))
const uploadedOnly = computed(() => Boolean(Object.keys(uploadResults.value).length && !submission.value))
const composerLocked = computed(() => isBusy.value || uploadedOnly.value)
const canDiscardUploadedFile = computed(() => (
  uploadedOnly.value && [413, 422].includes(Number(requestError.value?.httpStatus || requestError.value?.status || 0))
))
const operationContext = () => Object.freeze({
  taskId: Number(props.taskId),
  operationGeneration: Number(props.operationGeneration)
})

function isCanceled(error, controller) {
  return error?.code === 'ERR_CANCELED' || controller?.signal.aborted
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
  pollController?.abort()
  pollController = null
}

function resetPollingBudget() {
  pollAttemptCount = 0
  consecutivePollErrors = 0
}

function pauseAutomaticPolling(message) {
  stopPolling()
  pollError.value = {
    title: '自动刷新已暂停',
    message,
    errorKey: null
  }
}

function abortRequests() {
  recoveryController?.abort()
  recoveryController = null
  workflowController?.abort()
  workflowController = null
  stopPolling()
}

function revokeCandidatePreview(candidate) {
  if (candidate?.previewUrl?.startsWith('blob:') && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(candidate.previewUrl)
  }
  if (candidate) candidate.previewUrl = ''
}

function releaseCandidatePreviews(candidates = selectedCandidates.value) {
  candidates.forEach(revokeCandidatePreview)
}

function createCandidatePreviewUrl(file) {
  return file && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : ''
}

function markCandidatePreviewError(candidate) {
  candidate.previewError = true
}

function resetComposer() {
  formValidating.value = false
  releaseCandidatePreviews()
  selectedCandidates.value = []
  fileUploadRef.value?.clearFiles?.()
  changelog.value = ''
  issueHandlingStates.value = Object.fromEntries(props.openIssues.map(issue => [issue.issueId, 'handled']))
  issueUnhandledReasons.value = Object.fromEntries(props.openIssues.map(issue => [issue.issueId, '']))
  openIssueSnapshotHash.value = ''
  uploadResults.value = {}
  uploadProgress.value = 0
  phase.value = 'idle'
  requestError.value = null
  pollError.value = null
  validationMessage.value = ''
  submissionFormRef.value?.clearValidate()
  resetPollingBudget()
  fileGeneration += 1
  idempotency.reset()
}

function resetContext() {
  contextGeneration += 1
  abortRequests()
  recovering.value = false
  recoveryResolved.value = false
  resetComposer()
  submission.value = null
  idempotency = createIdempotencyState(`version-${props.taskId}`)
}

function stillCurrent(generation, targetTaskId, targetOperationGeneration) {
  return !disposed &&
    contextGeneration === generation &&
    Number(props.taskId) === targetTaskId &&
    Number(props.operationGeneration) === targetOperationGeneration
}

function updateSubmission(nextSubmission) {
  if (!nextSubmission) return
  submission.value = { ...(submission.value || {}), ...nextSubmission }
  emit('submission-change', submission.value, operationContext())
}

function applyAcceptedSubmission(data, generation, targetTaskId, targetOperationGeneration) {
  const nextSubmission = acceptedToSubmissionStatus(data)
  if (!nextSubmission) return
  releaseCandidatePreviews()
  updateSubmission(nextSubmission)
  phase.value = nextSubmission.submissionStatus || 'pending'
  resetPollingBudget()
  if (nextSubmission.submissionStatus === 'committed') {
    stopPolling()
    emit('committed', nextSubmission, operationContext())
    return
  }
  if (nextSubmission.submissionStatus === 'failed') {
    stopPolling()
    return
  }
  schedulePoll(generation, targetTaskId, targetOperationGeneration)
}

function schedulePoll(generation, targetTaskId, targetOperationGeneration, immediate = false, delayOverride = null) {
  stopPolling()
  if (!props.canQuery || !submission.value || isSubmissionTerminal(submission.value.submissionStatus)) return
  if (pollAttemptCount >= MAX_AUTOMATIC_POLL_ATTEMPTS) {
    pauseAutomaticPolling('已达到本轮自动刷新次数，提交仍会继续处理；请稍后手动刷新。')
    return
  }
  const delay = immediate
    ? 0
    : delayOverride ?? Math.max(250, Number(props.pollInterval) || 2000)
  pollTimer = setTimeout(() => pollSubmission(generation, targetTaskId, targetOperationGeneration), delay)
}

async function pollSubmission(generation, targetTaskId, targetOperationGeneration) {
  if (!stillCurrent(generation, targetTaskId, targetOperationGeneration) || !submission.value?.submissionId) return
  const targetSubmissionId = Number(submission.value.submissionId)
  const controller = new AbortController()
  pollController = controller
  pollAttemptCount += 1
  try {
    const response = await getVersionSubmissionStatus(targetSubmissionId, { signal: controller.signal })
    if (
      pollController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      Number(submission.value?.submissionId) !== targetSubmissionId
    ) return
    pollError.value = null
    consecutivePollErrors = 0
    updateSubmission(response.data)
    if (response.data?.submissionStatus === 'committed') {
      phase.value = 'committed'
      stopPolling()
      emit('committed', response.data, operationContext())
      return
    }
    if (response.data?.submissionStatus === 'failed') {
      phase.value = 'failed'
      stopPolling()
      return
    }
    schedulePoll(generation, targetTaskId, targetOperationGeneration)
  } catch (error) {
    if (isCanceled(error, controller) || !stillCurrent(generation, targetTaskId, targetOperationGeneration)) return
    pollError.value = versionErrorState(error, '版本状态刷新失败')
    const status = Number(error?.httpStatus || error?.status || 0)
    if (status === 401 || status === 403 || status === 404) {
      stopPolling()
      return
    }
    consecutivePollErrors += 1
    if (consecutivePollErrors >= MAX_CONSECUTIVE_POLL_ERRORS) {
      pauseAutomaticPolling('连续 3 次刷新失败，自动刷新已暂停；提交仍会继续处理。')
      return
    }
    const baseDelay = Math.max(250, Number(props.pollInterval) || 2000)
    const retryDelay = Math.min(MAX_POLL_BACKOFF_MS, baseDelay * (2 ** consecutivePollErrors))
    schedulePoll(generation, targetTaskId, targetOperationGeneration, false, retryDelay)
  } finally {
    if (pollController === controller) pollController = null
  }
}

async function recoverCurrentSubmission() {
  const generation = contextGeneration
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  if (!Number.isSafeInteger(targetTaskId) || targetTaskId <= 0) return
  if (!props.canQuery) {
    recoveryResolved.value = !props.hasUncommittedSubmission
    if (props.hasUncommittedSubmission) {
      requestError.value = versionErrorState({
        httpStatus: 403,
        message: '任务有正在处理的版本提交，但当前账号无法查看进度'
      }, '无法确认当前版本提交')
    }
    return
  }
  const controller = new AbortController()
  recoveryController = controller
  recovering.value = true
  recoveryResolved.value = false
  requestError.value = null
  try {
    const response = await getCurrentTaskVersionSubmission(targetTaskId, { signal: controller.signal })
    if (recoveryController !== controller || !stillCurrent(generation, targetTaskId, targetOperationGeneration)) return
    recoveryResolved.value = true
    if (!response.data) return
    updateSubmission(response.data)
    phase.value = response.data.submissionStatus
    if (!isSubmissionTerminal(response.data.submissionStatus)) {
      resetPollingBudget()
      schedulePoll(generation, targetTaskId, targetOperationGeneration)
    }
  } catch (error) {
    if (!isCanceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      recoveryResolved.value = false
      requestError.value = versionErrorState(error, '未能恢复当前版本提交')
    }
  } finally {
    if (recoveryController === controller) {
      recoveryController = null
      recovering.value = false
    }
  }
}

function discardUploadedFile() {
  if (!canDiscardUploadedFile.value || isBusy.value) return
  resetComposer()
}

function chooseFiles(uploadFile, uploadFiles) {
  validationMessage.value = ''
  requestError.value = null
  const file = uploadFile?.raw || null
  if (!file) return
  const extension = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
  if (!acceptedExtensions.value.includes(extension)) {
    validationMessage.value = `当前任务只接受 ${acceptedExtensions.value.map(item => item.toUpperCase()).join('/')} 文件`
    fileUploadRef.value?.handleRemove?.(uploadFile)
    return
  }
  if (file.size > MAX_VERSION_FILE_SIZE) {
    validationMessage.value = '版本文件不能超过 100 MiB'
    fileUploadRef.value?.handleRemove?.(uploadFile)
    return
  }
  if (file.size <= 0) {
    validationMessage.value = '版本文件不能为空'
    fileUploadRef.value?.handleRemove?.(uploadFile)
    return
  }
  const rawFiles = (uploadFiles || []).filter(item => item.raw)
  if (rawFiles.length > MAX_VERSION_CANDIDATES) {
    validationMessage.value = `每轮最多提交 ${MAX_VERSION_CANDIDATES} 个候选文件`
    fileUploadRef.value?.handleRemove?.(uploadFile)
    return
  }
  if (rawFiles.reduce((total, item) => total + Number(item.raw.size || 0), 0) > MAX_VERSION_BATCH_SIZE) {
    validationMessage.value = '候选文件总大小不能超过 500 MiB'
    fileUploadRef.value?.handleRemove?.(uploadFile)
    return
  }
  workflowController?.abort()
  fileGeneration += 1
  const existingByKey = new Map(selectedCandidates.value.map(item => [item.clientFileKey, item]))
  const reusedCandidates = new Set()
  const nextCandidates = rawFiles.map(item => {
    const clientFileKey = String(item.uid)
    const existing = existingByKey.get(clientFileKey)
    const reused = existing?.file === item.raw
    if (reused) reusedCandidates.add(existing)
    return {
      clientFileKey,
      file: item.raw,
      uploadFile: item,
      candidateNote: existing?.candidateNote || '',
      previewUrl: reused ? existing.previewUrl : createCandidatePreviewUrl(item.raw),
      previewError: reused ? existing.previewError : false
    }
  })
  selectedCandidates.value
    .filter(candidate => !reusedCandidates.has(candidate))
    .forEach(revokeCandidatePreview)
  selectedCandidates.value = nextCandidates
  submissionFormRef.value?.clearValidate('candidates')
  uploadResults.value = {}
  uploadProgress.value = 0
  phase.value = 'idle'
  idempotency.reset()
}

function removeCandidate(clientFileKey) {
  if (composerLocked.value) return
  const candidate = selectedCandidates.value.find(item => item.clientFileKey === clientFileKey)
  const uploadFile = candidate?.uploadFile
  if (uploadFile) fileUploadRef.value?.handleRemove?.(uploadFile)
  revokeCandidatePreview(candidate)
  selectedCandidates.value = selectedCandidates.value.filter(item => item.clientFileKey !== clientFileKey)
  fileGeneration += 1
  uploadResults.value = {}
  idempotency.reset()
  submissionFormRef.value?.validateField('candidates').catch(() => {})
}

function handleCandidateExceed() {
  validationMessage.value = `每轮最多提交 ${MAX_VERSION_CANDIDATES} 个候选文件`
}

function validateSelectedCandidates(_rule, candidates, callback) {
  if (!Array.isArray(candidates) || !candidates.length) return callback(new Error('请至少选择一个候选文件'))
  if (candidates.length > MAX_VERSION_CANDIDATES) {
    return callback(new Error(`每轮最多提交 ${MAX_VERSION_CANDIDATES} 个候选文件`))
  }
  if (candidates.reduce((total, item) => total + Number(item.file?.size || 0), 0) > MAX_VERSION_BATCH_SIZE) {
    return callback(new Error('候选文件总大小不能超过 500 MiB'))
  }
  for (const candidate of candidates) {
    const file = candidate.file
    const extension = file?.name?.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
    if (!acceptedExtensions.value.includes(extension)) {
      return callback(new Error(`当前任务只接受 ${acceptedExtensions.value.map(item => item.toUpperCase()).join('/')} 文件`))
    }
    if (file.size > MAX_VERSION_FILE_SIZE) return callback(new Error('单个候选文件不能超过 100 MiB'))
    if (file.size <= 0) return callback(new Error('候选文件不能为空'))
  }
  callback()
}

function validateChangelog(_rule, value, callback) {
  const normalized = String(value || '').trim()
  if (!normalized) return callback(new Error('请填写本轮修改说明'))
  if (normalized.length > 5000) return callback(new Error('本轮修改说明不能超过 5000 个字符'))
  if (Array.from(normalized).some(character => character !== ' ' && /[\p{C}\p{Z}]/u.test(character))) {
    return callback(new Error('修改说明不能换行或包含不可见字符'))
  }
  callback()
}

function issueUnhandledReasonRules(issueId) {
  return [{
    validator: (_rule, value, callback) => {
      if (issueHandlingStates.value[issueId] !== 'unhandled') return callback()
      const normalized = String(value || '').trim()
      if (!normalized) return callback(new Error('请说明该问题本轮未处理的原因'))
      if (normalized.length > 5000) return callback(new Error('未处理说明不能超过 5000 个字符'))
      callback()
    },
    trigger: ['blur', 'change']
  }]
}

function changeIssueHandling(issueId, handlingState) {
  if (handlingState !== 'handled') return
  issueUnhandledReasons.value[issueId] = ''
  submissionFormRef.value?.clearValidate(`issueUnhandledReasons.${issueId}`)
}

async function submitVersion() {
  if (isBusy.value || hasActiveSubmission.value) return
  validationMessage.value = ''
  requestError.value = null
  pollError.value = null
  if (!canSubmit.value) {
    validationMessage.value = `当前任务状态或账号权限不允许${submissionCopy.value.title}`
    return
  }
  formValidating.value = true
  let valid = false
  try {
    await submissionFormRef.value?.validate((result, invalidFields) => {
      valid = result
      if (!result) {
        validationMessage.value = Object.values(invalidFields || {}).flat()[0]?.message || '请检查版本提交表单'
      }
    })
    if (!valid) return
    if (props.taskStatus === 'revision' && !props.openIssues.length) {
      validationMessage.value = '退回修改任务缺少待处理问题，请刷新任务'
      return
    }
  } catch (error) {
    validationMessage.value = error.message
    return
  } finally {
    formValidating.value = false
  }
  const normalizedChangelog = changelog.value.trim()

  const generation = contextGeneration
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const targetCandidates = selectedCandidates.value.map(item => ({ ...item }))
  const targetFileGeneration = fileGeneration
  const controller = new AbortController()
  workflowController?.abort()
  workflowController = controller
  let failureTitle = '提交前检查未通过'

  try {
    if (!openIssueSnapshotHash.value) {
      phase.value = 'preflighting'
      const preflightPayload = {
        candidates: targetCandidates.map((item, index) => ({
          clientFileKey: item.clientFileKey,
          fileName: item.file.name,
          fileSize: item.file.size,
          sortOrder: index,
          candidateNote: String(item.candidateNote || '').trim() || null
        })),
        changelog: normalizedChangelog,
        issueResponses: issueResponses.value
      }
      const preflightResponse = await preflightVersionSubmission(
        targetTaskId,
        preflightPayload,
        { signal: controller.signal }
      )
      if (
        workflowController !== controller ||
        !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
        fileGeneration !== targetFileGeneration
      ) return
      if (!canSubmit.value) {
        const permissionError = new Error('提交权限或任务状态已发生变化，文件尚未上传')
        permissionError.httpStatus = 403
        throw permissionError
      }
      const checkedCandidates = preflightResponse?.data?.candidates || []
      if (
        preflightResponse?.data?.ready !== true ||
        Number(preflightResponse.data.taskId) !== targetTaskId ||
        preflightResponse.data.taskKind !== props.taskKind ||
        checkedCandidates.length !== targetCandidates.length ||
        checkedCandidates.some((item, index) => (
          item.clientFileKey !== targetCandidates[index].clientFileKey ||
          item.fileExtension !== targetCandidates[index].file.name.split('.').pop().toLowerCase()
        )) ||
        !preflightResponse.data.allowedActions?.includes('version.add')
      ) {
        throw new Error('提交检查结果与当前任务不一致，文件尚未上传')
      }
      openIssueSnapshotHash.value = preflightResponse.data.openIssueSnapshotHash

    }

    failureTitle = '候选文件上传失败'
    phase.value = 'uploading'
    for (let index = 0; index < targetCandidates.length; index += 1) {
      const candidate = targetCandidates[index]
      if (uploadResults.value[candidate.clientFileKey]) continue
      const response = await uploadProtectedVersionFile(candidate.file, {
        signal: controller.signal,
        onUploadProgress: event => {
          if (event.total && stillCurrent(generation, targetTaskId, targetOperationGeneration) && fileGeneration === targetFileGeneration) {
            const currentPercent = Math.min(100, (event.loaded * 100) / event.total)
            uploadProgress.value = Math.round(((index * 100) + currentPercent) / targetCandidates.length)
          }
        }
      })
      if (
        workflowController !== controller ||
        !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
        fileGeneration !== targetFileGeneration
      ) return
      if (!response?.fileId || response?.accessType !== 'private') {
        throw new Error(`候选 ${index + 1} 上传结果异常，版本尚未提交`)
      }
      uploadResults.value = {
        ...uploadResults.value,
        [candidate.clientFileKey]: {
          fileId: response.fileId,
          originalFilename: response.originalFilename || candidate.file.name,
          downloadUrl: response.downloadUrl
        }
      }
      uploadProgress.value = Math.round(((index + 1) * 100) / targetCandidates.length)
    }
    phase.value = 'uploaded'

    const payload = {
      candidates: targetCandidates.map((item, index) => ({
        clientFileKey: item.clientFileKey,
        fileId: uploadResults.value[item.clientFileKey].fileId,
        sortOrder: index,
        candidateNote: String(item.candidateNote || '').trim() || null
      })),
      changelog: normalizedChangelog,
      openIssueSnapshotHash: openIssueSnapshotHash.value,
      issueResponses: issueResponses.value
    }
    phase.value = 'submitting'
    failureTitle = '版本提交创建失败'
    const response = await createVersionSubmission(
      targetTaskId,
      payload,
      idempotency.forPayload(payload),
      { signal: controller.signal }
    )
    if (
      workflowController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      fileGeneration !== targetFileGeneration
    ) return
    applyAcceptedSubmission(response.data, generation, targetTaskId, targetOperationGeneration)
  } catch (error) {
    if (!isCanceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration) && fileGeneration === targetFileGeneration) {
      requestError.value = versionErrorState(error, failureTitle)
      phase.value = Object.keys(uploadResults.value).length ? 'submission_failed' : 'idle'
    }
  } finally {
    if (workflowController === controller) workflowController = null
  }
}

async function retryFailedSubmission() {
  if (!props.canRetry || submission.value?.submissionStatus !== 'failed' || isBusy.value) return
  const generation = contextGeneration
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const targetSubmissionId = Number(submission.value.submissionId)
  const controller = new AbortController()
  workflowController?.abort()
  workflowController = controller
  requestError.value = null
  pollError.value = null
  phase.value = 'retrying'
  try {
    const response = await retryVersionSubmission(targetSubmissionId, { signal: controller.signal })
    if (
      workflowController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      Number(submission.value?.submissionId) !== targetSubmissionId
    ) return
    applyAcceptedSubmission(response.data, generation, targetTaskId, targetOperationGeneration)
  } catch (error) {
    if (!isCanceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      requestError.value = versionErrorState(error, '版本提交重试失败')
      phase.value = 'failed'
    }
  } finally {
    if (workflowController === controller) workflowController = null
  }
}

function refreshSubmissionStatus() {
  if (!submission.value?.submissionId || isBusy.value) return
  const generation = contextGeneration
  stopPolling()
  resetPollingBudget()
  pollError.value = null
  void pollSubmission(generation, Number(props.taskId), Number(props.operationGeneration))
}

watch(
  () => [props.taskId, props.operationGeneration, props.canQuery, props.hasUncommittedSubmission],
  () => {
    resetContext()
    recoverCurrentSubmission()
  },
  { immediate: true }
)

watch(
  () => props.openIssues.map(issue => issue.issueId),
  issueIds => {
    const currentStates = issueHandlingStates.value
    const currentReasons = issueUnhandledReasons.value
    issueHandlingStates.value = Object.fromEntries(issueIds.map(issueId => [issueId, currentStates[issueId] || 'handled']))
    issueUnhandledReasons.value = Object.fromEntries(issueIds.map(issueId => [issueId, currentReasons[issueId] || '']))
  }
)

onBeforeUnmount(() => {
  disposed = true
  contextGeneration += 1
  abortRequests()
  releaseCandidatePreviews()
})
</script>

<template>
  <el-card class="version-submission-panel" shadow="never">
    <div class="panel-heading">
      <div>
        <p class="sg-eyebrow">{{ submissionCopy.eyebrow }}</p>
        <h3>{{ submissionCopy.title }}</h3>
        <p>{{ submissionCopy.description }}</p>
      </div>
      <el-button v-if="submission && canQuery" :icon="Refresh" :disabled="isBusy" @click="refreshSubmissionStatus">刷新状态</el-button>
      <el-button v-else-if="!recoveryResolved && !recovering && canQuery" :icon="Refresh" @click="recoverCurrentSubmission">重新检查</el-button>
    </div>

    <el-skeleton v-if="recovering" class="recovering-state" :rows="4" animated />

    <VersionSubmissionStatus v-else-if="submission" :submission="submission" :poll-error="pollError" />

    <el-alert
      v-if="requestError || validationMessage"
      class="version-error"
      :title="requestError?.title || '请检查提交内容'"
      :description="requestError?.message || validationMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <el-alert v-if="submission?.submissionStatus === 'failed'" class="submission-actions" title="必须恢复当前失败提交" type="error" :closable="false" show-icon>
      <span class="submission-actions__description">当前失败提交仍需处理，不能另选文件创建新版本。</span>
      <el-button type="primary" :loading="phase === 'retrying'" :disabled="!canRetry" @click="retryFailedSubmission">
        {{ canRetry ? '重试当前提交' : '当前账号没有重试权限' }}
      </el-button>
    </el-alert>

    <el-form v-else-if="!submission" ref="submissionFormRef" :model="submissionFormModel" :rules="submissionFormRules" class="submission-form" label-position="top" label-width="auto" :aria-label="submissionCopy.title">
      <el-form-item class="submission-file-field" prop="candidates">
        <el-upload ref="fileUploadRef" class="file-picker" :class="{ 'has-file': selectedCandidates.length }" action="#" drag multiple :limit="MAX_VERSION_CANDIDATES" :auto-upload="false" :show-file-list="false" :accept="acceptAttribute" :disabled="composerLocked || !canSubmit" :on-change="chooseFiles" :on-exceed="handleCandidateExceed">
          <el-icon><UploadFilled /></el-icon>
          <span>
            <strong>{{ selectedCandidates.length ? `已选择 ${selectedCandidates.length} 个候选文件` : submissionCopy.uploadPrompt }}</strong>
            <small>可拖拽或多选；仅接受 {{ acceptedExtensions.map(item => item.toUpperCase()).join('/') }}，单个最大 100 MiB，整批最大 500 MiB</small>
          </span>
          <b>{{ selectedCandidates.length ? '继续添加' : '拖拽或选择' }}</b>
        </el-upload>
        <div v-if="selectedCandidates.length" class="candidate-upload-list">
          <el-card v-for="(candidate, index) in selectedCandidates" :key="candidate.clientFileKey" shadow="never" class="candidate-upload-item">
            <div class="candidate-upload-item__content">
              <div class="candidate-local-preview">
                <el-image
                  v-if="taskKind === 'asset_image' && candidate.previewUrl && !candidate.previewError"
                  class="candidate-local-preview__media"
                  :src="candidate.previewUrl"
                  :preview-src-list="[candidate.previewUrl]"
                  :alt="`候选 ${String(index + 1).padStart(2, '0')} ${candidate.file.name} 本地预览`"
                  fit="contain"
                  hide-on-click-modal
                  preview-teleported
                  @error="markCandidatePreviewError(candidate)"
                />
                <video
                  v-else-if="taskKind !== 'asset_image' && candidate.previewUrl && !candidate.previewError"
                  class="candidate-local-preview__media"
                  :src="candidate.previewUrl"
                  :aria-label="`候选 ${String(index + 1).padStart(2, '0')} ${candidate.file.name} 本地预览`"
                  controls
                  playsinline
                  preload="metadata"
                  @error="markCandidatePreviewError(candidate)"
                >
                  当前浏览器不支持视频预览。
                </video>
                <div v-else class="candidate-local-preview__fallback" role="status">
                  <strong>无法本地预览</strong>
                  <span>浏览器可能不支持该文件编码，仍可继续提交。</span>
                </div>
                <span class="candidate-local-preview__label">本地预览</span>
              </div>
              <div class="candidate-upload-item__details">
                <div class="candidate-upload-item__main">
                  <el-tag size="small" effect="plain" round>候选 {{ String(index + 1).padStart(2, '0') }}</el-tag>
                  <div><strong>{{ candidate.file.name }}</strong><small>{{ (candidate.file.size / 1024 / 1024).toFixed(2) }} MiB</small></div>
                  <el-button text type="danger" :disabled="composerLocked" @click="removeCandidate(candidate.clientFileKey)">移除</el-button>
                </div>
                <el-input v-model="candidate.candidateNote" maxlength="500" show-word-limit clearable :disabled="composerLocked" placeholder="可选：说明这个候选的特点或希望审核人关注的地方" />
              </div>
            </div>
          </el-card>
        </div>
      </el-form-item>

      <el-card v-if="taskStatus === 'revision'" class="issue-response-panel" shadow="never">
        <header class="issue-response-panel__heading">
          <div>
            <p class="sg-eyebrow">REVIEW ISSUES</p>
            <h4>逐条说明修改情况</h4>
          </div>
          <el-tag type="warning" effect="plain" size="small" round>{{ openIssues.length }} 条待处理</el-tag>
        </header>
        <p class="issue-response-help">请确认每条审核意见是否已在本轮处理；未处理时说明原因。说明会随 {{ nextVersionNumber }} 永久保存。</p>
        <div v-if="openIssues.length" class="issue-response-list">
          <article v-for="(issue, index) in openIssues" :key="issue.issueId">
            <div class="issue-response-title">
              <strong>问题 {{ index + 1 }}</strong>
              <span>待处理归属 {{ issue.pendingVersionNumber || issue.originVersionNumber }}<template v-if="issue.pendingVersionNumber && issue.pendingVersionNumber !== issue.originVersionNumber"> · 来源 {{ issue.originVersionNumber }}</template></span>
            </div>
            <p>{{ issue.content || `包含 ${issue.annotations?.items?.length || 0} 个画面标注` }}</p>
            <el-button class="issue-source-link" link type="primary" @click="emit('focus-issue', issue)">
              查看来源版本{{ issue.annotations?.items?.length ? `与 ${issue.annotations.items.length} 处画面标注` : '' }}
            </el-button>
            <el-form-item class="field-label issue-handling-field" label="本轮处理情况" :prop="`issueHandlingStates.${issue.issueId}`" :rules="issueHandlingStateRules">
              <el-radio-group
                v-model="issueHandlingStates[issue.issueId]"
                size="small"
                :disabled="composerLocked || !canSubmit"
                :aria-label="`问题 ${index + 1} 本轮处理情况`"
                @change="changeIssueHandling(issue.issueId, $event)"
              >
                <el-radio-button label="已处理" value="handled" />
                <el-radio-button label="未处理" value="unhandled" />
              </el-radio-group>
            </el-form-item>
            <el-form-item
              v-if="issueHandlingStates[issue.issueId] === 'unhandled'"
              class="field-label issue-unhandled-reason"
              label="未处理说明"
              :prop="`issueUnhandledReasons.${issue.issueId}`"
              :rules="issueUnhandledReasonRules(issue.issueId)"
            >
              <el-input
                v-model="issueUnhandledReasons[issue.issueId]"
                type="textarea"
                maxlength="5000"
                :rows="3"
                show-word-limit
                :disabled="composerLocked || !canSubmit"
                placeholder="请说明本轮为什么暂不处理，以及后续计划。"
              />
            </el-form-item>
          </article>
        </div>
        <el-empty v-else class="issue-response-empty" :image-size="48" description="当前没有可处理问题，请刷新任务后再提交" />
      </el-card>

      <el-form-item class="field-label changelog-field" :label="submissionCopy.changelogLabel" prop="changelog">
        <el-input v-model="changelog" type="textarea" maxlength="5000" :rows="4" show-word-limit :disabled="composerLocked || !canSubmit" :placeholder="changelogPlaceholder" />
      </el-form-item>

      <el-progress v-if="phase === 'uploading'" class="upload-progress" :percentage="uploadProgress" :stroke-width="8" :status="uploadProgress >= 100 ? 'success' : undefined" aria-label="版本文件上传进度" />
      <el-alert v-if="uploadedOnly" class="uploaded-boundary" title="文件已上传，正式版本尚未生成" type="warning" :closable="false" show-icon>
        <span class="submission-actions__description">候选文件与说明已锁定，请直接重试提交；若服务端拒绝当前批次，可放弃后重新选择。</span>
        <el-button v-if="canDiscardUploadedFile" text @click="discardUploadedFile">放弃已上传批次并重新选择</el-button>
      </el-alert>

      <footer>
        <p v-if="!canSubmit">当前账号或任务状态不允许{{ submissionCopy.title }}；请确认任务已进入可交付状态。</p>
        <p v-else>{{ submissionCopy.footerHint }}</p>
        <el-button
          type="primary"
          :loading="isBusy"
          :disabled="!canSubmit"
          @click="submitVersion"
        >
          {{ uploadedOnly ? submissionCopy.retryLabel : `${submissionCopy.submitLabel}${selectedCandidates.length ? `（${selectedCandidates.length} 个候选）` : ''}` }}
        </el-button>
      </footer>
    </el-form>
  </el-card>
</template>

<style scoped lang="scss">
.version-submission-panel { --el-card-bg-color: var(--sg-surface); --el-card-border-color: var(--sg-border); border-radius: var(--sg-radius-lg); }
.version-submission-panel:deep(.el-card__body) { padding: 24px; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.panel-heading h3 { margin: 3px 0 7px; font-size: 20px; }
.panel-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.recovering-state { min-height: 150px; padding: 28px; margin-top: 20px; background: rgba(255, 255, 255, 0.025); border: 1px dashed var(--sg-border); border-radius: var(--sg-radius-md); }
.submission-status { margin-top: 20px; }
.version-error { margin-top: 16px; }
.version-error code { display: inline-block; margin-top: 6px; color: inherit; font-size: 10px; }
.submission-actions { margin-top: 16px; }
.submission-actions__description { display: block; }
.submission-actions .el-button { margin-top: 10px; }
.submission-form { display: grid; margin-top: 20px; gap: 16px; }
.submission-form :deep(.el-form-item) { margin-bottom: 0; }
.submission-file-field :deep(.el-form-item__content) { display: block; }
.issue-response-panel { --el-card-bg-color: rgba(255, 182, 87, 0.045); --el-card-border-color: rgba(255, 182, 87, 0.2); border-radius: 12px; }
.issue-response-panel:deep(.el-card__body) { display: grid; padding: 17px; gap: 12px; }
.issue-response-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.issue-response-panel h4 { margin: 3px 0 0; font-size: 16px; }
.issue-response-help { margin: 0; color: var(--sg-text-muted); font-size: 11px; line-height: 1.6; }
.issue-response-list { display: grid; gap: 10px; }
.issue-response-list article { display: grid; gap: 9px; padding: 13px; background: rgba(0, 0, 0, 0.14); border: 1px solid var(--sg-border); border-radius: 10px; }
.issue-response-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.issue-response-title strong { font-size: 12px; }
.issue-response-title span { color: var(--sg-text-muted); font-size: 9px; }
.issue-response-list article > p { margin: 0; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.65; white-space: pre-wrap; }
.issue-source-link { justify-self: start; height: auto; padding: 0; font-size: 10px; }
.issue-handling-field :deep(.el-radio-group) { display: flex; width: 100%; }
.issue-handling-field :deep(.el-radio-button) { flex: 1 1 0; }
.issue-handling-field :deep(.el-radio-button__inner) { width: 100%; }
.issue-response-empty { padding: 18px; border: 1px dashed rgba(244, 92, 92, 0.3); border-radius: 9px; }
.file-picker { width: 100%; }
.file-picker :deep(.el-upload) { display: block; width: 100%; }
.file-picker :deep(.el-upload-dragger) { position: relative; display: grid; box-sizing: border-box; width: 100%; min-height: 84px; padding: 18px; cursor: pointer; text-align: left; background: rgba(255, 255, 255, 0.025); border: 1px dashed var(--sg-border-strong); border-radius: var(--sg-radius-md); grid-template-columns: auto minmax(0, 1fr) auto; gap: 14px; align-items: center; }
.file-picker:hover :deep(.el-upload-dragger),
.file-picker.has-file :deep(.el-upload-dragger),
.file-picker :deep(.el-upload-dragger.is-dragover) { background: rgba(255, 182, 87, 0.055); border-color: rgba(255, 182, 87, 0.5); }
.candidate-upload-list { display: grid; width: 100%; margin-top: 12px; gap: 10px; }
.candidate-upload-item:deep(.el-card__body) { padding: 12px; }
.candidate-upload-item__content { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 14px; align-items: start; }
.candidate-upload-item__details { display: grid; min-width: 0; gap: 12px; }
.candidate-upload-item__main { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: center; }
.candidate-upload-item__main div { display: grid; min-width: 0; gap: 2px; }
.candidate-upload-item__main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.candidate-upload-item__main small { color: var(--sg-text-muted); }
.candidate-local-preview { position: relative; aspect-ratio: 16 / 9; min-height: 124px; overflow: hidden; background: #050608; border: 1px solid var(--sg-border); border-radius: 9px; }
.candidate-local-preview__media { display: block; width: 100%; height: 100%; object-fit: contain; }
.candidate-local-preview:deep(.el-image) { width: 100%; height: 100%; }
.candidate-local-preview__fallback { display: grid; height: 100%; min-height: 124px; padding: 18px; box-sizing: border-box; color: var(--sg-text-muted); text-align: center; place-content: center; gap: 6px; }
.candidate-local-preview__fallback strong { color: var(--sg-text-secondary); font-size: 12px; }
.candidate-local-preview__fallback span { max-width: 230px; font-size: 10px; line-height: 1.5; }
.candidate-local-preview__label { position: absolute; top: 8px; left: 8px; padding: 3px 7px; color: #fff; font-size: 9px; line-height: 1; background: rgba(0, 0, 0, 0.62); border-radius: 999px; pointer-events: none; }
.file-picker .el-icon { color: var(--sg-accent); font-size: 25px; }
.file-picker strong,
.file-picker small { display: block; }
.file-picker small { margin-top: 6px; color: var(--sg-text-muted); font-size: 11px; }
.file-picker b { color: var(--sg-accent); font-size: 12px; }
.field-label { display: grid; gap: 8px; }
.field-label :deep(.el-form-item__label) { color: var(--sg-text-secondary); font-size: 12px; }
.upload-progress { width: 100%; }
.uploaded-boundary { font-size: 11px; line-height: 1.6; }
.uploaded-boundary .el-button { margin-top: 8px; }
.submission-form footer { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.submission-form footer p { max-width: 650px; margin: 0; color: var(--sg-text-muted); font-size: 11px; line-height: 1.6; }

@media (max-width: 720px) {
  .panel-heading,
  .submission-actions,
  .submission-form footer { align-items: stretch; flex-direction: column; }
  .candidate-upload-item__content { grid-template-columns: 1fr; }
  .submission-form footer .el-button { width: 100%; }
}
</style>
