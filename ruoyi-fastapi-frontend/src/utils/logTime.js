const logTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
})

/**
 * 登录、操作日志专用：无时区值保留原钟面时间，不猜测为 UTC。
 * 明确带时区的输入转换为北京时间；不改变数据库或其他业务时间契约。
 */
export function formatLogTime(value) {
  if (value === null || value === undefined || value === '') return '—'
  let input = value
  if (typeof input === 'string') {
    input = input.trim().replace(' ', 'T')
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/i.test(input)) return '—'
    // 无时区历史值缺少来源信息，按显示目标时区解析以避免额外偏移。
    if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(input)) input += '+08:00'
  }
  const date = new Date(input)
  if (Number.isNaN(date.getTime())) return '—'
  const parts = Object.fromEntries(logTimeFormatter.formatToParts(date).map(({ type, value }) => [type, value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}
