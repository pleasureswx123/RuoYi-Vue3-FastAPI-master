import axios from 'axios'
import { ElMessage } from 'element-plus'
import { pinia } from '@/store'
import { useAppStore } from '@/store/modules/app'
import { getToken } from '@/utils/auth'

const service = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API,
  timeout: 15000
})

service.interceptors.request.use((config) => {
  useAppStore(pinia).beginRequest()
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

service.interceptors.response.use(
  (response) => {
    useAppStore(pinia).endRequest()
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      return Promise.reject(Object.assign(new Error(body.msg || '请求失败'), { response, errorKey: body.errorKey }))
    }
    return body?.data ?? body
  },
  (error) => {
    useAppStore(pinia).endRequest()
    const status = error.response?.status
    if (status === 401 && window.location.pathname !== '/shot-grid/session-expired') {
      window.location.assign('/shot-grid/session-expired')
    } else if (status !== 401) {
      ElMessage.error(error.response?.data?.msg || error.message || '服务暂时不可用')
    }
    return Promise.reject(error)
  }
)

export default service
