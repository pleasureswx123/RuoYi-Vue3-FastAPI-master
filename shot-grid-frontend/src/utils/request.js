import axios from 'axios'
import { ElMessage } from 'element-plus'
import { pinia } from '@/store'
import { useAppStore } from '@/store/modules/app'
import { getToken, removeToken } from '@/utils/auth'
import { clearClientSession } from '@/utils/sessionCleanup'
import { decryptTransportErrorResponse, decryptTransportResponse, encryptTransportRequest, invalidateTransportKeyMeta, resetTransportRequestConfig, shouldRetryTransportWithFreshKey } from '@/utils/transportCrypto'
import { getErrorDetails, parseBlobError, parseResponseEnvelope } from '@/utils/requestErrors'
import { createSingleFlight } from '@/utils/singleFlight'

const service = axios.create({ baseURL: import.meta.env.VITE_APP_BASE_API, timeout: 15000 })
const recentSubmissions = new Map()
let unauthorizedNotified = false

function submissionFingerprint(config) {
  const data = typeof config.data === 'string' ? config.data : JSON.stringify(config.data ?? null)
  return `${String(config.method).toUpperCase()} ${config.url} ${data}`
}

function preventRepeatSubmission(config) {
  if (!['post', 'put', 'patch'].includes(String(config.method).toLowerCase()) || config.headers?.repeatSubmit === false) return
  const serialized = typeof config.data === 'string' ? config.data : JSON.stringify(config.data ?? null)
  if (serialized.length > 5 * 1024 * 1024) return
  const key = submissionFingerprint(config)
  const now = Date.now()
  const interval = Number(config.headers?.interval || 1000)
  if (now - (recentSubmissions.get(key) || 0) < interval) throw new Error('数据正在处理，请勿重复提交')
  recentSubmissions.set(key, now)
  setTimeout(() => recentSubmissions.delete(key), interval)
}

const handleUnauthorized = createSingleFlight(async () => {
  if (!unauthorizedNotified) {
    unauthorizedNotified = true
    ElMessage.error('登录状态已过期，请重新登录')
  }
  const token = getToken()
  try {
    if (token) await axios.post(`${import.meta.env.VITE_APP_BASE_API || ''}/logout`, null, { headers: { Authorization: `Bearer ${token}` }, timeout: 5000 })
  } catch {
    // 会话已经失效时退出接口允许失败，本地状态仍必须清理。
  } finally {
    removeToken()
    clearClientSession()
    if (typeof window !== 'undefined' && !window.location.pathname.endsWith('/session-expired')) window.location.assign(`${import.meta.env.BASE_URL}session-expired`)
  }
})

service.interceptors.request.use(async (config) => {
  useAppStore(pinia).beginRequest()
  try {
    config.headers = config.headers || {}
    if (config.headers.isToken !== false && getToken()) config.headers.Authorization = `Bearer ${getToken()}`
    preventRepeatSubmission(config)
    return await encryptTransportRequest(config)
  } catch (error) {
    useAppStore(pinia).endRequest()
    throw error
  }
}, (error) => Promise.reject(error))

service.interceptors.response.use(async (response) => {
  useAppStore(pinia).endRequest()
  response = await decryptTransportResponse(response)
  if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') return response.data
  try {
    return parseResponseEnvelope(response.data)
  } catch (error) {
    error.response = response
    const details = getErrorDetails(error)
    if (details.status === 401) await handleUnauthorized()
    else ElMessage({ message: details.message, type: details.status === 409 ? 'warning' : 'error' })
    throw Object.assign(error, details)
  }
}, async (rawError) => {
  useAppStore(pinia).endRequest()
  const error = await decryptTransportErrorResponse(rawError)
  if (shouldRetryTransportWithFreshKey(error) && error.config && !error.config.__transportRetried) {
    invalidateTransportKeyMeta()
    error.config.__transportRetried = true
    error.config.headers = error.config.headers || {}
    error.config.headers.repeatSubmit = false
    resetTransportRequestConfig(error.config)
    return service.request(error.config)
  }
  if (error.response?.status === 401) await handleUnauthorized()
  let details = getErrorDetails(error)
  if (error.response?.data instanceof Blob) details = (await parseBlobError(error.response.data, error.response.status)) || details
  const normalized = Object.assign(new Error(details.message), details, { response: error.response, cause: error })
  if (details.status !== 401) ElMessage({ message: details.message, type: details.status === 409 || details.status === 416 ? 'warning' : 'error' })
  return Promise.reject(normalized)
})

export function download(url, params, config = {}) {
  return service.get(url, { ...config, params, responseType: 'blob', headers: { ...config.headers, encrypt: false, encryptResponse: false } })
}

export function requestMedia(url, { range, projectId, ...config } = {}) {
  return service.get(url, { ...config, responseType: 'blob', headers: { ...config.headers, ...(range ? { Range: range } : {}), ...(projectId ? { 'X-Project-Id': projectId } : {}), encrypt: false, encryptResponse: false } })
}

export default service
