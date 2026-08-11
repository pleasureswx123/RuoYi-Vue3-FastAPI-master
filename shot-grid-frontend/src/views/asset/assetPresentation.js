const TYPE_META = {
  Character: { label: '角色', tone: 'character' },
  Environment: { label: '场景', tone: 'environment' },
  Prop: { label: '道具', tone: 'prop' }
}

const STATUS_META = {
  unassigned: { label: '未分配', tone: 'muted' },
  not_started: { label: '未开始', tone: 'muted' },
  in_progress: { label: '制作中', tone: 'warning' },
  reviewing: { label: '待审核', tone: 'info' },
  revision: { label: '修改中', tone: 'danger' },
  completed: { label: '已完成', tone: 'success' }
}

const DIRECTORY_META = {
  pending: { label: '目录待创建', tone: 'warning' },
  ready: { label: '目录就绪', tone: 'success' },
  failed: { label: '目录失败', tone: 'danger' }
}

export function assetTypeMeta(assetType) {
  return TYPE_META[assetType] || { label: assetType || '未知类型', tone: 'muted' }
}

export function assetStatusMeta(status) {
  return STATUS_META[status] || { label: status || '未知状态', tone: 'muted' }
}

export function assetDirectoryStatusMeta(status) {
  return DIRECTORY_META[status] || { label: status || '未知目录状态', tone: 'muted' }
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
  if (status === 410) return { ...context, title: '导入预检已过期', retryable: false }
  if (status === 413) return { ...context, title: 'Excel 文件过大', retryable: false }
  if (status === 422 || status === 400) return { ...context, title: '资产数据校验失败', retryable: false }
  return { ...context, title: fallbackTitle, retryable: status >= 500 || status === 0 }
}

export function groupAssetPreviewRows(rows = []) {
  return rows.reduce((groups, row) => {
    const key = row.sheetName || '未知 Sheet'
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
  const name = member.nickName || member.userName || `用户 ${member.userId}`
  return member.producerCode ? `${name}（${member.producerCode}）` : name
}

export function assetAssigneeSummary(assigneeUserIds, members = []) {
  const ids = [...new Set((Array.isArray(assigneeUserIds) ? assigneeUserIds : [])
    .map(Number)
    .filter(id => Number.isSafeInteger(id) && id > 0))]
  if (!ids.length) return '未分配'
  const memberById = new Map((Array.isArray(members) ? members : [])
    .filter(member => Number.isSafeInteger(Number(member?.userId)) && Number(member.userId) > 0)
    .map(member => [Number(member.userId), member]))
  const visible = ids.flatMap(id => memberById.has(id) ? [memberLabel(memberById.get(id))] : [])
  const unavailableCount = ids.length - visible.length
  if (unavailableCount > 0) visible.push(`另 ${unavailableCount} 人不可分配`)
  return visible.join('、')
}
