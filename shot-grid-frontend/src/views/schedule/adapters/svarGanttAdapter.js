function isoWeekNumber(value) {
  const date = new Date(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()))
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil((((date - yearStart) / 86_400_000) + 1) / 7)
}

const formatYear = date => `${date.getFullYear()}年`
const formatMonth = date => `${date.getMonth() + 1}月`
const formatYearMonth = date => `${date.getFullYear()}年${date.getMonth() + 1}月`
const formatDay = date => `${date.getDate()}日`
const formatWeek = date => `第${isoWeekNumber(date)}周`

const SCALE_CONFIG = Object.freeze({
  day: Object.freeze({
    cellWidth: 72,
    lengthUnit: 'day',
    scales: Object.freeze([
      Object.freeze({ unit: 'month', step: 1, format: formatMonth }),
      Object.freeze({ unit: 'day', step: 1, format: formatDay })
    ])
  }),
  week: Object.freeze({
    cellWidth: 112,
    lengthUnit: 'week',
    scales: Object.freeze([
      Object.freeze({ unit: 'month', step: 1, format: formatYearMonth }),
      Object.freeze({ unit: 'week', step: 1, format: formatWeek })
    ])
  }),
  month: Object.freeze({
    cellWidth: 128,
    lengthUnit: 'month',
    scales: Object.freeze([
      Object.freeze({ unit: 'year', step: 1, format: formatYear }),
      Object.freeze({ unit: 'month', step: 1, format: formatMonth })
    ])
  })
})

export function ganttScaleFor(scale) {
  return SCALE_CONFIG[scale]
}

function toGanttTask(row, editable) {
  const conflicts = Array.isArray(row.conflicts) ? row.conflicts : []
  const canSchedule = Array.isArray(row.allowedActions) && row.allowedActions.includes('schedule')
  return {
    id: `task:${row.taskId}`,
    taskId: row.taskId,
    text: row.taskName || row.target?.code || row.target?.name || `任务 ${row.taskId}`,
    start: new Date(row.currentStart),
    end: new Date(row.currentEnd),
    assigneeUserId: row.assignee.userId,
    assigneeName: row.assignee.userName,
    targetName: row.target.name,
    taskKind: row.taskKind,
    taskStatus: row.taskStatus,
    priority: row.priority,
    lockVersion: row.lockVersion,
    groupKey: row.groupKey,
    groupName: row.groupName,
    baseline: {
      start: new Date(row.baselineStart),
      end: new Date(row.baselineEnd)
    },
    conflictTaskIds: conflicts.map(conflict => conflict.taskId),
    className: conflicts.length > 0 ? 'is-conflicted' : '',
    readonly: !editable || !canSchedule
  }
}

function ganttGroupFor(task, groupBy) {
  if (groupBy === 'assignee') {
    return {
      key: `assignee:${task.assigneeUserId}`,
      name: task.assigneeName || '未分配负责人'
    }
  }
  return {
    key: task.groupKey || `${groupBy}:ungrouped`,
    name: task.groupName || '未分组'
  }
}

export function toGanttTasks(rows, { editable = false, groupBy = null } = {}) {
  const tasks = rows.map(row => toGanttTask(row, editable))
  if (!groupBy) {
    return tasks
  }

  const groups = new Map()
  for (const task of tasks) {
    const group = ganttGroupFor(task, groupBy)
    if (!groups.has(group.key)) {
      groups.set(group.key, { ...group, tasks: [] })
    }
    groups.get(group.key).tasks.push(task)
  }

  return Array.from(groups.values()).flatMap(group => {
    const groupId = `group:${group.key}`
    const start = new Date(Math.min(...group.tasks.map(task => task.start.getTime())))
    const end = new Date(Math.max(...group.tasks.map(task => task.end.getTime())))
    const summary = {
      id: groupId,
      text: group.name,
      type: 'summary',
      parent: 0,
      open: true,
      start,
      end,
      readonly: true,
      isScheduleGroup: true,
      groupKey: group.key,
      groupName: group.name
    }
    return [summary, ...group.tasks.map(task => ({ ...task, parent: groupId }))]
  })
}

function padDatePart(value) {
  return String(value).padStart(2, '0')
}

function formatLocalDateTime(value) {
  return `${value.getFullYear()}-${padDatePart(value.getMonth() + 1)}-${padDatePart(value.getDate())}`
    + `T${padDatePart(value.getHours())}:${padDatePart(value.getMinutes())}:${padDatePart(value.getSeconds())}`
}

export function rangeChangeRequest({ task, nextStart, nextEnd, nextAssigneeUserId, operationSource }) {
  if (task.readonly) {
    return { accepted: false, reason: 'readonly' }
  }
  if (nextAssigneeUserId !== task.assigneeUserId) {
    return { accepted: false, reason: 'assignee-change' }
  }
  return {
    accepted: true,
    payload: {
      taskId: task.taskId,
      lockVersion: task.lockVersion,
      expectedStartTime: formatLocalDateTime(nextStart),
      expectedEndTime: formatLocalDateTime(nextEnd),
      operationSource
    }
  }
}

export function toSwimlaneRows(tasks, { groupBy = 'assignee' } = {}) {
  const lanes = new Map()
  for (const task of tasks) {
    const laneId = groupBy === 'assignee' ? `assignee:${task.assigneeUserId}` : task.groupKey
    const laneName = groupBy === 'assignee' ? task.assigneeName : task.groupName
    if (!lanes.has(laneId)) {
      lanes.set(laneId, {
        id: laneId,
        assigneeUserId: task.assigneeUserId,
        assigneeName: task.assigneeName,
        groupName: laneName,
        tasks: []
      })
    }
    lanes.get(laneId).tasks.push(task)
  }

  return Array.from(lanes.values()).map(lane => {
    const trackEnds = []
    const sortedTasks = [...lane.tasks].sort((left, right) => (
      left.start - right.start || left.end - right.end || left.taskId - right.taskId
    ))
    const tasksWithTracks = sortedTasks.map(task => {
      let track = trackEnds.findIndex(end => end <= task.start)
      if (track === -1) {
        track = trackEnds.length
      }
      trackEnds[track] = task.end
      return { ...task, track }
    })
    return { ...lane, tasks: tasksWithTracks, trackCount: trackEnds.length }
  })
}

export function baselineOverlayStyle(task) {
  if (!task?.baseline?.start || !task?.baseline?.end || !task?.start || !task?.end) {
    return {}
  }
  const currentDuration = task.end - task.start
  if (currentDuration <= 0) {
    return {}
  }
  const left = ((task.baseline.start - task.start) / currentDuration) * 100
  const width = ((task.baseline.end - task.baseline.start) / currentDuration) * 100
  return {
    left: `${Number(left.toFixed(4))}%`,
    width: `${Number(width.toFixed(4))}%`
  }
}
