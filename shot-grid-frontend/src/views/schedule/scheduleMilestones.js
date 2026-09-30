export function taskMilestones(history, taskId) {
  const lane = history?.lanes?.find(item => item.task?.taskId === taskId)
  if (!lane) return null
  const cycles = (history.events || []).filter(item => item.laneIds?.includes(lane.laneId) && item.versionCycle).map(item => item.versionCycle)
  const ordered = values => values.filter(Boolean).sort((a, b) => new Date(a) - new Date(b))
  const submissions = ordered(cycles.map(item => item.submittedTime))
  const actions = cycles.flatMap(item => item.reviewActions || [])
  return {
    created: lane.task.createTime,
    firstSubmitted: submissions[0],
    lastSubmitted: submissions.at(-1),
    lastReviewed: ordered(actions.map(item => item.createTime)).at(-1),
    approved: ordered(actions.filter(item => item.actionType === 'approve').map(item => item.createTime)).at(-1)
  }
}

export function scheduleDateWarnings(task, range, milestones, now = Date.now()) {
  const [start, end] = (range || []).map(value => new Date(value).getTime())
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return []
  const messages = []
  if (task?.taskStatus === 'not_started' && start < now) messages.push('计划开始已过去，任务尚未开工。')
  if (task?.taskStatus !== 'completed' && end < now) messages.push('计划结束已过去，保存后该任务将显示为逾期。')
  if (milestones?.created && start < new Date(milestones.created).getTime()) messages.push('计划开始早于任务创建，请核对是否为线下工作补录。')
  if (milestones?.firstSubmitted && start > new Date(milestones.firstSubmitted).getTime()) messages.push('新计划开始晚于首次提交，请核对计划口径。')
  return messages
}
