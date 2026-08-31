import { ref, shallowRef } from 'vue'

import { updateTaskSchedule } from '@/api/shot-grid/schedules'

function newIdempotencyKey(taskId) {
  const nonce = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `schedule:${taskId}:${nonce}`
}

function safeError(error) {
  return {
    httpStatus: error?.httpStatus ?? error?.status ?? null,
    errorKey: error?.errorKey || '',
    message: error?.message || '排期保存失败，请重试',
    details: error?.details && typeof error.details === 'object' ? error.details : null
  }
}

function conflictIds(error) {
  const ids = error?.details?.conflictTaskIds
  if (!Array.isArray(ids)) return []
  return [...new Set(ids.map(Number).filter(id => Number.isSafeInteger(id) && id > 0))].sort((a, b) => a - b)
}

export function useScheduleMutation(store, options = {}) {
  const visible = ref(false)
  const saving = ref(false)
  const activeTask = shallowRef(null)
  const draft = ref(null)
  const error = ref(null)
  const conflictTaskIds = ref([])
  const overlapAcknowledged = ref(false)
  let idempotencyKey = ''
  let disposed = false

  function open(task, rangeDraft = {}) {
    if (!task?.taskId || !task.allowedActions?.includes('schedule')) return false
    activeTask.value = task
    draft.value = {
      expectedStartTime: rangeDraft.expectedStartTime || task.currentStart || null,
      expectedEndTime: rangeDraft.expectedEndTime || task.currentEnd || null,
      operationSource: rangeDraft.operationSource || 'dialog',
      changeReason: rangeDraft.changeReason || ''
    }
    conflictTaskIds.value = []
    overlapAcknowledged.value = false
    error.value = null
    idempotencyKey = newIdempotencyKey(task.taskId)
    visible.value = true
    return true
  }

  function close() {
    if (saving.value) return
    visible.value = false
    activeTask.value = null
    draft.value = null
    conflictTaskIds.value = []
    overlapAcknowledged.value = false
    error.value = null
    idempotencyKey = ''
  }

  async function save(form) {
    if (saving.value || !visible.value || !activeTask.value || !draft.value || disposed) return null
    const task = activeTask.value
    const command = {
      lockVersion: task.lockVersion,
      expectedStartTime: form.expectedStartTime || draft.value.expectedStartTime,
      expectedEndTime: form.expectedEndTime || draft.value.expectedEndTime,
      operationSource: form.operationSource || draft.value.operationSource,
      changeReason: form.changeReason,
      overlapAcknowledged: Boolean(form.overlapAcknowledged),
      expectedConflictTaskIds: form.overlapAcknowledged ? [...conflictTaskIds.value] : []
    }
    saving.value = true
    error.value = null
    try {
      const response = await updateTaskSchedule(task.taskId, command, idempotencyKey)
      if (disposed) return null
      const saved = response?.data ?? response
      const index = store.tasks.findIndex(item => item.taskId === task.taskId)
      if (index >= 0 && saved?.taskId === task.taskId) store.tasks.splice(index, 1, saved)
      visible.value = false
      activeTask.value = null
      draft.value = null
      conflictTaskIds.value = []
      overlapAcknowledged.value = false
      await options.onSaved?.(saved)
      return saved
    } catch (caught) {
      if (disposed) return null
      error.value = safeError(caught)
      if (caught?.errorKey === 'SG_TASK_SCHEDULE_OVERLAP') {
        conflictTaskIds.value = conflictIds(caught)
        overlapAcknowledged.value = false
        return null
      }
      if (caught?.errorKey === 'SG_OPTIMISTIC_LOCK_CONFLICT') {
        await options.onRefresh?.()
        const refreshed = store.tasks.find(item => item.taskId === task.taskId)
        if (refreshed) activeTask.value = refreshed
        return null
      }
      if (caught?.errorKey === 'SG_TASK_SCHEDULE_READ_ONLY' || Number(caught?.httpStatus || caught?.status) === 403) {
        store.setEditMode(false)
        visible.value = false
      }
      return null
    } finally {
      saving.value = false
    }
  }

  function dispose() {
    disposed = true
    visible.value = false
  }

  return {
    visible,
    saving,
    activeTask,
    draft,
    error,
    conflictTaskIds,
    overlapAcknowledged,
    open,
    close,
    save,
    dispose
  }
}
