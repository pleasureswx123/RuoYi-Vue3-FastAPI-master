export const STATUS_MESSAGES = {
  401: '登录状态已过期，请重新登录',
  403: '您没有访问该项目或执行此操作的权限',
  404: '请求的资源不存在或已被删除',
  409: '数据已发生变化，请刷新后重试',
  413: '上传文件超过允许的大小',
  416: '媒体请求范围无效，请重新加载媒体'
}

export function parseResponseEnvelope(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || !Object.hasOwn(body, 'code')) return body
  if (Number(body.code) === 200) return body.data
  const error = new Error(body.msg || '请求失败')
  error.code = Number(body.code)
  error.errorKey = body.errorKey
  error.payload = body.data
  throw error
}

export function getErrorDetails(error) {
  const status = Number(error?.response?.status || error?.code || 0)
  const body = error?.response?.data
  const serverMessage = body && typeof body === 'object' ? body.msg : ''
  let message = STATUS_MESSAGES[status]
  if (status === 409 && serverMessage) message = serverMessage
  if (status >= 500) message = serverMessage || '服务暂时不可用，请稍后重试'
  if (!message) message = serverMessage || (error?.message === 'Network Error' ? '后端接口连接异常' : error?.message) || '请求失败'
  return { status, message, errorKey: body?.errorKey || error?.errorKey, data: body?.data }
}

export async function parseBlobError(blob, status) {
  if (!(blob instanceof Blob) || !String(blob.type || '').includes('json')) return null
  try {
    const body = JSON.parse(await blob.text())
    return { ...getErrorDetails({ response: { status, data: body } }), body }
  } catch {
    return null
  }
}
