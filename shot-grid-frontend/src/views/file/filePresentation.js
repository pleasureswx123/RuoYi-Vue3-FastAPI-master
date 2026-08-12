const ROLE_LABELS = Object.freeze({
  review_media: '审核文件',
  thumbnail: '缩略图',
  proxy_media: '代理文件',
  source_original: '原始生成文件',
  source_repaired: '修复后文件',
  first_frame: '首帧',
  last_frame: '尾帧',
  reference: '参考文件'
})

const VERSION_STATUS = Object.freeze({
  pending_review: { label: '待审核', tone: 'warning' },
  rejected: { label: '已退回', tone: 'danger' },
  final: { label: '最终版本', tone: 'success' }
})

export function fileRoleLabel(role) {
  return ROLE_LABELS[role] || role || '未分类'
}

export function fileVersionStatusMeta(status) {
  return VERSION_STATUS[status] || { label: status || '未知', tone: 'neutral' }
}

export function formatFileSize(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value < 0) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`
  return `${(value / 1024 ** 3).toFixed(1)} GiB`
}

export function formatFileDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
}

export function fileErrorState(error, fallback = '文件数据加载失败') {
  const status = Number(error?.httpStatus || error?.status || 0)
  return {
    status: status || null,
    title: status === 403 ? '没有文件访问权限' : status === 404 ? '文件资源不存在' : fallback,
    message: error?.message || '请求未完成，请稍后重试。',
    retryable: status !== 403 && status !== 404,
    errorKey: error?.errorKey || null
  }
}
