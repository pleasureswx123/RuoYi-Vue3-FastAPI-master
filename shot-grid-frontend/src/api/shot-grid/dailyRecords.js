import request from '@/utils/request'
import { assertPositiveId } from './projects'

export function dailyRequest(projectId, suffix = '', params = {}, options = {}) {
  return request({ url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/daily-${options.statistics ? 'statistics' : 'records'}${suffix}`, method: 'get', params, signal: options.signal, silentError: true })
}
export function saveDailyRecords(projectId, data) {
  return request({ url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/daily-records`, method: 'put', data, silentError: true })
}
