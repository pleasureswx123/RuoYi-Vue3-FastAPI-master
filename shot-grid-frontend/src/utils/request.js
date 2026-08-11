import axios from 'axios'
import { ElMessage } from 'element-plus'

import { ApiError, createApiError, getDefaultErrorMessage } from '@/utils/apiError'
import { getToken } from '@/utils/auth'
import cache from '@/utils/cache'
import { toQueryString } from '@/utils/query'
import {
  decryptTransportErrorResponse,
  decryptTransportResponse,
  encryptTransportRequest,
  invalidateTransportKeyMeta,
  resetTransportRequestConfig,
  shouldRetryTransportWithFreshKey
} from '@/utils/transportCrypto'

const SUCCESS_CODE = 200
const REPEAT_SUBMIT_LIMIT = 5 * 1024 * 1024
const REPEAT_SUBMIT_KEY = 'shot-grid:repeat-submit'
const MAX_STRUCTURED_ERROR_BYTES = 64 * 1024

let sessionExpiredHandler = null
let sessionExpiryPromise = null

function responseContentType(response) {
  return String(
    response?.headers?.get?.('content-type') ||
    response?.headers?.['content-type'] ||
    response?.data?.type ||
    ''
  ).toLowerCase()
}

function isJsonContentType(contentType) {
  return contentType.includes('application/json') || contentType.includes('+json')
}

async function readBlobText(payload) {
  if (typeof payload.text === 'function') return payload.text()
  if (typeof FileReader === 'undefined') return null
  return new Promise(resolve => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : null)
    reader.onerror = () => resolve(null)
    reader.readAsText(payload)
  })
}

async function decodeStructuredErrorResponse(response) {
  if (!response || !isJsonContentType(responseContentType(response))) return response
  const payload = response.data
  let text = null
  try {
    if (typeof Blob !== 'undefined' && payload instanceof Blob) {
      if (payload.size > MAX_STRUCTURED_ERROR_BYTES) return response
      text = await readBlobText(payload)
    } else if (typeof ArrayBuffer !== 'undefined' && payload instanceof ArrayBuffer) {
      if (payload.byteLength > MAX_STRUCTURED_ERROR_BYTES) return response
      text = new TextDecoder().decode(payload)
    }
  } catch {
    return response
  }
  if (text === null) return response
  try {
    const data = JSON.parse(text)
    return data && typeof data === 'object' ? { ...response, data } : response
  } catch {
    return response
  }
}

export function setSessionExpiredHandler(handler) {
  sessionExpiredHandler = typeof handler === 'function' ? handler : null
}

async function handleSessionExpired(error) {
  if (!sessionExpiredHandler) {
    return
  }
  if (!sessionExpiryPromise) {
    sessionExpiryPromise = Promise.resolve(sessionExpiredHandler(error)).finally(() => {
      sessionExpiryPromise = null
    })
  }
  await sessionExpiryPromise
}

function checkRepeatSubmit(config) {
  const headers = config.headers || {}
  if (headers.repeatSubmit === false || !['post', 'put', 'patch'].includes(config.method)) {
    return
  }
  const request = {
    url: config.url,
    data: typeof config.data === 'string' ? config.data : JSON.stringify(config.data ?? null),
    time: Date.now()
  }
  if (JSON.stringify(request).length >= REPEAT_SUBMIT_LIMIT) {
    console.warn(`[${config.url}] 请求体过大，跳过前端重复提交检测。`)
    return
  }
  const previous = cache.session.getJSON(REPEAT_SUBMIT_KEY)
  const interval = Number(headers.interval || 1000)
  if (
    previous &&
    previous.url === request.url &&
    previous.data === request.data &&
    request.time - previous.time < interval
  ) {
    throw createApiError(
      { status: 409, data: { code: 409, errorKey: 'SG_CLIENT_REPEAT_SUBMIT', msg: '请求正在处理，请勿重复提交' } },
      '请求正在处理，请勿重复提交'
    )
  }
  cache.session.setJSON(REPEAT_SUBMIT_KEY, request)
}

function notifyRequestError(error, config = {}) {
  if (config.silentError || error.status === 401 || axios.isCancel(error)) {
    return
  }
  ElMessage({
    type: error.status === 409 || error.status === 413 || error.status === 416 ? 'warning' : 'error',
    message: error.message,
    duration: 5000
  })
}

const request = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json;charset=utf-8' },
  paramsSerializer: params => toQueryString(params)
})

request.interceptors.request.use(async config => {
  config.headers = config.headers || {}
  config.method = (config.method || 'get').toLowerCase()
  if (config.headers.isToken !== false && getToken()) {
    config.headers.Authorization = `Bearer ${getToken()}`
  }
  checkRepeatSubmit(config)
  delete config.headers.isToken
  delete config.headers.repeatSubmit
  delete config.headers.interval
  return encryptTransportRequest(config)
})

request.interceptors.response.use(
  async response => {
    response = await decryptTransportResponse(response)
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') {
      return response.data
    }
    const payload = response.data
    const code = Number(payload?.code ?? response.status ?? SUCCESS_CODE)
    const isHttpSuccess = response.status >= 200 && response.status < 300
    const isEnvelopeSuccess = code >= 200 && code < 300 && payload?.success !== false
    if (isHttpSuccess && isEnvelopeSuccess) {
      return payload
    }
    const error = createApiError(response)
    if (error.status === 401) {
      await handleSessionExpired(error)
    }
    notifyRequestError(error, response.config)
    throw error
  },
  async originalError => {
    if (axios.isCancel(originalError)) {
      throw originalError
    }
    if (originalError instanceof ApiError) {
      if (originalError.status === 401) {
        await handleSessionExpired(originalError)
      }
      notifyRequestError(originalError)
      throw originalError
    }
    const decryptedError = await decryptTransportErrorResponse(originalError)
    if (
      shouldRetryTransportWithFreshKey(decryptedError) &&
      decryptedError.config &&
      !decryptedError.config.__transportRetried
    ) {
      invalidateTransportKeyMeta()
      decryptedError.config.__transportRetried = true
      decryptedError.config.headers = decryptedError.config.headers || {}
      decryptedError.config.headers.repeatSubmit = false
      resetTransportRequestConfig(decryptedError.config)
      return request.request(decryptedError.config)
    }

    const response = await decodeStructuredErrorResponse(decryptedError.response)
    const fallback = !response
      ? decryptedError.code === 'ECONNABORTED'
        ? '请求超时，请稍后重试'
        : '无法连接业务服务，请检查网络或稍后重试'
      : getDefaultErrorMessage(response.status)
    const error = response
      ? createApiError(response, fallback)
      : createApiError({ status: 0, data: { code: 500, msg: fallback } }, fallback)
    if (error.status === 401) {
      await handleSessionExpired(error)
    }
    notifyRequestError(error, decryptedError.config)
    throw error
  }
)

export default request
