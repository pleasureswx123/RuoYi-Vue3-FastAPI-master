const STATUS_META = Object.freeze({
  preparing: { label: '准备中', tone: 'warning' },
  active: { label: '进行中', tone: 'success' },
  completed: { label: '已完成', tone: 'info' },
  archived: { label: '已归档', tone: 'muted' }
})

const STORAGE_META = Object.freeze({
  initializing: { label: '目录初始化中', tone: 'warning' },
  ready: { label: '存储就绪', tone: 'success' },
  failed: { label: '存储异常', tone: 'danger' },
  migrating: { label: '存储迁移中', tone: 'warning' }
})

const PHASE_LABELS = Object.freeze({
  planning: '策划',
  asset_production: '资产制作',
  shot_production: '镜头制作',
  review: '审核',
  delivery: '交付',
  completed: '已完成'
})

const OPERATION_STATUS_LABELS = Object.freeze({
  pending: '等待执行',
  processing: '执行中',
  succeeded: '已成功',
  retry_wait: '等待重试',
  failed: '执行失败',
  compensation_pending: '等待补偿',
  compensated: '已补偿',
  compensation_failed: '补偿失败'
})

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || '未知', tone: 'muted' }
}

export function storageMeta(status) {
  return STORAGE_META[status] || { label: status || '未知', tone: 'muted' }
}

export function phaseLabel(phase) {
  return PHASE_LABELS[phase] || phase || '未设置'
}

export function operationStatusLabel(status) {
  return OPERATION_STATUS_LABELS[status] || status || '未知'
}

export function canRetryDynamicStorageOperation(operation) {
  return Boolean(
    operation &&
      operation.operationStatus === 'failed' &&
      operation.aggregateType !== 'project' &&
      operation.operationType !== 'initialize_project'
  )
}

export function projectErrorState(error, fallback = '项目数据加载失败') {
  const status = Number(error?.httpStatus || error?.status || 0)
  const state = {
    status,
    errorKey: error?.errorKey || null,
    title: fallback,
    message: error?.message || fallback,
    retryable: status === 0 || status >= 500 || status === 409
  }
  if (status === 403) {
    return { ...state, title: '没有项目访问权限', retryable: false }
  }
  if (status === 404) {
    return { ...state, title: '项目或资源不存在', retryable: false }
  }
  if (status === 409) {
    return { ...state, title: '数据状态已发生变化', retryable: true }
  }
  if (status === 422) {
    return { ...state, title: '提交内容未通过校验', retryable: false }
  }
  if (status >= 500 || status === 0) {
    return { ...state, title: '业务服务暂不可用', retryable: true }
  }
  return state
}

export function formatDuration(milliseconds) {
  const value = Number(milliseconds)
  if (!Number.isFinite(value) || value <= 0) {
    return '未设置'
  }
  const totalMinutes = Math.round(value / 60000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分钟`
}

export function formatDateTime(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString('zh-CN', { hour12: false })
}
