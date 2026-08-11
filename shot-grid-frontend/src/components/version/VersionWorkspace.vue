<script setup>
import { computed, ref } from 'vue'

import { useSessionStore } from '@/store/modules/session'
import VersionHistoryPanel from './VersionHistoryPanel.vue'
import VersionSubmissionPanel from './VersionSubmissionPanel.vue'

const props = defineProps({
  taskId: { type: Number, required: true },
  taskKind: { type: String, required: true },
  allowedActions: { type: Array, default: () => [] },
  hasUncommittedSubmission: { type: Boolean, default: false },
  operationGeneration: { type: Number, default: 0 }
})
const emit = defineEmits(['committed', 'submission-change', 'version-selected'])

const sessionStore = useSessionStore()
const historyRefreshKey = ref(0)
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canAdd = computed(() => props.allowedActions.includes('version.add') && hasPermission('shotgrid:version:add'))
const canQuery = computed(() => hasPermission('shotgrid:version:query'))
const canRetry = computed(() => wildcard.value || sessionStore.permissions.includes('shotgrid:version:retry'))
const canList = computed(() => hasPermission('shotgrid:version:list'))
const canDownload = computed(() => hasPermission('shotgrid:file:download'))

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
</script>

<template>
  <div class="version-workspace">
    <VersionSubmissionPanel
      :task-id="taskId"
      :task-kind="taskKind"
      :allowed-actions="allowedActions"
      :has-uncommitted-submission="hasUncommittedSubmission"
      :has-add-permission="canAdd"
      :can-query="canQuery"
      :can-retry="canRetry"
      :operation-generation="operationGeneration"
      @committed="handleCommitted"
      @submission-change="handleSubmissionChange"
    />
    <VersionHistoryPanel
      :task-id="taskId"
      :operation-generation="operationGeneration"
      :refresh-key="historyRefreshKey"
      :can-list="canList"
      :can-query="canQuery"
      :can-download="canDownload"
      @version-selected="handleVersionSelected"
    />
  </div>
</template>

<style scoped>
.version-workspace {
  display: grid;
  gap: 18px;
}
</style>
