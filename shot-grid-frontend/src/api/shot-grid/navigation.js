import request from '@/utils/request'

export function getShotGridNavigation() {
  return request({ url: '/shot-grid/navigation', method: 'get', silentError: true })
}
