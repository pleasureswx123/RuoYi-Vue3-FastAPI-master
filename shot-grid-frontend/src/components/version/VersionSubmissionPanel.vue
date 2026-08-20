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
const MAX_AUTOMATIC_POLL_ATTEMPTS = 30
const MAX_CONSECUTIVE_POLL_ERRORS = 3
const MAX_POLL_BACKOFF_MS = 30_000

const props = defineProps({
  taskId: { type: Number, required: true },
  taskKind: { type: String, required: true },
  taskStatus: { type: String, required: true },
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

const selectedFile = ref(null)
const changelog = ref('')
const aiParamsText = ref('')
const issueResponseTexts = ref({})
const submissionFormRef = ref(null)
const fileUploadRef = ref(null)
const formValidating = ref(false)
const activeComposerSections = ref([])
const openIssueSnapshotHash = ref('')
const uploadResult = ref(null)
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
const canSubmit = computed(() => (
  recoveryResolved.value &&
  props.allowedActions.includes('version.add') &&
  props.hasAddPermission
))
const issueResponses = computed(() => props.taskStatus === 'revision'
  ? props.openIssues.map(issue => ({
      issueId: Number(issue.issueId),
      responseText: String(issueResponseTexts.value[issue.issueId] || '').trim()
    }))
  : [])
const submissionFormModel = computed(() => ({
  selectedFile: selectedFile.value,
  changelog: changelog.value,
  aiParamsText: aiParamsText.value,
  issueResponseTexts: issueResponseTexts.value
}))
const submissionFormRules = {
  selectedFile: [{ validator: validateSelectedFile, trigger: 'change' }],
  changelog: [{ validator: validateChangelog, trigger: 'blur' }],
  aiParamsText: [{ validator: validateAiParams, trigger: 'blur' }]
}
const issueResponseRules = [
  { required: true, whitespace: true, message: '请填写该问题的本轮处理说明', trigger: ['blur', 'change'] },
  { max: 5000, message: '单条问题处理说明不能超过 5000 个字符', trigger: 'blur' }
]
const hasActiveSubmission = computed(() => Boolean(submission.value && submission.value.submissionStatus !== 'committed'))
const isBusy = computed(() => formValidating.value || recovering.value || ['preflighting', 'uploading', 'submitting', 'retrying'].includes(phase.value))
const uploadedOnly = computed(() => Boolean(uploadResult.value && !submission.value))
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

function resetComposer() {
  formValidating.value = false
  activeComposerSections.value = []
  selectedFile.value = null
  fileUploadRef.value?.clearFiles?.()
  changelog.value = ''
  aiParamsText.value = ''
  issueResponseTexts.value = Object.fromEntries(props.openIssues.map(issue => [issue.issueId, '']))
  openIssueSnapshotHash.value = ''
  uploadResult.value = null
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

function chooseFile(uploadFile) {
  validationMessage.value = ''
  requestError.value = null
  const file = uploadFile?.raw || uploadFile?.target?.files?.[0] || null
  if (!file) {
    selectedFile.value = null
    return
  }
  const extension = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
  if (!acceptedExtensions.value.includes(extension)) {
    validationMessage.value = `当前任务只接受 ${acceptedExtensions.value.map(item => item.toUpperCase()).join('/')} 文件`
    if (uploadFile?.target) uploadFile.target.value = ''
    fileUploadRef.value?.clearFiles?.()
    selectedFile.value = null
    return
  }
  if (file.size > MAX_VERSION_FILE_SIZE) {
    validationMessage.value = '版本文件不能超过 100 MiB'
    if (uploadFile?.target) uploadFile.target.value = ''
    fileUploadRef.value?.clearFiles?.()
    selectedFile.value = null
    return
  }
  if (file.size <= 0) {
    validationMessage.value = '版本文件不能为空'
    if (uploadFile?.target) uploadFile.target.value = ''
    fileUploadRef.value?.clearFiles?.()
    selectedFile.value = null
    return
  }
  workflowController?.abort()
  fileGeneration += 1
  selectedFile.value = file
  submissionFormRef.value?.clearValidate('selectedFile')
  uploadResult.value = null
  uploadProgress.value = 0
  phase.value = 'idle'
  idempotency.reset()
}

function parseAiParams() {
  const normalized = aiParamsText.value.trim()
  if (!normalized) return null
  let value
  try {
    value = JSON.parse(normalized)
  } catch {
    throw new TypeError('AI 参数必须是有效 JSON')
  }
  if ((typeof value !== 'object' || value === null) || new Blob([JSON.stringify(value)]).size > 64 * 1024) {
    throw new TypeError('AI 参数必须是对象或数组，且不能超过 64 KiB')
  }
  return value
}

function validateSelectedFile(_rule, file, callback) {
  if (!file) return callback(new Error('请先选择版本文件'))
  const extension = file.name?.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
  if (!acceptedExtensions.value.includes(extension)) {
    return callback(new Error(`当前任务只接受 ${acceptedExtensions.value.map(item => item.toUpperCase()).join('/')} 文件`))
  }
  if (file.size > MAX_VERSION_FILE_SIZE) return callback(new Error('版本文件不能超过 100 MiB'))
  if (file.size <= 0) return callback(new Error('版本文件不能为空'))
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

function validateAiParams(_rule, _value, callback) {
  try {
    parseAiParams()
    callback()
  } catch (error) {
    callback(new Error(error.message))
  }
}

async function submitVersion() {
  if (isBusy.value || hasActiveSubmission.value) return
  validationMessage.value = ''
  requestError.value = null
  pollError.value = null
  if (!canSubmit.value) {
    validationMessage.value = '当前任务状态或账号权限不允许提交新版本'
    return
  }
  formValidating.value = true
  let valid = false
  let aiParams
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
    aiParams = parseAiParams()
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
  const targetFile = selectedFile.value
  const targetFileGeneration = fileGeneration
  const controller = new AbortController()
  workflowController?.abort()
  workflowController = controller
  let failureTitle = '提交前检查未通过'

  try {
    if (!uploadResult.value) {
      phase.value = 'preflighting'
      const preflightPayload = {
        fileName: targetFile.name,
        fileSize: targetFile.size,
        changelog: normalizedChangelog,
        aiParams,
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
        fileGeneration !== targetFileGeneration ||
        selectedFile.value !== targetFile
      ) return
      if (!canSubmit.value) {
        const permissionError = new Error('提交权限或任务状态已发生变化，文件尚未上传')
        permissionError.httpStatus = 403
        throw permissionError
      }
      const declaredExtension = targetFile.name.split('.').pop().toLowerCase()
      if (
        preflightResponse?.data?.ready !== true ||
        Number(preflightResponse.data.taskId) !== targetTaskId ||
        preflightResponse.data.taskKind !== props.taskKind ||
        preflightResponse.data.fileExtension !== declaredExtension ||
        !preflightResponse.data.allowedActions?.includes('version.add')
      ) {
        throw new Error('提交检查结果与当前任务不一致，文件尚未上传')
      }
      openIssueSnapshotHash.value = preflightResponse.data.openIssueSnapshotHash

      failureTitle = '版本文件上传失败'
      phase.value = 'uploading'
      uploadProgress.value = 0
      const response = await uploadProtectedVersionFile(targetFile, {
        signal: controller.signal,
        onUploadProgress: event => {
          if (event.total && stillCurrent(generation, targetTaskId, targetOperationGeneration) && fileGeneration === targetFileGeneration) {
            uploadProgress.value = Math.min(100, Math.round((event.loaded * 100) / event.total))
          }
        }
      })
      if (
        workflowController !== controller ||
        !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
        fileGeneration !== targetFileGeneration ||
        selectedFile.value !== targetFile
      ) return
      if (!response?.fileId || response?.accessType !== 'private') {
        throw new Error('文件上传结果异常，版本尚未提交')
      }
      uploadResult.value = {
        fileId: response.fileId,
        originalFilename: response.originalFilename || targetFile.name,
        downloadUrl: response.downloadUrl
      }
      uploadProgress.value = 100
      phase.value = 'uploaded'
    }

    const payload = {
      fileId: uploadResult.value.fileId,
      changelog: normalizedChangelog,
      aiParams,
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
      phase.value = uploadResult.value ? 'submission_failed' : 'idle'
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
    const current = issueResponseTexts.value
    issueResponseTexts.value = Object.fromEntries(issueIds.map(issueId => [issueId, current[issueId] || '']))
  }
)

onBeforeUnmount(() => {
  disposed = true
  contextGeneration += 1
  abortRequests()
})
</script>

<template>
  <el-card class="version-submission-panel" shadow="never">
    <div class="panel-heading">
      <div>
        <p class="sg-eyebrow">UPLOAD &amp; PUBLISH</p>
        <h3>提交新版本</h3>
        <p>上传制作成果并生成不可覆盖的正式版本；完成后将自动进入审核。</p>
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

    <el-form v-else-if="!submission" ref="submissionFormRef" :model="submissionFormModel" :rules="submissionFormRules" class="submission-form" label-position="top" aria-label="提交新版本">
      <el-form-item class="submission-file-field" prop="selectedFile">
        <el-upload ref="fileUploadRef" class="file-picker" :class="{ 'has-file': selectedFile }" action="#" :auto-upload="false" :show-file-list="false" :accept="acceptAttribute" :disabled="composerLocked || !canSubmit" :on-change="chooseFile">
          <el-icon><UploadFilled /></el-icon>
          <span>
            <strong>{{ selectedFile?.name || '选择离线制作成果' }}</strong>
            <small>{{ selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MiB` : `仅接受 ${acceptedExtensions.map(item => item.toUpperCase()).join('/')}，最大 100 MiB` }}</small>
          </span>
          <b>{{ selectedFile ? '更换' : '选择文件' }}</b>
        </el-upload>
      </el-form-item>

      <el-card v-if="taskStatus === 'revision'" class="issue-response-panel" shadow="never">
        <header class="issue-response-panel__heading">
          <div>
            <p class="sg-eyebrow">REVIEW ISSUES</p>
            <h4>逐条说明本轮如何处理</h4>
          </div>
          <el-tag type="warning" effect="plain" size="small" round>{{ openIssues.length }} 条待处理</el-tag>
        </header>
        <p class="issue-response-help">每条说明会随新版本永久保存，审核人将在下一版逐条确认是否已修复。</p>
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
            <el-form-item class="field-label" label="本轮处理说明" :prop="`issueResponseTexts.${issue.issueId}`" :rules="issueResponseRules">
              <el-input
                v-model="issueResponseTexts[issue.issueId]"
                type="textarea"
                maxlength="5000"
                :rows="3"
                show-word-limit
                :disabled="composerLocked || !canSubmit"
                placeholder="说明具体改了什么、如何改，以及需要审核人重点确认的位置。"
              />
            </el-form-item>
          </article>
        </div>
        <el-empty v-else class="issue-response-empty" :image-size="48" description="当前没有可处理问题，请刷新任务后再提交" />
      </el-card>

      <el-form-item class="field-label" label="本轮修改说明" prop="changelog">
        <el-input v-model="changelog" type="textarea" maxlength="5000" :rows="4" show-word-limit :disabled="composerLocked || !canSubmit" placeholder="说明本版本完成内容、修改点或需要审核人关注的部分。" />
      </el-form-item>

      <el-collapse v-model="activeComposerSections" class="ai-params">
        <el-collapse-item title="AI 生成参数（可选 JSON）" name="ai-params">
          <el-form-item prop="aiParamsText"><el-input v-model="aiParamsText" type="textarea" :rows="4" :disabled="composerLocked || !canSubmit" placeholder='例如：{"model":"...","seed":42}' /></el-form-item>
        </el-collapse-item>
      </el-collapse>

      <el-progress v-if="phase === 'uploading'" class="upload-progress" :percentage="uploadProgress" :stroke-width="8" :status="uploadProgress >= 100 ? 'success' : undefined" aria-label="版本文件上传进度" />
      <el-alert v-if="uploadedOnly" class="uploaded-boundary" title="文件已上传，正式版本尚未生成" type="warning" :closable="false" show-icon>
        <span class="submission-actions__description">文件与说明已锁定，请直接重试提交；若放弃当前文件，可重新选择。</span>
        <el-button v-if="canDiscardUploadedFile" text @click="discardUploadedFile">放弃已上传文件并重新选择</el-button>
      </el-alert>

      <footer>
        <p v-if="!canSubmit">当前账号或任务状态不允许提交新版本；任务需处于制作中或退回修改。</p>
        <p v-else>提交后可在此查看文件保存、版本生成和审核准备进度。</p>
        <el-button
          type="primary"
          :loading="isBusy"
          :disabled="!canSubmit"
          @click="submitVersion"
        >
          {{ uploadResult ? '重试创建版本提交' : '上传并提交版本' }}
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
.issue-response-empty { padding: 18px; border: 1px dashed rgba(244, 92, 92, 0.3); border-radius: 9px; }
.file-picker { width: 100%; }
.file-picker :deep(.el-upload) { position: relative; display: grid; box-sizing: border-box; width: 100%; min-height: 84px; padding: 18px; cursor: pointer; background: rgba(255, 255, 255, 0.025); border: 1px dashed var(--sg-border-strong); border-radius: var(--sg-radius-md); grid-template-columns: auto minmax(0, 1fr) auto; gap: 14px; align-items: center; }
.file-picker:hover :deep(.el-upload),
.file-picker.has-file :deep(.el-upload) { border-color: rgba(255, 182, 87, 0.5); }
.file-picker .el-icon { color: var(--sg-accent); font-size: 25px; }
.file-picker strong,
.file-picker small { display: block; }
.file-picker small { margin-top: 6px; color: var(--sg-text-muted); font-size: 11px; }
.file-picker b { color: var(--sg-accent); font-size: 12px; }
.field-label { display: grid; gap: 8px; }
.field-label :deep(.el-form-item__label) { color: var(--sg-text-secondary); font-size: 12px; }
.ai-params { color: var(--sg-text-secondary); font-size: 12px; border-color: var(--sg-border); }
.ai-params:deep(.el-collapse-item__header),
.ai-params:deep(.el-collapse-item__wrap) { color: var(--sg-text-secondary); background: transparent; border-color: var(--sg-border); }
.ai-params:deep(.el-collapse-item__content) { padding-bottom: 12px; }
.ai-params :deep(.el-form-item) { margin-bottom: 0; }
.upload-progress { width: 100%; }
.uploaded-boundary { font-size: 11px; line-height: 1.6; }
.uploaded-boundary .el-button { margin-top: 8px; }
.submission-form footer { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.submission-form footer p { max-width: 650px; margin: 0; color: var(--sg-text-muted); font-size: 11px; line-height: 1.6; }

@media (max-width: 720px) {
  .panel-heading,
  .submission-actions,
  .submission-form footer { align-items: stretch; flex-direction: column; }
  .submission-form footer .el-button { width: 100%; }
}
</style>
