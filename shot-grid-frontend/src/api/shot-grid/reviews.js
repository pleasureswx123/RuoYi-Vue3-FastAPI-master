import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function idempotencyHeaders(idempotencyKey) {
  const normalized = typeof idempotencyKey === 'string' ? idempotencyKey.trim() : ''
  if (!normalized || normalized.length > 100) {
    throw new TypeError('幂等键长度必须为 1—100 个字符')
  }
  return { 'X-Idempotency-Key': normalized, repeatSubmit: false }
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

export function addVersionIssue(versionId, data, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/issues`,
    method: 'post',
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
