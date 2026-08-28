const FALLBACK_META = Object.freeze({ label: '未知', tone: 'neutral' })

const TASK_STATUS = Object.freeze({
  not_started: Object.freeze({ label: '待开工', tone: 'neutral' }),
  preparing: Object.freeze({ label: '目录准备中', tone: 'warning' }),
  in_progress: Object.freeze({ label: '制作中', tone: 'info' }),
  pending_review: Object.freeze({ label: '待审核', tone: 'warning' }),
  revision: Object.freeze({ label: '待修订', tone: 'danger' }),
  completed: Object.freeze({ label: '已完成', tone: 'success' })
})

const TASK_KIND = Object.freeze({
  shot_video: Object.freeze({ label: '镜头视频', shortLabel: '镜头', tone: 'info' }),
  asset_image: Object.freeze({ label: '资产图片', shortLabel: '资产', tone: 'purple' })
})

const TASK_PRIORITY = Object.freeze({
  low: Object.freeze({ label: '低', tone: 'neutral' }),
  normal: Object.freeze({ label: '普通', tone: 'info' }),
  high: Object.freeze({ label: '高', tone: 'warning' }),
  urgent: Object.freeze({ label: '紧急', tone: 'danger' })
})

const VERSION_STATUS = Object.freeze({
  pending_review: Object.freeze({ label: '待审核', tone: 'warning' }),
  rejected: Object.freeze({ label: '已退回', tone: 'danger' }),
  final: Object.freeze({ label: '最终版本', tone: 'success' })
})

export function taskStatusMeta(value) {
  return TASK_STATUS[value] || FALLBACK_META
}

export function taskKindMeta(value) {
  return TASK_KIND[value] || FALLBACK_META
}

export function taskPriorityMeta(value) {
  return TASK_PRIORITY[value] || FALLBACK_META
}

export function taskVersionStatusMeta(value) {
  return VERSION_STATUS[value] || FALLBACK_META
}

export function formatTaskDateTime(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(parsed)
}

export function taskDueState(value, now = new Date()) {
  if (!value) return Object.freeze({ label: '未设置截止日期', tone: 'neutral', overdue: false })
  const due = new Date(`${value}T23:59:59`)
  if (Number.isNaN(due.getTime())) return Object.freeze({ label: String(value), tone: 'neutral', overdue: false })
  const overdue = due.getTime() < now.getTime()
  return Object.freeze({ label: overdue ? `${value} · 已逾期` : value, tone: overdue ? 'danger' : 'neutral', overdue })
}

export function taskAssigneeLabel(assignee) {
  if (!assignee) return '未分配'
  const name = assignee.userName || assignee.nickName || `用户 ${assignee.userId || '—'}`
  return name
}

export function taskErrorState(error, fallbackTitle = '任务加载失败') {
  const status = Number(error?.status || error?.httpStatus || 0)
  const base = {
    status,
    errorKey: error?.errorKey || '',
    message: error?.message || '请稍后重试',
    retryable: status !== 403 && status !== 404
  }
  if (status === 401) return { ...base, title: '登录状态已失效', retryable: false }
  if (status === 403) return { ...base, title: '没有任务访问权限', retryable: false }
  if (status === 404) return { ...base, title: '任务不存在', retryable: false }
  if (status === 409) return { ...base, title: '任务已发生变更', retryable: true }
  if (status >= 500 || status === 0) return { ...base, title: '任务暂时无法打开', retryable: true }
  return { ...base, title: fallbackTitle }
}
