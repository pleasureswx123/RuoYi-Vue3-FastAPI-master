const TAG_TYPE_BY_TONE = Object.freeze({
  accent: 'warning',
  character: 'warning',
  danger: 'danger',
  environment: 'primary',
  info: 'primary',
  muted: 'info',
  neutral: 'info',
  primary: 'primary',
  prop: 'success',
  purple: 'primary',
  success: 'success',
  warning: 'warning'
})

/**
 * 将业务展示色调收敛为 Element Plus ElTag 支持的类型。
 */
export function tagTypeFromTone(tone) {
  return Object.hasOwn(TAG_TYPE_BY_TONE, tone) ? TAG_TYPE_BY_TONE[tone] : 'info'
}
