import { taskKindMeta, taskPriorityMeta, taskStatusMeta } from '@/views/task/taskPresentation'

const DAY_MS = 24 * 60 * 60 * 1000

function timestamp(value) {
  if (!value) return null
  const result = new Date(value).getTime()
  return Number.isFinite(result) ? result : null
}

export function baselineVariance(task) {
  const currentStart = timestamp(task?.currentStart)
  const currentEnd = timestamp(task?.currentEnd)
  const baselineStart = timestamp(task?.baselineStart)
  const baselineEnd = timestamp(task?.baselineEnd)
  if ([currentStart, currentEnd, baselineStart, baselineEnd].some(value => value === null)) {
    return null
  }
  const startDays = Math.round((currentStart - baselineStart) / DAY_MS)
  const endDays = Math.round((currentEnd - baselineEnd) / DAY_MS)
  return { startDays, endDays, delayed: startDays > 0 || endDays > 0 }
}

export function scheduleReminder(task, serverTime = new Date()) {
  if (task?.taskStatus === 'completed') {
    return { state: 'completed', label: '已完成', tone: 'success' }
  }
  const end = timestamp(task?.currentEnd)
  const now = timestamp(serverTime)
  if (end === null || now === null) {
    return { state: 'unset', label: '未排期', tone: 'neutral' }
  }
  const remaining = end - now
  if (remaining <= 0) return { state: 'overdue', label: '已逾期', tone: 'danger' }
  if (remaining <= DAY_MS) return { state: 'warning', label: '临近结束', tone: 'warning' }
  return { state: 'normal', label: '正常', tone: 'success' }
}

export function scheduleTaskLabel(task) {
  const code = task?.target?.code?.trim()
  const name = task?.target?.name?.trim()
  if (code && name && code !== name) return `${code} · ${name}`
  return code || name || `任务 ${task?.taskId || '—'}`
}

export function scheduleTaskMeta(task) {
  return {
    status: taskStatusMeta(task?.taskStatus),
    kind: taskKindMeta(task?.taskKind),
    priority: taskPriorityMeta(task?.priority),
    label: scheduleTaskLabel(task)
  }
}

export function scheduleErrorState(error) {
  const errorKey = error?.errorKey || ''
  const base = {
    errorKey,
    message: error?.message || '请稍后重试',
    details: error?.details || null,
    retryable: true
  }
  if (errorKey === 'SG_TASK_SCHEDULE_OVERLAP') {
    return { ...base, title: '人员排期发生重叠', action: '查看冲突后再次确认' }
  }
  if (errorKey === 'SG_OPTIMISTIC_LOCK_CONFLICT') {
    return { ...base, title: '任务已被其他人修改', action: '刷新任务后重试' }
  }
  if (errorKey === 'SG_TASK_SCHEDULE_READ_ONLY') {
    return { ...base, title: '当前任务不可调整排期', action: '刷新权限和任务状态', retryable: false }
  }
  if (errorKey === 'SG_IDEMPOTENCY_CONFLICT') {
    return { ...base, title: '本次保存请求已失效', action: '关闭窗口后重新编辑' }
  }
  const status = Number(error?.httpStatus || error?.status || 0)
  if (status === 403) {
    return { ...base, title: '没有排期访问权限', action: '返回可访问项目', retryable: false }
  }
  if (status === 404) {
    return { ...base, title: '任务或项目不存在', action: '刷新项目数据', retryable: false }
  }
  return { ...base, title: '排期暂时不可用', action: '稍后重试' }
}
