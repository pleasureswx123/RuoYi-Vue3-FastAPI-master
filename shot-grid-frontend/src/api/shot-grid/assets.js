import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function projectUrl(projectId, suffix = '') {
  return `/shot-grid/projects/${assertPositiveId(projectId, '项目')}${suffix}`
}

function assetUrl(projectId, assetId, suffix = '') {
  return `${projectUrl(projectId, '/assets')}/${assertPositiveId(assetId, '资产')}${suffix}`
}

function assetItemUrl(projectId, assetItemId, suffix = '') {
  return `${projectUrl(projectId, '/asset-items')}/${assertPositiveId(assetItemId, '资产制作分项')}${suffix}`
}

function idempotencyHeaders(idempotencyKey) {
  const normalized = typeof idempotencyKey === 'string' ? idempotencyKey.trim() : ''
  if (!normalized || normalized.length > 100) {
    throw new TypeError('幂等键长度必须为 1—100 个字符')
  }
  return {
    'X-Idempotency-Key': normalized,
    repeatSubmit: false
  }
}

export function assertProtectedAssetThumbnailUrl(value) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!/^\/shot-grid\/versions\/[1-9]\d*\/files\/[A-Za-z0-9_-]{1,100}\/download$/.test(normalized)) {
    throw new TypeError('资产缩略图下载地址不符合受保护版本文件路径')
  }
  return normalized
}

export function downloadAssetThumbnail(url, options = {}) {
  return request({
    url: assertProtectedAssetThumbnailUrl(url),
    method: 'get',
    responseType: 'blob',
    signal: options.signal,
    silentError: true
  })
}

export function listAssetAssignees(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/asset-assignee-options'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getAssetPage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/assets'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getAssetDetail(projectId, assetId, options = {}) {
  return request({
    url: assetUrl(projectId, assetId),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function createAsset(projectId, data) {
  return request({
    url: projectUrl(projectId, '/assets'),
    method: 'post',
    data,
    silentError: true
  })
}

export function updateAsset(projectId, assetId, data) {
  return request({
    url: assetUrl(projectId, assetId),
    method: 'put',
    data,
    silentError: true
  })
}

export function archiveAsset(projectId, assetId, data) {
  return request({
    url: assetUrl(projectId, assetId, '/archive'),
    method: 'post',
    data,
    silentError: true
  })
}

export function batchDeleteAssets(projectId, items) {
  return request({
    url: projectUrl(projectId, '/assets/batch-delete'),
    method: 'post',
    data: { items, reason: '资产列表批量删除' },
    silentError: true
  })
}

export function getAssetItems(projectId, assetId, options = {}) {
  return request({
    url: assetUrl(projectId, assetId, '/items'),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function createAssetItem(projectId, assetId, data) {
  return request({
    url: assetUrl(projectId, assetId, '/items'),
    method: 'post',
    data,
    silentError: true
  })
}

export function updateAssetItem(projectId, assetItemId, data) {
  return request({
    url: assetItemUrl(projectId, assetItemId),
    method: 'put',
    data,
    silentError: true
  })
}

export function archiveAssetItem(projectId, assetItemId, data) {
  return request({
    url: assetItemUrl(projectId, assetItemId, '/archive'),
    method: 'post',
    data,
    silentError: true
  })
}

export function deleteAssetItem(projectId, assetItemId, data) {
  return request({
    url: assetItemUrl(projectId, assetItemId, '/delete'),
    method: 'post',
    data,
    silentError: true
  })
}

export function assignAssetItemTask(projectId, assetItemId, data) {
  return request({
    url: assetItemUrl(projectId, assetItemId, '/assign'),
    method: 'post',
    data,
    silentError: true
  })
}

export function batchAssignAssetItemTasks(projectId, assigneeUserId, items) {
  return request({
    url: projectUrl(projectId, '/asset-items/batch-assign'),
    method: 'post',
    data: { assigneeUserId, items },
    silentError: true
  })
}

export function previewAssetImport(projectId, file, options = {}) {
  if (!(file instanceof File)) {
    throw new TypeError('请选择资产 Excel 文件')
  }
  const data = new FormData()
  data.append('file', file, file.name)
  return request({
    url: projectUrl(projectId, '/assets/import/preview'),
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data',
      repeatSubmit: false
    },
    timeout: 60_000,
    signal: options.signal,
    silentError: true
  })
}

export function downloadAssetImportTemplate(options = {}) {
  return request({
    url: '/shot-grid/imports/assets/template',
    method: 'get',
    responseType: 'blob',
    signal: options.signal,
    silentError: true
  })
}

export function commitAssetImport(projectId, data, idempotencyKey) {
  return request({
    url: projectUrl(projectId, '/assets/import/commit'),
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    timeout: 60_000,
    silentError: true
  })
}

export function getAssetRequirementPage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/asset-requirements'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function resolveAssetRequirement(projectId, requirementId, data, idempotencyKey) {
  return request({
    url: `${projectUrl(projectId, '/asset-requirements')}/${assertPositiveId(requirementId, '资产需求')}/resolve`,
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    silentError: true
  })
}

export function ignoreAssetRequirement(projectId, requirementId, data, idempotencyKey) {
  return request({
    url: `${projectUrl(projectId, '/asset-requirements')}/${assertPositiveId(requirementId, '资产需求')}/ignore`,
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    silentError: true
  })
}

export function rematchAssetRequirements(projectId) {
  return request({
    url: projectUrl(projectId, '/asset-requirements/rematch'),
    method: 'post',
    silentError: true
  })
}
