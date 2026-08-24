const STATUS_META = {
  unassigned: { label: '待分配', tone: 'warning' },
  not_started: { label: '未开始', tone: 'muted' },
  preparing: { label: '目录准备中', tone: 'info' },
  in_progress: { label: '制作中', tone: 'primary' },
  reviewing: { label: '待审核', tone: 'purple' },
  revision: { label: '修改中', tone: 'danger' },
  completed: { label: '已完成', tone: 'success' }
}

const DIRECTORY_META = {
  not_created: { label: '开始制作时创建', tone: 'muted' },
  pending: { label: '目录准备中', tone: 'info' },
  ready: { label: '目录已就绪', tone: 'info' },
  failed: { label: '目录处理异常', tone: 'danger' }
}

export function shotStatusMeta(status) {
  return STATUS_META[status] || { label: '未知镜头状态', tone: 'muted' }
}

export function shotStatusTagClass(status) {
  return `shot-status-tag--${Object.hasOwn(STATUS_META, status) ? status : 'unknown'}`
}

export function directoryStatusMeta(status) {
  return DIRECTORY_META[status] || { label: '未知目录状态', tone: 'muted' }
}

export function shotAssigneeName(assignee, members = []) {
  if (!assignee) return '未分配'
  const userId = Number(assignee.userId)
  const member = (Array.isArray(members) ? members : [])
    .find(item => Number(item?.userId) === userId)
  return String(member?.userName || assignee.userName || '').trim()
    || String(member?.nickName || assignee.nickName || '').trim()
    || `用户 ${assignee.userId}`
}

export function shotAssigneeOptionLabel(member) {
  if (!member) return '未分配'
  const userName = String(member.userName || '').trim()
  const nickName = String(member.nickName || '').trim()
  if (userName && nickName && userName !== nickName) return `${userName}（${nickName}）`
  return userName || nickName || `用户 ${member.userId}`
}

export function formatShotDuration(durationMs) {
  const value = Number(durationMs)
  if (!Number.isFinite(value) || value < 0) return '—'
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)} 秒`
}

export function secondsToDurationMs(value) {
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds < 0) throw new TypeError('镜头时长不能为负数')
  const rawDurationMs = seconds * 1000
  const durationMs = Math.round(rawDurationMs)
  if (!Number.isSafeInteger(durationMs) || Math.abs(rawDurationMs - durationMs) > 1e-6) {
    throw new TypeError('镜头时长最多精确到 1 毫秒，且数值不能过大')
  }
  return durationMs
}

export function formatShotDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

export function shotErrorState(error, fallbackTitle = '镜头数据加载失败') {
  const status = Number(error?.httpStatus || error?.status || error?.code || 500)
  const message = error?.message || '服务暂时不可用，请稍后重试。'
  const context = { status, message, errorKey: error?.errorKey || null, details: error?.details || null }
  if (status === 403) return { ...context, title: '没有镜头访问权限', retryable: false }
  if (status === 404) return { ...context, title: '镜头或项目不存在', retryable: false }
  if (status === 409) return { ...context, title: '镜头状态已发生变化', retryable: true }
  if (status === 410) return { ...context, title: '导入检查结果已过期', retryable: false }
  if (status === 413) return { ...context, title: 'Excel 文件过大', retryable: false }
  if (status === 422 || status === 400) return { ...context, title: '镜头信息有误', retryable: false }
  return { ...context, title: fallbackTitle, retryable: status >= 500 || status === 0 }
}

export function groupPreviewRows(rows = []) {
  return rows.reduce((groups, row) => {
    const key = row.sheetName || '未知工作表'
    if (!groups[key]) groups[key] = []
    groups[key].push(row)
    return groups
  }, {})
}

export function selectablePreviewRows(rows = []) {
  return rows
    .filter(row => row.canImport && row.rowNumber >= 2 && row.sheetName)
    .map(row => ({ sheetName: row.sheetName, rowNumber: row.rowNumber }))
}
