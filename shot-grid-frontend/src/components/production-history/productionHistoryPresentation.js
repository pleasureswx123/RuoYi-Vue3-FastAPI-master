import { tagTypeFromTone } from '@/utils/tag'

export const PRODUCTION_HISTORY_STEPS = Object.freeze(['创建/导入', '委派', '制作', '提交版本', '审核', '完成'])

const STAGE_META = Object.freeze({
  created: Object.freeze({ label: '已创建', tone: 'neutral' }),
  assigned: Object.freeze({ label: '已委派', tone: 'info' }),
  production: Object.freeze({ label: '制作中', tone: 'warning' }),
  review: Object.freeze({ label: '待审核', tone: 'warning' }),
  revision: Object.freeze({ label: '返修中', tone: 'danger' }),
  final: Object.freeze({ label: '已完成', tone: 'success' })
})

const EVENT_META = Object.freeze({
  subject_created: Object.freeze({ label: '创建', tone: 'info', timelineType: 'primary' }),
  subject_imported: Object.freeze({ label: '导入', tone: 'success', timelineType: 'success' }),
  lane_created: Object.freeze({ label: '制作分项建立', tone: 'info', timelineType: 'primary' }),
  task_created: Object.freeze({ label: '任务委派', tone: 'info', timelineType: 'primary' }),
  version_cycle: Object.freeze({ label: '版本与审核', tone: 'warning', timelineType: 'warning' })
})

const VERSION_STATUS_META = Object.freeze({
  pending_review: Object.freeze({ label: '待审核', tone: 'warning' }),
  rejected: Object.freeze({ label: '已退回', tone: 'danger' }),
  final: Object.freeze({ label: '最终版本', tone: 'success' })
})

const WORKFLOW_STATUS_LABEL = Object.freeze({
  not_started: '未开始',
  preparing: '目录准备中',
  in_progress: '制作中',
  pending_review: '待审核',
  revision: '返修中',
  completed: '已完成',
  rejected: '已退回',
  final: '最终版本',
  draft: '草稿',
  active: '审核中',
  archived: '已归档'
})

const IMPORT_BATCH_STATUS_META = Object.freeze({
  previewed: Object.freeze({ label: '已预检', tone: 'info' }),
  committing: Object.freeze({ label: '提交中', tone: 'warning' }),
  committed: Object.freeze({ label: '已提交', tone: 'success' }),
  failed: Object.freeze({ label: '提交失败', tone: 'danger' }),
  expired: Object.freeze({ label: '已过期', tone: 'neutral' })
})

const REVIEW_ACTION_META = Object.freeze({
  approve: Object.freeze({ label: '确认通过', tone: 'success' }),
  reject: Object.freeze({ label: '退回修改', tone: 'danger' }),
  defer: Object.freeze({ label: '稍后决定', tone: 'warning' })
})

const ISSUE_STATUS_META = Object.freeze({
  open: Object.freeze({ label: '待解决', tone: 'danger' }),
  resolved: Object.freeze({ label: '已解决', tone: 'success' })
})

const VERIFICATION_META = Object.freeze({
  resolved: Object.freeze({ label: '确认已修复', tone: 'success' }),
  still_present: Object.freeze({ label: '仍需修改', tone: 'danger' })
})

const FALLBACK_META = Object.freeze({ label: '未知', tone: 'neutral' })

export function historyStageMeta(value) {
  return STAGE_META[value] || FALLBACK_META
}

export function productionHistoryActiveStep(stage, fallbackValue) {
  const stageStep = {
    created: 0,
    assigned: 1,
    production: 2,
    review: 4,
    revision: 2,
    final: PRODUCTION_HISTORY_STEPS.length
  }[stage]
  if (Number.isInteger(stageStep)) return stageStep

  const fallback = Number(fallbackValue)
  return Number.isInteger(fallback) && fallback >= 0 && fallback <= PRODUCTION_HISTORY_STEPS.length
    ? fallback
    : 0
}

