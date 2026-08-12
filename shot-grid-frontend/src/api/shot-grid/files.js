import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

export function getProjectFilePage(projectId, params = {}, options = {}) {
  return request({
    url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/files`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}
