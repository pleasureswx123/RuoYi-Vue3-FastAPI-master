import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

export function listTargetPurges(projectId, params, signal) {
  return request({ url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/target-purges`, method: 'get', params, signal })
}
export function retryTargetPurge(projectId, purgeId) {
  return request({ url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/target-purges/${assertPositiveId(purgeId, '清理记录')}/retry`, method: 'post' })
}
