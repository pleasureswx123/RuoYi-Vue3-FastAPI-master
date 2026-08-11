import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function projectUrl(projectId, suffix = '') {
  return `/shot-grid/projects/${assertPositiveId(projectId, '项目')}${suffix}`
}

function shotUrl(projectId, shotId, suffix = '') {
  return `${projectUrl(projectId, '/shots')}/${assertPositiveId(shotId, '镜头')}${suffix}`
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

export function assertProtectedVersionDownloadUrl(value) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!/^\/shot-grid\/versions\/[1-9]\d*\/files\/[A-Za-z0-9_-]{1,100}\/download$/.test(normalized)) {
    throw new TypeError('缩略图下载地址不符合受保护版本文件路径')
  }
  return normalized
}

export function downloadProtectedThumbnail(url, options = {}) {
  return request({
    url: assertProtectedVersionDownloadUrl(url),
    method: 'get',
    responseType: 'blob',
    signal: options.signal,
    silentError: true
  })
}

export function getEpisodePage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/episodes'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getScenePage(projectId, episodeId, params, options = {}) {
  return request({
    url: `${projectUrl(projectId, '/episodes')}/${assertPositiveId(episodeId, '集')}/scenes`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function listShotAssignees(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/shot-assignee-options'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getShotPage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/shots'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getShotDetail(projectId, shotId, options = {}) {
  return request({
    url: shotUrl(projectId, shotId),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function createShot(projectId, data) {
  return request({
    url: projectUrl(projectId, '/shots'),
    method: 'post',
    data,
    silentError: true
  })
}

export function updateShot(projectId, shotId, data) {
  return request({
    url: shotUrl(projectId, shotId),
    method: 'put',
    data,
    silentError: true
  })
}

export function archiveShot(projectId, shotId, data) {
  return request({
    url: shotUrl(projectId, shotId, '/archive'),
    method: 'post',
    data,
    silentError: true
  })
}

export function assignShotTask(projectId, shotId, data) {
  return request({
    url: shotUrl(projectId, shotId, '/assign'),
    method: 'post',
    data,
    silentError: true
  })
}

export function previewShotImport(projectId, file, options = {}) {
  if (!(file instanceof File)) {
    throw new TypeError('请选择镜头 Excel 文件')
  }
  const data = new FormData()
  data.append('file', file, file.name)
  return request({
    url: projectUrl(projectId, '/shots/import/preview'),
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

export function downloadShotImportTemplate(options = {}) {
  return request({
    url: '/shot-grid/imports/shots/template',
    method: 'get',
    responseType: 'blob',
    signal: options.signal,
    silentError: true
  })
}

export function commitShotImport(projectId, data, idempotencyKey) {
  return request({
    url: projectUrl(projectId, '/shots/import/commit'),
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    timeout: 60_000,
    silentError: true
  })
}
