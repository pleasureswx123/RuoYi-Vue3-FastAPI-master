<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, ElRadioButton, ElRadioGroup } from 'element-plus'

import { useSessionStore } from '@/store/modules/session'
import VersionHistoryPanel from './VersionHistoryPanel.vue'
import VersionSubmissionPanel from './VersionSubmissionPanel.vue'

const props = defineProps({
  compact: { type: Boolean, default: false },
  taskId: { type: Number, required: true },
  taskKind: { type: String, required: true },
  taskStatus: { type: String, required: true },
  versionCount: { type: Number, default: 0 },
  latestVersionNo: { type: Number, default: 0 },
  productionDescription: { type: String, default: '' },
  openIssues: { type: Array, default: () => [] },
  allowedActions: { type: Array, default: () => [] },
  hasUncommittedSubmission: { type: Boolean, default: false },
  operationGeneration: { type: Number, default: 0 }
})
const emit = defineEmits(['committed', 'submission-change', 'version-selected'])

const sessionStore = useSessionStore()
const historyRefreshKey = ref(0)
const historyPanel = ref(null)
const submissionSection = ref(null)
const selectedVersion = ref(null)
const activeSection = ref('history')
const feedbackRequested = ref(false)
const submissionVisible = computed(() => props.taskKind === 'shot_video' || props.hasUncommittedSubmission || props.taskStatus !== 'pending_review' || (
  Number(props.latestVersionNo) > 0 &&
  Number(selectedVersion.value?.versionNo) === Number(props.latestVersionNo) &&
  selectedVersion.value?.versionStatus === 'pending_review'
))
watch(() => [props.taskId, props.operationGeneration, props.latestVersionNo], () => { selectedVersion.value = null })
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canUseSubmissionPanel = computed(() => ['in_progress', 'revision', 'pending_review'].includes(props.taskStatus))
const canAdd = computed(() => (
  canUseSubmissionPanel.value &&
  props.allowedActions.includes('version.add') &&
  hasPermission('shotgrid:version:add')
))
const canQuery = computed(() => hasPermission('shotgrid:version:query'))
const canRetry = computed(() => wildcard.value || sessionStore.permissions.includes('shotgrid:version:retry'))
const canList = computed(() => hasPermission('shotgrid:version:list'))
const canDownload = computed(() => hasPermission('shotgrid:file:download'))
const canListNotes = computed(() => hasPermission('shotgrid:note:list'))
const shouldShowSubmission = computed(() => (
  canUseSubmissionPanel.value &&
  (canAdd.value || props.hasUncommittedSubmission)
))

function contextMatches(context) {
  return Number(context?.taskId) === Number(props.taskId) &&
    Number(context?.operationGeneration) === Number(props.operationGeneration)
}

function handleCommitted(status, context) {
  if (!contextMatches(context)) return
  historyRefreshKey.value += 1
  emit('committed', status, context)
}

function handleSubmissionChange(status, context) {
  if (!contextMatches(context)) return
  emit('submission-change', status, context)
}

function handleVersionSelected(version, context) {
  if (!contextMatches(context)) return
  selectedVersion.value = version
  emit('version-selected', version, context)
  if (feedbackRequested.value) focusFeedback()
}
function focusFeedback() {
  activeSection.value = 'history'
  feedbackRequested.value = !selectedVersion.value
  if (feedbackRequested.value) return
  if (props.openIssues[0]) historyPanel.value?.focusIssue(props.openIssues[0])
  else historyPanel.value?.focusFeedback?.()
}

function focusIssue(issue) {
  activeSection.value = 'history'
  historyPanel.value?.focusIssue(issue)
}

