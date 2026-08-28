const permissions = {
  'assetItem.edit': 'shotgrid:asset:edit',
  'assetItem.delete': 'shotgrid:asset:archive',
  'task.assign': 'shotgrid:task:assign',
  'task.start': 'shotgrid:task:start'
}

export function canAssetItemAction(asset, item, action, hasPermission) {
  if (!asset || !item || !permissions[action] || !hasPermission(permissions[action])) return false
  if (Number(item.projectId) !== Number(asset.projectId) || Number(item.assetId) !== Number(asset.assetId)) return false
  if (asset.lifecycleStatus !== 'active' || item.lifecycleStatus !== 'active') return false
  if (!item.allowedActions?.includes(action)) return false
  return action !== 'task.start' || Boolean(asset.allowedActions?.includes('task.start'))
}
