<script setup>
import { computed, ref, watch } from 'vue'

import { useSessionStore } from '@/store/modules/session'
import VersionHistoryPanel from './VersionHistoryPanel.vue'
import VersionSubmissionPanel from './VersionSubmissionPanel.vue'

const props = defineProps({
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
const submissionVisible = computed(() => props.taskStatus !== 'pending_review' || (
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
}

function focusIssue(issue) {
  historyPanel.value?.focusIssue(issue)
}

function focusSubmission() {
  if (!canAdd.value || !submissionVisible.value || props.hasUncommittedSubmission) return
  const element = submissionSection.value?.$el
  element?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  element?.setAttribute('tabindex', '-1')
  element?.focus({ preventScroll: true })
}
</script>

<template>
  <div class="version-workspace">
    <VersionHistoryPanel
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
        <el-button type="primary" @click="focusSubmission">{{ taskStatus === 'pending_review' ? '追加本轮文件' : '提交新版本' }}</el-button>
      </template>
    </VersionHistoryPanel>
    <VersionSubmissionPanel
      v-if="shouldShowSubmission"
      v-show="submissionVisible"
      ref="submissionSection"
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
</style>
