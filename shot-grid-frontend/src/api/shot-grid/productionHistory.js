import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function subjectHistoryUrl(projectId, subjectType, subjectId) {
  const normalizedProjectId = assertPositiveId(projectId, '项目')
  const normalizedSubjectId = assertPositiveId(subjectId, subjectType === 'shot' ? '镜头' : '资产')
  const resource = subjectType === 'shot' ? 'shots' : subjectType === 'asset' ? 'assets' : null
  if (!resource) throw new TypeError('制作履历对象类型无效')
  return `/shot-grid/projects/${normalizedProjectId}/${resource}/${normalizedSubjectId}/production-history`
}

export function getProductionHistory(projectId, subjectType, subjectId, options = {}) {
  return request({
    url: subjectHistoryUrl(projectId, subjectType, subjectId),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function getShotProductionHistory(projectId, shotId, options = {}) {
  return getProductionHistory(projectId, 'shot', shotId, options)
}

export function getAssetProductionHistory(projectId, assetId, options = {}) {
  return getProductionHistory(projectId, 'asset', assetId, options)
}
