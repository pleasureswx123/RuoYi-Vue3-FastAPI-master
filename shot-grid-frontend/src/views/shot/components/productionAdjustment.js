export const adjustmentFields = [
  { key: 'expectedRange', label: '计划起止时间', type: 'range', permission: 'shotgrid:task:schedule' },
  { key: 'assigneeUserId', label: '制作人', type: 'member', permission: 'shotgrid:task:assign' },
  { key: 'priority', label: '优先级', type: 'priority' },
  { key: 'description', label: '制作内容', type: 'text' },
  { key: 'durationMs', label: '镜头时长（毫秒）', type: 'number' },
  ...[['shotSize', '景别', 500], ['cameraPosition', '机位', 500], ['cameraMovement', '镜头运动', 500], ['focalLength', '焦段', 500], ['dialogue', '台词 / 对白'], ['soundEffect', '音效'], ['colorReference', '色调参考'], ['remark', '备注', 2000]].map(([key, label, max]) => ({ key, label, max, type: 'text' })),
  { key: 'referenceFileIds', label: '参考内容（可选）', type: 'references', permission: 'shotgrid:shot:edit' }
].map(field => ({ ...field, permission: field.permission || (field.key === 'priority' ? 'shotgrid:task:edit' : 'shotgrid:shot:edit') }))

export function adjustmentValues(detail) {
  return Object.fromEntries(adjustmentFields.map(field => [field.key,
    field.key === 'referenceFileIds' ? [] : field.key === 'expectedRange' ? [detail.task.expectedStartTime, detail.task.expectedEndTime].filter(Boolean).map(value => value.replace(' ', 'T'))
      : field.key === 'assigneeUserId' ? detail.task.assignee.userId
        : field.key === 'priority' ? detail.task.priority : detail[field.key] ?? (field.type === 'number' ? 0 : '')
  ]))
}
export function adjustmentPatch(keys, values) {
  const patch = {}
  for (const key of keys) {
    if (key === 'expectedRange') [patch.expectedStartTime, patch.expectedEndTime] = values[key]
    else patch[key] = typeof values[key] === 'string' ? values[key].trim() || null : values[key]
  }
  return patch
}
