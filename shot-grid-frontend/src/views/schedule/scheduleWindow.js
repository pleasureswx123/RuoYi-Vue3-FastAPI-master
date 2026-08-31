const SCALES = new Set(['day', 'week', 'month'])
const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

function pad(value) {
  return String(value).padStart(2, '0')
}

function validDate(value, fieldName) {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) throw new TypeError(`${fieldName}无效`)
  return date
}

function parseScheduleDate(value, fieldName) {
  const match = typeof value === 'string' ? DATE_PATTERN.exec(value) : null
  if (!match) throw new TypeError(`${fieldName}无效`)
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  if (
    date.getFullYear() !== Number(match[1])
    || date.getMonth() !== Number(match[2]) - 1
    || date.getDate() !== Number(match[3])
  ) throw new TypeError(`${fieldName}无效`)
  return date
}

function addDays(value, days) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate() + days)
}

function addCalendarMonths(value, months) {
  const targetMonthStart = new Date(
    value.getFullYear(),
    value.getMonth() + months,
    1,
    value.getHours(),
    value.getMinutes(),
    value.getSeconds(),
    value.getMilliseconds()
  )
  const targetMonthEnd = new Date(targetMonthStart.getFullYear(), targetMonthStart.getMonth() + 1, 0)
  targetMonthStart.setDate(Math.min(value.getDate(), targetMonthEnd.getDate()))
  return targetMonthStart
}

export function formatScheduleTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function formatScheduleDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function scheduleWindowForScale(scale = 'week', anchor = new Date()) {
  const effectiveScale = SCALES.has(scale) ? scale : 'week'
  const anchorDate = validDate(anchor, '排期锚点')
  const anchorDay = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), anchorDate.getDate())
  let start
  let end

  if (effectiveScale === 'day') {
    start = addDays(anchorDay, -7)
    end = addDays(anchorDay, 24)
  } else if (effectiveScale === 'week') {
    const mondayOffset = (anchorDay.getDay() + 6) % 7
    const currentMonday = addDays(anchorDay, -mondayOffset)
    start = addDays(currentMonday, -28)
    end = addDays(currentMonday, 63)
  } else {
    start = new Date(anchorDay.getFullYear(), anchorDay.getMonth() - 3, 1)
    end = new Date(anchorDay.getFullYear(), anchorDay.getMonth() + 10, 1)
  }

  return {
    windowStart: formatScheduleTime(start),
    windowEnd: formatScheduleTime(end)
  }
}

export function dateRangeToScheduleWindow(value) {
  if (!Array.isArray(value) || value.length !== 2) throw new TypeError('日期范围无效')
  const start = parseScheduleDate(value[0], '窗口开始日期')
  const inclusiveEnd = parseScheduleDate(value[1], '窗口结束日期')
  if (inclusiveEnd < start) throw new TypeError('窗口结束日期不能早于开始日期')
  return {
    windowStart: formatScheduleTime(start),
    windowEnd: formatScheduleTime(addDays(inclusiveEnd, 1))
  }
}

export function scheduleWindowToDateRange(windowStart, windowEnd) {
  const start = validDate(windowStart, '窗口开始时间')
  const exclusiveEnd = validDate(windowEnd, '窗口结束时间')
  if (exclusiveEnd <= start) throw new TypeError('窗口结束时间必须晚于开始时间')
  const endsAtDayBoundary = exclusiveEnd.getHours() === 0
    && exclusiveEnd.getMinutes() === 0
    && exclusiveEnd.getSeconds() === 0
    && exclusiveEnd.getMilliseconds() === 0
  const inclusiveEnd = endsAtDayBoundary ? addDays(exclusiveEnd, -1) : exclusiveEnd
  return [formatScheduleDate(start), formatScheduleDate(inclusiveEnd)]
}

export function shiftScheduleWindow(windowStart, windowEnd, direction, scale) {
  const start = validDate(windowStart, '窗口开始时间')
  const end = validDate(windowEnd, '窗口结束时间')
  if (end <= start) throw new TypeError('窗口结束时间必须晚于开始时间')

  if (scale === 'month') {
    const monthSpan = Math.max(1, (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth())
    return {
      windowStart: formatScheduleTime(addCalendarMonths(start, monthSpan * direction)),
      windowEnd: formatScheduleTime(addCalendarMonths(end, monthSpan * direction))
    }
  }

  const duration = end.getTime() - start.getTime()
  return {
    windowStart: formatScheduleTime(new Date(start.getTime() + duration * direction)),
    windowEnd: formatScheduleTime(new Date(end.getTime() + duration * direction))
  }
}
