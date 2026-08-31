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

export function toGanttTasks(rows, { editable = false } = {}) {
  return rows.map(row => {
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
      baseline: {
        start: new Date(row.baselineStart),
        end: new Date(row.baselineEnd)
      },
      conflictTaskIds: conflicts.map(conflict => conflict.taskId),
      className: conflicts.length > 0 ? 'is-conflicted' : '',
      readonly: !editable || !canSchedule
    }
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

export function toSwimlaneRows(tasks) {
  const lanes = new Map()
  for (const task of tasks) {
    if (!lanes.has(task.assigneeUserId)) {
      lanes.set(task.assigneeUserId, {
        id: `assignee:${task.assigneeUserId}`,
        assigneeUserId: task.assigneeUserId,
        assigneeName: task.assigneeName,
        tasks: []
      })
    }
    lanes.get(task.assigneeUserId).tasks.push(task)
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
  const currentDuration = task.end - task.start
  const left = ((task.baseline.start - task.start) / currentDuration) * 100
  const width = ((task.baseline.end - task.baseline.start) / currentDuration) * 100
  return {
    left: `${Number(left.toFixed(4))}%`,
    width: `${Number(width.toFixed(4))}%`
  }
}
