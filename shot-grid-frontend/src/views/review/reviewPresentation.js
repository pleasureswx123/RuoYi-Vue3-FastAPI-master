const REVIEW_STATUS = Object.freeze({
  draft: { label: '草稿', tone: 'neutral' },
  active: { label: '待审核', tone: 'warning' },
  completed: { label: '已完成', tone: 'success' },
  archived: { label: '已归档', tone: 'neutral' }
})

const REVIEW_MODE = Object.freeze({
  auto_single: { label: '自动单版', tone: 'info' },
  manual_batch: { label: '人工批量', tone: 'primary' }
})

const MEDIA_DERIVATION_STATUS = Object.freeze({
  pending: { label: '媒体排队中', tone: 'warning' },
  processing: { label: '正在生成预览', tone: 'warning' },
  completed: { label: '预览已优化', tone: 'success' },
  failed: { label: '使用原始媒体', tone: 'danger' }
})

const ACTION_META = Object.freeze({
  approve: { label: '确认通过', tone: 'success' },
  reject: { label: '退回修改', tone: 'danger' },
  defer: { label: '稍后决定', tone: 'warning' }
})

export function reviewStatusMeta(status) {
  return REVIEW_STATUS[status] || { label: status || '未知', tone: 'neutral' }
}

export function reviewModeMeta(mode) {
  return REVIEW_MODE[mode] || { label: mode || '未知模式', tone: 'neutral' }
}

export function mediaDerivationStatusMeta(status) {
  return MEDIA_DERIVATION_STATUS[status] || null
}

export function reviewActionMeta(action) {
  return ACTION_META[action] || { label: action || '未知动作', tone: 'neutral' }
}

export function formatReviewDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  }).format(date)
}

export function formatMediaTime(value) {
  const milliseconds = Number(value)
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return null
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function reviewErrorState(error, fallbackTitle = '审核操作失败') {
  const status = Number(error?.httpStatus || error?.status || 0)
  const title = status === 403
    ? '没有审核访问权限'
    : status === 404
      ? '审核资源不存在'
      : status === 409
        ? '审核状态已发生变化'
        : status >= 500
          ? '审核服务暂不可用'
          : fallbackTitle
  return {
    title,
    message: error?.message || '请求未完成，请稍后重试。',
    retryable: status !== 403 && status !== 404,
    status: status || null,
    errorKey: error?.errorKey || null
  }
}