export function historyEventMeta(value) {
  return EVENT_META[value] || FALLBACK_META
}

export function historyVersionStatusMeta(value) {
  return VERSION_STATUS_META[value] || FALLBACK_META
}

export function historyWorkflowStatusLabel(value) {
  return WORKFLOW_STATUS_LABEL[value] || '未知状态'
}

export function historyImportBatchStatusMeta(value) {
  return IMPORT_BATCH_STATUS_META[value] || FALLBACK_META
}

export function historyReviewActionMeta(value) {
  return REVIEW_ACTION_META[value] || FALLBACK_META
}

export function historyIssueStatusMeta(value) {
  return ISSUE_STATUS_META[value] || FALLBACK_META
}

export function historyVerificationMeta(value) {
  return VERIFICATION_META[value] || FALLBACK_META
}

export function historyTagType(meta) {
  return tagTypeFromTone(meta?.tone || 'neutral')
}

export function actorDisplayName(actor) {
  if (!actor) return '系统'
  return String(actor.userName || '').trim()
    || String(actor.nickName || '').trim()
    || (actor.userId ? `用户 ${actor.userId}` : '系统')
}

export function assigneeDisplayName(assignee) {
  return assignee ? actorDisplayName(assignee) : '未分配'
}

export function formatHistoryDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date)
}

export function formatHistoryFileSize(value) {
  const size = Number(value)
  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KiB`
  if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MiB`
  return `${(size / 1024 ** 3).toFixed(1)} GiB`
}

export function sourceIssueSummary(issue) {
  const content = String(issue?.content || '').trim()
  if (content) return content
  const annotationCount = Number(issue?.annotationCount || 0)
  if (Number.isSafeInteger(annotationCount) && annotationCount > 0) {
    return `包含 ${annotationCount} 个画面标注。`
  }
  if (issue?.hasAnnotations) return '包含画面标注。'
  return '未填写问题说明。'
}

export function productionHistoryErrorState(error, subjectType) {
  const status = Number(error?.httpStatus || error?.status || 0)
  const resourceLabel = subjectType === 'asset' ? '资产' : '镜头'
  const context = {
    status,
    errorKey: error?.errorKey || '',
    message: error?.message || '请稍后重试。',
    retryable: status !== 403 && status !== 404
  }
  if (status === 403) return { ...context, title: `没有${resourceLabel}制作履历访问权限`, retryable: false }
  if (status === 404) return { ...context, title: `${resourceLabel}不存在`, retryable: false }
  if (status >= 500 || status === 0) return { ...context, title: '制作履历暂时无法加载', retryable: true }
  return { ...context, title: '制作履历加载失败' }
}

export function assertProductionHistoryData(value, subjectType) {
  if (!value || typeof value !== 'object') throw new TypeError('制作履历响应缺少 data')
  if (!value.subject || value.subject.subjectType !== subjectType) throw new TypeError('制作履历对象与当前页面不匹配')
  if (!value.summary || typeof value.summary !== 'object') throw new TypeError('制作履历响应缺少汇总信息')
  if (!Array.isArray(value.lanes) || !Array.isArray(value.events)) throw new TypeError('制作履历响应结构不完整')
  if (!Number.isInteger(Number(value.summary.activeStep)) || Number(value.summary.activeStep) < 0 || Number(value.summary.activeStep) > PRODUCTION_HISTORY_STEPS.length) {
    throw new TypeError('制作履历当前阶段无效')
  }
  return value
}

export function eventsForLane(events, laneId) {
  if (!laneId) return []
  const normalizedLaneId = String(laneId)
  return (Array.isArray(events) ? events : []).filter(event => {
    const laneIds = Array.isArray(event?.laneIds) ? event.laneIds : []
    return laneIds.length === 0 || laneIds.some(id => String(id) === normalizedLaneId)
  })
}
