const DEFAULT_MESSAGES = {
  400: '请求参数不正确',
  401: '登录状态已失效',
  403: '当前账号无权执行此操作',
  404: '请求的资源不存在',
  409: '数据状态已变更，请刷新后重试',
  413: '上传内容超过允许大小',
  416: '媒体分段请求无效',
  500: '服务暂时不可用'
}

export class ApiError extends Error {
  constructor(message, options = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? null
    this.httpStatus = options.httpStatus ?? null
    this.code = options.code ?? null
    this.errorKey = options.errorKey ?? null
    this.data = options.data ?? null
    this.details = options.details ?? null
    this.response = options.response ?? null
  }
}

export function createApiError(response, fallbackMessage) {
  const payload = response?.data && typeof response.data === 'object' ? response.data : {}
  const httpStatus = Number(response?.status || 0)
  const code = Number(payload.code || httpStatus || 500)
  const status = httpStatus === 200 && code !== 200 ? code : httpStatus || code
  const message = payload.msg || fallbackMessage || DEFAULT_MESSAGES[status] || DEFAULT_MESSAGES[500]
  return new ApiError(message, {
    status,
    httpStatus,
    code,
    errorKey: payload.errorKey ?? payload.data?.errorKey,
    data: payload.data,
    details: payload.details ?? payload.detail ?? payload.data?.details ?? null,
    response
  })
}

export function getDefaultErrorMessage(status) {
  return DEFAULT_MESSAGES[status] || DEFAULT_MESSAGES[500]
}
