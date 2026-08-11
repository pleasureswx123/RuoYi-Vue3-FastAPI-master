const SUBMISSION_STATUS = Object.freeze({
  pending: {
    label: '等待发布',
    tone: 'warning',
    step: 0,
    description: '提交已受理，尚未开始写入 NAS，也尚未形成正式版本。'
  },
  publishing: {
    label: '正在发布',
    tone: 'warning',
    step: 1,
    description: '后台正在校验源文件并写入 NAS 临时文件，尚未形成正式版本。'
  },
  published: {
    label: '文件已发布',
    tone: 'warning',
    step: 2,
    description: 'NAS 文件已完成原子发布，正式版本记录仍在创建中。'
  },
  committing: {
    label: '正在落库',
    tone: 'warning',
    step: 3,
    description: '正在创建正式版本、文件引用和自动审核单。'
  },
  committed: {
    label: '版本已形成',
    tone: 'success',
    step: 4,
    description: '正式版本与自动审核单已创建，上传链路完成。'
  },
  failed: {
    label: '发布失败',
    tone: 'danger',
    step: -1,
    description: '正式版本尚未形成；请查看诊断后人工重试。'
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
  413: ['文件超过上传上限', '平台私有文件当前单文件上限为 100 MiB。'],
  416: ['文件读取范围无效', '请重新发起完整下载，或刷新版本文件信息。'],
  500: ['版本服务异常', '服务暂时不可用，当前操作没有被视为成功。']
})

export function submissionStatusMeta(status) {
  return SUBMISSION_STATUS[status] || {
    label: '未知状态',
    tone: 'neutral',
    step: -1,
    description: '后端返回了前端尚未识别的提交状态，请刷新后重试。'
  }
}

export function versionStatusMeta(status) {
  return VERSION_STATUS[status] || { label: status || '未知', tone: 'neutral' }
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
  const [title, description] = STATUS_HTTP_COPY[normalizedStatus] || [fallbackTitle, '请求未完成，请稍后重试。']
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
