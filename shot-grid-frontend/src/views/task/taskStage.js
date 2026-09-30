// 仅派生展示阶段，不改写服务端任务状态或历史事件。
export function taskStage(value) {
  if (!value || typeof value !== 'object') return value
  const task = value.task || value
  const status = value.taskStatus || value.status || value.assetStatus || task.taskStatus
  const start = value.expectedStartTime || task.expectedStartTime || value.currentStart || value.start
  const end = value.expectedEndTime || task.expectedEndTime || value.currentEnd || value.end
  return status === 'not_started' && (!start || !end) ? 'pending_schedule' : status
}