async function focusSubmission() {
  if (!shouldShowSubmission.value || !submissionVisible.value) return
  feedbackRequested.value = false
  activeSection.value = 'submit'
  await nextTick()
  const element = submissionSection.value?.$el
  element?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  element?.setAttribute('tabindex', '-1')
  element?.focus({ preventScroll: true })
}
async function canLeave() {
  if (submissionSection.value?.isBusy) {
    ElMessage.warning('正在上传或提交，请等待当前操作结束。')
    return false
  }
  if (!submissionSection.value?.hasUnsavedChanges) return true
  try {
    await ElMessageBox.confirm('已选文件或填写的说明尚未提交，离开会丢失本次草稿。', '离开当前任务？', {
      confirmButtonText: '放弃草稿并离开', cancelButtonText: '继续编辑', type: 'warning'
    })
    return true
  } catch { return false }
}
watch(() => props.hasUncommittedSubmission, value => { if (value) activeSection.value = 'submit' }, { immediate: true })
const dirty = computed(() => Boolean(submissionSection.value?.isBusy || submissionSection.value?.hasUnsavedChanges))
defineExpose({ focusSubmission, focusFeedback, canLeave, dirty })
</script>

<template>
  <div class="version-workspace" :class="{ 'version-workspace--compact': compact }">
    <el-radio-group v-if="compact" v-model="activeSection" aria-label="成果与反馈">
      <el-radio-button value="history">版本与反馈</el-radio-button>
      <el-radio-button v-if="shouldShowSubmission && submissionVisible" value="submit">{{ hasUncommittedSubmission ? '提交进度' : taskStatus === 'pending_review' ? taskKind === 'shot_video' ? '继续提交新版本' : '追加本轮文件' : '提交成果' }}</el-radio-button>
    </el-radio-group>
    <VersionHistoryPanel
      v-show="!compact || activeSection === 'history'"
      ref="historyPanel"
      :task-id="taskId"
      :operation-generation="operationGeneration"
      :refresh-key="historyRefreshKey"
      :can-list="canList"
      :can-query="canQuery"
      :can-download="canDownload"
      :can-list-notes="canListNotes"
      @version-selected="handleVersionSelected"
      @selection-loading="selectedVersion = null"
    >
      <template v-if="canAdd && submissionVisible && !hasUncommittedSubmission" #actions>
        <el-button type="primary" @click="focusSubmission">{{ taskStatus === 'pending_review' ? taskKind === 'shot_video' ? '继续提交新版本' : '追加本轮文件' : '提交新版本' }}</el-button>
      </template>
    </VersionHistoryPanel>
    <VersionSubmissionPanel
      v-if="shouldShowSubmission"
      v-show="submissionVisible && (!compact || activeSection === 'submit')"
      ref="submissionSection"
      :simple="compact"
      :task-id="taskId"
      :task-kind="taskKind"
      :task-status="taskStatus"
      :version-count="versionCount"
      :latest-version-no="latestVersionNo"
      :production-description="productionDescription"
      :open-issues="openIssues"
      :allowed-actions="allowedActions"
      :has-uncommitted-submission="hasUncommittedSubmission"
      :has-add-permission="canAdd"
      :can-query="canQuery"
      :can-retry="canRetry"
      :operation-generation="operationGeneration"
      @committed="handleCommitted"
      @submission-change="handleSubmissionChange"
      @focus-issue="focusIssue"
    />
  </div>
</template>

<style scoped>
.version-workspace {
  display: grid;
  gap: 18px;
}
.version-workspace--compact :deep(.feedback-layout) { grid-template-columns: minmax(0, 1fr); }
.version-workspace--compact :deep(.feedback-file-nav) { grid-column: 1; grid-row: auto; display: flex; flex-wrap: wrap; gap: 6px; }
.version-workspace--compact :deep(.feedback-file) { width: 110px; }
.version-workspace--compact :deep(.feedback-media), .version-workspace--compact :deep(.feedback-list-panel) { grid-column: 1; grid-row: auto; min-width: 0; }
.version-workspace--compact :deep(.el-affix--fixed) { position: static !important; width: auto !important; }
.version-workspace--compact :deep(.panel-heading) { flex-wrap: wrap; }
</style>
