import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function idempotencyHeaders(idempotencyKey) {
  const normalized = typeof idempotencyKey === 'string' ? idempotencyKey.trim() : ''
  if (!normalized || normalized.length > 100) {
    throw new TypeError('幂等键长度必须为 1—100 个字符')
  }
  return { 'X-Idempotency-Key': normalized, repeatSubmit: false }
}

function assertReferenceDownloadUrl(value) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!/^\/shot-grid\/(?:issue-drafts|issues)\/\d+\/reference-files\/[0-9a-f-]{36}\/download$/i.test(normalized)) {
    throw new TypeError('参考文件下载地址无效')
  }
  return normalized
}

export function uploadReviewReferenceFile(file, options = {}) {
  if (!(file instanceof File)) throw new TypeError('请选择需要上传的参考文件')
  const data = new FormData()
  data.append('file', file, file.name)
  return request({
    url: '/common/files/upload',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: 120_000,
    signal: options.signal,
    silentError: true,
    onUploadProgress: options.onUploadProgress
  })
}

export function downloadReviewReferenceFile(file, options = {}) {
  return request({
    url: assertReferenceDownloadUrl(file?.downloadUrl),
    method: 'get',
    responseType: 'blob',
    signal: options.signal,
    timeout: 120_000,
    silentError: true
  })
}

export function getMineReviewListPage(params = {}, options = {}) {
  return request({ url: '/shot-grid/review-lists/mine', method: 'get', params, signal: options.signal, silentError: true })
}

export function getRecentMineVersions(params = {}, options = {}) {
  return request({ url: '/shot-grid/versions/mine/recent', method: 'get', params, signal: options.signal, silentError: true })
}

export function getReviewListPage(projectId, params = {}, options = {}) {
  return request({
    url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/review-lists`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getReviewListDetail(reviewListId, options = {}) {
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function createManualReviewList(projectId, data, options = {}) {
  return request({
    url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/review-lists`,
    method: 'post', data, signal: options.signal, silentError: true
  })
}

export function updateManualReviewList(reviewListId, data, options = {}) {
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}`,
    method: 'put', data, signal: options.signal, silentError: true
  })
}

export function addManualReviewVersions(reviewListId, data, options = {}) {
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}/versions`,
    method: 'post', data, signal: options.signal, silentError: true
  })
}

export function removeManualReviewVersion(reviewListId, versionId, data, options = {}) {
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}/versions/${assertPositiveId(versionId, '版本')}`,
    method: 'delete', data, signal: options.signal, silentError: true
  })
}

export function reorderManualReviewVersions(reviewListId, data, options = {}) {
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}/versions/order`,
    method: 'put', data, signal: options.signal, silentError: true
  })
}

export function transitionManualReviewList(reviewListId, action, data, options = {}) {
  if (!['activate', 'complete', 'archive'].includes(action)) throw new TypeError('审核单动作无效')
  return request({
    url: `/shot-grid/review-lists/${assertPositiveId(reviewListId, '审核单')}/${action}`,
    method: 'post', data, signal: options.signal, silentError: true
  })
}

export function getTaskIssues(taskId, params = {}, options = {}) {
  return request({
    url: `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}/issues`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getVersionReviewContext(versionId, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/review-context`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function selectVersionCandidate(versionId, data, idempotencyKey, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/selected-candidate`,
    method: 'put',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    signal: options.signal,
    silentError: true
  })
}

export function addVersionIssueDraft(versionId, data, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/issues`,
    method: 'post',
    data,
    headers: { repeatSubmit: false },
    signal: options.signal,
    silentError: true
  })
}

// 兼容既有调用名称；新代码应使用能表达“退回前草稿”语义的函数名。
export const addVersionIssue = addVersionIssueDraft

export function updateVersionIssueDraft(versionId, draftId, data, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/issue-drafts/${assertPositiveId(draftId, '问题草稿')}`,
    method: 'put',
    data,
    headers: { repeatSubmit: false },
    signal: options.signal,
    silentError: true
  })
}

export function deleteVersionIssueDraft(versionId, draftId, data, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/issue-drafts/${assertPositiveId(draftId, '问题草稿')}`,
    method: 'delete',
    data,
    headers: { repeatSubmit: false },
    signal: options.signal,
    silentError: true
  })
}

export function getReviewActions(versionId, params = {}, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/review-actions`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function createReviewAction(versionId, data, idempotencyKey, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/review-actions`,
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    signal: options.signal,
    silentError: true
  })
}

export function retryFinalDelivery(versionId, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/final-delivery/retry`,
    method: 'post',
    signal: options.signal,
    silentError: true
  })
}
