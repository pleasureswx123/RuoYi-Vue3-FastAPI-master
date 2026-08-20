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

export const PROJECT_PHASE_OPTIONS = Object.freeze([
  Object.freeze({ value: 'planning', label: '制作规划' }),
  Object.freeze({ value: 'asset_production', label: '资产制作' }),
  Object.freeze({ value: 'shot_production', label: '镜头制作' }),
  Object.freeze({ value: 'review', label: '版本审核' }),
  Object.freeze({ value: 'delivery', label: '交付确认' }),
  Object.freeze({ value: 'completed', label: '项目完成' })
])

const PHASE_LABELS = Object.freeze(
  Object.fromEntries(PROJECT_PHASE_OPTIONS.map(option => [option.value, option.label]))
)

const PROJECT_ROLE_META = Object.freeze({
  director: Object.freeze({ label: '项目管理人', type: 'primary' }),
  creator: Object.freeze({ label: '制作人员', type: 'info' })
})

const SYSTEM_ROLE_KEY_BY_PROJECT_ROLE = Object.freeze({
  director: 'shotgrid_admin',
  creator: 'shotgrid_creator'
})

export const REQUIRED_PROJECT_ROLES = Object.freeze(['director', 'creator'])

const OPERATION_STATUS_META = Object.freeze({
  pending: { label: '等待执行', tone: 'warning' },
  processing: { label: '执行中', tone: 'primary' },
  succeeded: { label: '已成功', tone: 'success' },
  retry_wait: { label: '等待重试', tone: 'warning' },
  failed: { label: '执行失败', tone: 'danger' },
  compensation_pending: { label: '等待恢复', tone: 'warning' },
  compensated: { label: '已恢复', tone: 'success' },
  compensation_failed: { label: '恢复失败', tone: 'danger' }
})

const OPERATION_TYPE_META = Object.freeze({
  initialize_project: Object.freeze({ label: '项目初始化', tone: 'primary' }),
  ensure_episode_directory: Object.freeze({ label: '集目录', tone: 'info' }),
  ensure_shot_directory: Object.freeze({ label: '镜头目录', tone: 'info' }),
  ensure_asset_directory: Object.freeze({ label: '资产目录', tone: 'success' }),
  reconcile_directory: Object.freeze({ label: '目录核验', tone: 'warning' })
})

export function statusMeta(status) {
  return STATUS_META[status] || { label: '未知项目状态', tone: 'muted' }
}

export function storageMeta(status) {
  return STORAGE_META[status] || { label: '未知存储状态', tone: 'muted' }
}

export function phaseLabel(phase) {
  if (!phase) return '未设置'
  return PHASE_LABELS[phase] || '未知阶段'
}

export function projectRoleMeta(role) {
  if (Object.hasOwn(PROJECT_ROLE_META, role)) return PROJECT_ROLE_META[role]
  if (role === null || role === undefined || role === '') {
    return { label: '跨项目管理员', type: 'info' }
  }
  return { label: '未知项目角色', type: 'info' }
}

export function normalizeProjectRoleOptions(options) {
  if (!Array.isArray(options)) return []
  const seen = new Set()
  return options.flatMap(option => {
    const projectRole = option?.projectRole
    const systemRoleId = Number(option?.systemRoleId)
    const systemRoleKey = String(option?.systemRoleKey || '').trim()
    const systemRoleName = String(option?.systemRoleName || '').trim()
    if (
      !Object.hasOwn(PROJECT_ROLE_META, projectRole) ||
      seen.has(projectRole) ||
      !Number.isSafeInteger(systemRoleId) ||
      systemRoleId <= 0 ||
      !systemRoleKey ||
      systemRoleKey !== SYSTEM_ROLE_KEY_BY_PROJECT_ROLE[projectRole] ||
      !systemRoleName
    ) return []
    seen.add(projectRole)
    return [{
      projectRole,
      projectRoleLabel: PROJECT_ROLE_META[projectRole].label,
      systemRoleId,
      systemRoleKey,
      systemRoleName
    }]
  })
}

export function projectRoleOptionLabel(option) {
  const businessLabel = projectRoleMeta(option?.projectRole).label
  return businessLabel
}

export function operationStatusLabel(status) {
  return operationStatusMeta(status).label
}

export function operationStatusMeta(status) {
  return OPERATION_STATUS_META[status] || { label: '未知操作状态', tone: 'muted' }
}

export function operationTypeMeta(type) {
  return OPERATION_TYPE_META[type] || { label: '未知操作类型', tone: 'muted' }
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
  const errorKey = error?.errorKey || null
  const state = {
    status,
    errorKey,
    title: fallback,
    message: error?.message || fallback,
    retryable: status === 0 || status >= 500 || status === 409
  }
  if (['SG_PLATFORM_ROLE_MISSING', 'SG_PLATFORM_ROLE_DUPLICATE', 'SG_PLATFORM_ROLE_DISABLED', 'SG_PLATFORM_ROLE_UNSAFE'].includes(errorKey)) {
    return {
      ...state,
      title: '项目角色配置不可用',
      message: '项目角色尚未正确配置，请联系平台管理员调整后重试。',
      retryable: true
    }
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
    return { ...state, title: fallback, retryable: true }
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
