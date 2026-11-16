export function approvedVersion(row) {
  return row?.approvedVersion || row?.finalVersion || (['final'].includes(row?.latestVersion?.versionStatus || row?.latestVersion?.status) ? row.latestVersion : null)
}

export function finalVersionNumber(version) {
  return version?.versionNumber || (version?.versionNo ? `V${String(version.versionNo).padStart(3, '0')}` : '')
}

export function finalBadge(row) {
  const version = approvedVersion(row)
  if (!version) return null
  const current = (row.status || row.assetStatus || row.task?.taskStatus) === 'completed' && (version.versionStatus || version.status) === 'final'
  if (!current) return { type: 'warning', label: `${(row.status || row.assetStatus || row.task?.taskStatus) === 'revision' ? '修改中 · ' : ''}上次定稿 ${finalVersionNumber(version)}` }
  const status = version.deliveryStatus
  return { type: status === 'published' ? 'success' : 'warning', label: `${status === 'published' ? '定稿' : status === 'failed' ? '定稿整理失败' : ['pending', 'publishing'].includes(status) ? '定稿整理中' : '已通过 · 归档待核对'} ${finalVersionNumber(version)}` }
}

export function assetFinalSummary(asset) {
  return `已定稿 ${Number(asset?.finalizedItemCount || 0)}/${Number(asset?.itemCount || 0)}`
}
