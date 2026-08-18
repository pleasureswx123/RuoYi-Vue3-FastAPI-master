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

const PROJECT_ROLE_META = Object.freeze({
  director: Object.freeze({ label: '项目管理人', type: 'primary' }),
  creator: Object.freeze({ label: '制作人员', type: 'info' })
})

const OPERATION_STATUS_META = Object.freeze({
  pending: { label: '等待执行', tone: 'warning' },
  processing: { label: '执行中', tone: 'primary' },
  succeeded: { label: '已成功', tone: 'success' },
  retry_wait: { label: '等待重试', tone: 'warning' },
  failed: { label: '执行失败', tone: 'danger' },
  compensation_pending: { label: '等待补偿', tone: 'warning' },
  compensated: { label: '已补偿', tone: 'success' },
  compensation_failed: { label: '补偿失败', tone: 'danger' }
})

const OPERATION_TYPE_META = Object.freeze({
  initialize_project: Object.freeze({ label: '项目初始化', tone: 'primary' }),
  ensure_episode_directory: Object.freeze({ label: '集目录', tone: 'info' }),
  ensure_shot_directory: Object.freeze({ label: '镜头目录', tone: 'info' }),
  ensure_asset_directory: Object.freeze({ label: '资产目录', tone: 'success' }),
  reconcile_directory: Object.freeze({ label: '目录对账', tone: 'warning' })
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

export function projectRoleMeta(role) {
  if (Object.hasOwn(PROJECT_ROLE_META, role)) return PROJECT_ROLE_META[role]
  if (role === null || role === undefined || role === '') {
    return { label: '跨项目管理员', type: 'info' }
  }
  return { label: '未知项目角色', type: 'info' }
}

export function operationStatusLabel(status) {
  return operationStatusMeta(status).label
}

export function operationStatusMeta(status) {
  return OPERATION_STATUS_META[status] || { label: status || '未知', tone: 'muted' }
}

export function operationTypeMeta(type) {
  return OPERATION_TYPE_META[type] || { label: type || '未知类型', tone: 'muted' }
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
