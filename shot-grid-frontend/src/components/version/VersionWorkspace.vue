<script setup>
import { computed, ref } from 'vue'

import { useSessionStore } from '@/store/modules/session'
import VersionHistoryPanel from './VersionHistoryPanel.vue'
import VersionSubmissionPanel from './VersionSubmissionPanel.vue'

const props = defineProps({
  taskId: { type: Number, required: true },
  taskKind: { type: String, required: true },
  taskStatus: { type: String, required: true },
  versionCount: { type: Number, default: 0 },
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
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canUseSubmissionPanel = computed(() => ['in_progress', 'revision'].includes(props.taskStatus))
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
  emit('version-selected', version, context)
}

function focusIssue(issue) {
  historyPanel.value?.focusIssue(issue)
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
    />
    <VersionSubmissionPanel
      v-if="shouldShowSubmission"
      :task-id="taskId"
      :task-kind="taskKind"
      :task-status="taskStatus"
      :version-count="versionCount"
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
