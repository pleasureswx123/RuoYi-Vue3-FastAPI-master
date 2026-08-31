const MODES = new Set(['swimlane', 'gantt'])
const SCALES = new Set(['day', 'week', 'month'])
const GROUPS = new Set(['assignee', 'task_kind', 'status', 'priority', 'episode', 'asset_type'])
const BUSINESS_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/

function pad(value) {
  return String(value).padStart(2, '0')
}

export function formatScheduleRouteTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function defaultScheduleRouteWindow(now = new Date()) {
  return {
    windowStart: formatScheduleRouteTime(new Date(now.getFullYear(), now.getMonth(), 1)),
    windowEnd: formatScheduleRouteTime(new Date(now.getFullYear(), now.getMonth() + 1, 1))
  }
}

function firstQueryValue(value) {
  return Array.isArray(value) ? value[0] : value
}

function validBusinessTime(value) {
  if (typeof value !== 'string' || !BUSINESS_TIME_PATTERN.test(value)) return false
  return Number.isFinite(new Date(value).getTime())
}

export function normalizeScheduleRouteQuery(query = {}, now = new Date()) {
  const defaults = defaultScheduleRouteWindow(now)
  const rawMode = firstQueryValue(query.mode)
  const rawScale = firstQueryValue(query.scale)
  const rawGroupBy = firstQueryValue(query.groupBy)
  const rawStart = firstQueryValue(query.windowStart)
  const rawEnd = firstQueryValue(query.windowEnd)
  const validWindow = validBusinessTime(rawStart) && validBusinessTime(rawEnd) && new Date(rawEnd) > new Date(rawStart)
  return {
    mode: MODES.has(rawMode) ? rawMode : 'swimlane',
    scale: SCALES.has(rawScale) ? rawScale : 'week',
    groupBy: GROUPS.has(rawGroupBy) ? rawGroupBy : 'assignee',
    windowStart: validWindow ? rawStart : defaults.windowStart,
    windowEnd: validWindow ? rawEnd : defaults.windowEnd
  }
}

export function scheduleRouteQueryEquals(query, normalized) {
  return Object.entries(normalized).every(([key, value]) => firstQueryValue(query?.[key]) === value)
    && Object.keys(query || {}).every(key => Object.hasOwn(normalized, key))
}
