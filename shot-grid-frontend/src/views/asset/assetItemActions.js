const permissions = {
  'assetItem.edit': 'shotgrid:asset:edit',
  'assetItem.delete': 'shotgrid:asset:archive',
  'task.assign': 'shotgrid:task:assign',
  'task.start': 'shotgrid:task:start'
}

// 排期以分项任务为单位，不借用父资产开工动作；后端仍复核管理范围和任务版本。
export function canScheduleAssetItem(asset, item, permitted) {
  return Boolean(permitted && asset && item && asset.lifecycleStatus === 'active' && item.lifecycleStatus === 'active' &&
    Number(item.projectId) === Number(asset.projectId) && Number(item.assetId) === Number(asset.assetId) &&
    Number(item.task?.taskId) > 0 && ['not_started', 'preparing', 'in_progress', 'pending_review', 'revision'].includes(item.task?.taskStatus))
}

export function assetItemScheduleLabel(item) {
  return item?.task?.expectedStartTime && item?.task?.expectedEndTime ? '调整排期' : '设置排期'
}

// 与镜头操作列一致：突出当前阶段的下一步，前期开工前将编辑放到辅助操作区。
export function prioritizeAssetItemActions(actions, item) {
  const items = [...actions]
  const hasSchedule = Boolean(item?.task?.expectedStartTime && item?.task?.expectedEndTime)
  const status = item?.assetStatus || item?.task?.taskStatus || 'unassigned'
  const primaryKey = item?.task?.taskStatus === 'pending_review' && items.some(action => action.key === 'review') ? 'review'
    : ['in_progress', 'revision'].includes(item?.task?.taskStatus) && items.some(action => action.key === 'work') ? 'work'
    : !item?.task && !String(item?.productionItem || '').trim() ? 'edit'
    : !item?.task ? 'assign'
    : !hasSchedule && items.some(action => action.key === 'schedule') ? 'schedule' : 'start'
  const primaryIndex = items.findIndex(action => action.key === primaryKey)
  if (primaryIndex > 0) items.unshift(...items.splice(primaryIndex, 1))
  if (primaryKey !== 'edit' && ['unassigned', 'pending_schedule', 'not_started'].includes(status)) {
    const editIndex = items.findIndex(action => action.key === 'edit')
    if (editIndex >= 0) {
      const [edit] = items.splice(editIndex, 1)
      const deleteIndex = items.findIndex(action => action.key === 'delete')
      items.splice(deleteIndex >= 0 ? deleteIndex : items.length, 0, edit)
    }
  }
  return items
}

export function canAssetItemAction(asset, item, action, hasPermission) {
  if (!asset || !item || !permissions[action] || !hasPermission(permissions[action])) return false
  if (Number(item.projectId) !== Number(asset.projectId) || Number(item.assetId) !== Number(asset.assetId)) return false
  if (asset.lifecycleStatus !== 'active' || item.lifecycleStatus !== 'active') return false
  if (!item.allowedActions?.includes(action)) return false
  return action !== 'task.start' || Boolean(asset.allowedActions?.includes('task.start') &&
    hasPermission('shotgrid:asset:query') && item.task?.taskStatus === 'not_started' &&
    item.task?.expectedStartTime && item.task?.expectedEndTime)
}
