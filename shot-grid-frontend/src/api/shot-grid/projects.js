import request from '@/utils/request'

const MAX_BIGINT_ID = Number.MAX_SAFE_INTEGER

export function assertPositiveId(value, label = '资源') {
  const normalized = Number(value)
  if (!Number.isSafeInteger(normalized) || normalized <= 0 || normalized > MAX_BIGINT_ID) {
    throw new TypeError(`${label} ID 必须为正整数`)
  }
  return normalized
}

function projectUrl(projectId, suffix = '') {
  return `/shot-grid/projects/${assertPositiveId(projectId, '项目')}${suffix}`
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

export function getStorageRootOptions(options = {}) {
  return request({
    url: '/shot-grid/storage-roots/options',
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function getProjectRoleOptions(options = {}) {
  return request({
    url: '/shot-grid/project-role-options',
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function previewProjectPath(storageRootId, data, options = {}) {
  return request({
    url: `/shot-grid/storage-roots/${assertPositiveId(storageRootId, 'NAS 根目录')}/project-path-preview`,
    method: 'post',
    data,
    signal: options.signal,
    headers: { repeatSubmit: false },
    silentError: true
  })
}

export function getMemberCandidatePage(params, options = {}) {
  return request({
    url: '/shot-grid/member-candidates',
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getProjectMemberCandidatePage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/member-candidates'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getProjectPage(params, options = {}) {
  return request({
    url: '/shot-grid/projects',
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function createProject(data, idempotencyKey) {
  return request({
    url: '/shot-grid/projects',
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    silentError: true
  })
}

export function getProjectDetail(projectId, options = {}) {
  return request({
    url: projectUrl(projectId),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function getProjectOverview(projectId, options = {}) {
  return request({
    url: projectUrl(projectId, '/overview'),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function updateProject(projectId, data) {
  return request({
    url: projectUrl(projectId),
    method: 'put',
    data,
    silentError: true
  })
}

export function archiveProject(projectId, data) {
  return request({
    url: projectUrl(projectId, '/archive'),
    method: 'post',
    data,
    silentError: true
  })
}

export function purgeProject(projectId, data) {
  return request({
    url: projectUrl(projectId, '/purge'),
    method: 'post',
    data,
    silentError: true
  })
}

export function getProjectMembers(projectId, params = {}, options = {}) {
  return request({
    url: projectUrl(projectId, '/members'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getProjectMemberRoleOptions(projectId, options = {}) {
  return request({
    url: projectUrl(projectId, '/role-options'),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function addProjectMember(projectId, data) {
  return request({
    url: projectUrl(projectId, '/members'),
    method: 'post',
    data,
    silentError: true
  })
}

export function updateProjectMember(projectId, userId, data) {
  return request({
    url: `${projectUrl(projectId, '/members')}/${assertPositiveId(userId, '用户')}`,
    method: 'put',
    data,
    silentError: true
  })
}

export function removeProjectMember(projectId, userId) {
  return request({
    url: `${projectUrl(projectId, '/members')}/${assertPositiveId(userId, '用户')}`,
    method: 'delete',
    silentError: true
  })
}

export function getProjectStorage(projectId, options = {}) {
  return request({
    url: projectUrl(projectId, '/storage'),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function getStorageOperationPage(projectId, params, options = {}) {
  return request({
    url: projectUrl(projectId, '/storage/operations'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getStorageOperationDetail(projectId, operationId, options = {}) {
  return request({
    url: `${projectUrl(projectId, '/storage/operations')}/${assertPositiveId(operationId, '目录操作')}`,
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function retryProjectStorage(projectId, data, idempotencyKey) {
  return request({
    url: projectUrl(projectId, '/storage/retry'),
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    silentError: true
  })
}

export function retryStorageOperation(operationId, data, idempotencyKey) {
  return request({
    url: `/shot-grid/storage-operations/${assertPositiveId(operationId, '目录操作')}/retry`,
    method: 'post',
    data,
    headers: idempotencyHeaders(idempotencyKey),
    silentError: true
  })
}
