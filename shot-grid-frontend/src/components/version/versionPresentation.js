const SUBMISSION_STATUS = Object.freeze({
  pending: {
    label: '等待发布',
    tone: 'warning',
    step: 0,
    description: '提交已受理，正在等待处理；正式版本生成前请勿重复提交。'
  },
  publishing: {
    label: '正在发布',
    tone: 'warning',
    step: 1,
    description: '文件正在保存到项目 NAS，完成前请耐心等待。'
  },
  published: {
    label: '文件已保存',
    tone: 'warning',
    step: 2,
    description: '文件已保存到项目 NAS，正在生成正式版本。'
  },
  committing: {
    label: '正在生成版本',
    tone: 'warning',
    step: 3,
    description: '正在整理版本信息并创建审核任务。'
  },
  committed: {
    label: '版本已生成',
    tone: 'success',
    step: 4,
    description: '正式版本和审核任务已创建，可以继续后续工作。'
  },
  failed: {
    label: '发布失败',
    tone: 'danger',
    step: -1,
    description: '正式版本尚未生成；请重试，或联系项目管理人处理。'
  }
})

const VERSION_STATUS = Object.freeze({
  pending_review: { label: '待审核', tone: 'warning' },
  rejected: { label: '已退回', tone: 'danger' },
  final: { label: '最终版本', tone: 'success' }
})

const STATUS_HTTP_COPY = Object.freeze({
  401: ['会话已失效', '请重新登录后继续操作。'],
  403: ['无权访问版本', '当前账号不是该资源的授权成员，或缺少所需版本权限。'],
  404: ['版本资源不存在', '任务、提交或版本可能已删除，也可能当前账号不可见。'],
  409: ['版本状态发生冲突', '请保留当前文件并刷新任务状态后重试。'],
  413: ['文件超过上传上限', '单个版本文件不能超过 100 MiB。'],
  416: ['文件下载信息已失效', '请重新下载，或刷新版本文件信息后重试。'],
  500: ['版本处理异常', '暂时无法完成操作，请稍后重试。']
})

export function submissionStatusMeta(status) {
  return SUBMISSION_STATUS[status] || {
    label: '未知状态',
    tone: 'neutral',
    step: -1,
    description: '暂时无法识别当前提交进度，请刷新后重试。'
  }
}

export function versionStatusMeta(status) {
  return VERSION_STATUS[status] || { label: '未知状态', tone: 'neutral' }
}

export function formatVersionDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

export function formatFileSize(value) {
  const size = Number(value)
  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KiB`
  return `${(size / 1024 ** 2).toFixed(1)} MiB`
}

export function versionErrorState(error, fallbackTitle = '版本操作失败') {
  const status = Number(error?.httpStatus || error?.status || 0)
  const normalizedStatus = status >= 500 ? 500 : status
  const [title, description] = STATUS_HTTP_COPY[normalizedStatus] || [fallbackTitle, '操作未完成，请稍后重试。']
  return {
    title,
    message: error?.message || description,
    description,
    httpStatus: status || null,
    errorKey: error?.errorKey || null,
    details: error?.details || null
  }
}

export function isSubmissionTerminal(status) {
  return status === 'committed' || status === 'failed'
}

export function acceptedToSubmissionStatus(data) {
  if (!data) return null
  return {
    submissionId: data.submissionId,
    taskId: data.taskId,
    submissionStatus: data.submissionStatus,
    reservedVersionNumber: data.reservedVersionNumber,
    candidateCount: data.candidateCount ?? data.candidates?.length ?? 1,
    candidates: data.candidates || [],
    businessFileName: data.businessFileName,
    taskStatus: data.taskStatus,
    replayed: Boolean(data.replayed),
    attemptCount: data.attemptCount ?? 0,
    versionId: data.versionId ?? null,
    reviewListId: data.reviewListId ?? null,
    lastErrorKey: data.lastErrorKey ?? null,
    lastErrorMessage: data.lastErrorMessage ?? null
  }
}

export const submissionStatusOrder = Object.freeze(['pending', 'publishing', 'published', 'committing', 'committed'])
