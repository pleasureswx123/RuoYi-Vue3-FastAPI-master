import request from '@/utils/request'

export function searchShotGrid(keyword, options = {}) {
  const normalized = typeof keyword === 'string' ? keyword.trim() : ''
  if (normalized.length < 2 || normalized.length > 100) {
    throw new TypeError('搜索关键字长度必须为 2—100 个字符')
  }
  return request({
    url: '/shot-grid/search',
    method: 'get',
    params: { keyword: normalized, limit: options.limit || 8 },
    signal: options.signal,
    silentError: true
  })
}
