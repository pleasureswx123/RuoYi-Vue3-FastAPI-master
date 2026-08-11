import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

const IDEMPOTENCY_KEY_MAX_LENGTH = 100

function idempotencyHeaders(idempotencyKey) {
  const normalized = typeof idempotencyKey === 'string' ? idempotencyKey.trim() : ''
  if (!normalized || normalized.length > IDEMPOTENCY_KEY_MAX_LENGTH) {
    throw new TypeError('幂等键长度必须为 1—100 个字符')
  }
  return {
    'X-Idempotency-Key': normalized,
    repeatSubmit: false
  }
}

function assertFileId(value) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(normalized)) {
    throw new TypeError('文件 ID 必须是有效 UUID')
  }
  return normalized
}

export function uploadProtectedVersionFile(file, options = {}) {
  if (!(file instanceof File)) {
    throw new TypeError('请选择需要提交的版本文件')
  }
  const data = new FormData()
  data.append('file', file, file.name)
  return request({
    url: '/common/files/upload',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data',
      repeatSubmit: false
    },
    timeout: 120_000,
    signal: options.signal,
    silentError: true,
    onUploadProgress: options.onUploadProgress
  })
}

export function createVersionSubmission(taskId, data, idempotencyKey, options = {}) {
  return request({
    url: `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}/version-submissions`,
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    signal: options.signal,
    timeout: 120_000,
    silentError: true
  })
}

export function preflightVersionSubmission(taskId, data, options = {}) {
  return request({
    url: `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}/version-submissions/preflight`,
    method: 'post',
    data,
    headers: { repeatSubmit: false },
    signal: options.signal,
    silentError: true
  })
}

export function getVersionSubmissionStatus(submissionId, options = {}) {
  return request({
    url: `/shot-grid/version-submissions/${assertPositiveId(submissionId, '版本提交')}`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function getCurrentTaskVersionSubmission(taskId, options = {}) {
  return request({
    url: `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}/version-submissions/current`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function retryVersionSubmission(submissionId, options = {}) {
  return request({
    url: `/shot-grid/version-submissions/${assertPositiveId(submissionId, '版本提交')}/retry`,
    method: 'post',
    headers: { repeatSubmit: false },
    signal: options.signal,
    timeout: 120_000,
    silentError: true
  })
}

export function getTaskVersions(taskId, params = {}, options = {}) {
  return request({
    url: `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}/versions`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getVersionDetail(versionId, options = {}) {
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function downloadProtectedVersionFile(versionId, fileId, options = {}) {
  const headers = {}
  if (typeof options.range === 'string' && options.range.trim()) {
    headers.Range = options.range.trim()
  }
  return request({
    url: `/shot-grid/versions/${assertPositiveId(versionId, '版本')}/files/${assertFileId(fileId)}/download`,
    method: 'get',
    responseType: 'blob',
    headers,
    signal: options.signal,
    timeout: 120_000,
    silentError: true
  })
}

export { assertFileId }
