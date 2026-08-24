const TYPE_META = {
  Character: { label: '角色', tone: 'character' },
  Environment: { label: '场景', tone: 'environment' },
  Prop: { label: '道具', tone: 'prop' }
}

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
  pending: { label: '目录准备中', tone: 'info' },
  ready: { label: '目录已就绪', tone: 'info' },
  failed: { label: '目录处理异常', tone: 'danger' }
}

export function assetTypeMeta(assetType) {
  return TYPE_META[assetType] || { label: '未知资产类型', tone: 'muted' }
}

export function assetStatusMeta(status) {
  return STATUS_META[status] || { label: '未知资产状态', tone: 'muted' }
}

export function assetDirectoryStatusMeta(status) {
  return DIRECTORY_META[status] || { label: '未知目录状态', tone: 'muted' }
}

export function formatAssetDateTime(value) {
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

export function assetErrorState(error, fallbackTitle = '资产数据加载失败') {
  const status = Number(error?.httpStatus || error?.status || error?.code || 500)
  const message = error?.message || '服务暂时不可用，请稍后重试。'
  const context = { status, message, errorKey: error?.errorKey || null, details: error?.details || null }
  if (status === 403) return { ...context, title: '没有资产访问权限', retryable: false }
  if (status === 404) return { ...context, title: '资产或项目不存在', retryable: false }
  if (status === 409) return { ...context, title: '资产状态已发生变化', retryable: true }
  if (status === 410) return { ...context, title: '导入检查已过期', retryable: false }
  if (status === 413) return { ...context, title: 'Excel 文件过大', retryable: false }
  if (status === 422 || status === 400) return { ...context, title: '资产数据校验失败', retryable: false }
  return { ...context, title: fallbackTitle, retryable: status >= 500 || status === 0 }
}

export function groupAssetPreviewRows(rows = []) {
  return rows.reduce((groups, row) => {
    const key = row.sheetName || '未知工作表'
    if (!groups[key]) groups[key] = []
    groups[key].push(row)
    return groups
  }, {})
}

export function selectableAssetPreviewRows(rows = []) {
  return rows
    .filter(row => row.canImport && row.rowNumber >= 2 && row.sheetName)
    .map(row => ({ sheetName: row.sheetName, rowNumber: row.rowNumber }))
}

export function resolveAssetThumbnail(asset) {
  if (asset?.thumbnail?.url) return asset.thumbnail
  return null
}

export function memberLabel(member) {
  if (!member) return '未分配'
  const userName = String(member.userName || '').trim()
  const nickName = String(member.nickName || '').trim()
  if (userName && nickName && userName !== nickName) return `${userName}（${nickName}）`
  return userName || nickName || `用户 ${member.userId}`
}

export function memberUserName(member) {
  if (!member) return '未分配'
  return String(member.userName || '').trim()
    || String(member.nickName || '').trim()
    || `用户 ${member.userId}`
}

export function assetAssigneeSummary(assigneeUserIds, members = []) {
  const ids = [...new Set((Array.isArray(assigneeUserIds) ? assigneeUserIds : [])
    .map(Number)
    .filter(id => Number.isSafeInteger(id) && id > 0))]
  if (!ids.length) return '-'
  const memberById = new Map((Array.isArray(members) ? members : [])
    .filter(member => Number.isSafeInteger(Number(member?.userId)) && Number(member.userId) > 0)
    .map(member => [Number(member.userId), member]))
  const visible = ids.flatMap(id => memberById.has(id) ? [memberUserName(memberById.get(id))] : [])
  const unavailableCount = ids.length - visible.length
  if (unavailableCount > 0) visible.push(`另 ${unavailableCount} 人不可分配`)
  return visible.join('、')
}
export function assetStatusTagClass(status) {
  return `asset-status-tag--${Object.hasOwn(STATUS_META, status) ? status : 'unknown'}`
}
