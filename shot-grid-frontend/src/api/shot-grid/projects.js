import request from '@/utils/request'

const BASE_URL = '/shot-grid/projects'

export function listProjects(params, config = {}) {
  return request.get(BASE_URL, { ...config, params })
}

export function createProject(data, idempotencyKey) {
  return request.post(BASE_URL, data, {
    headers: { 'X-Idempotency-Key': idempotencyKey, interval: 2000 }
  })
}

export function getProject(projectId, config = {}) {
  return request.get(`${BASE_URL}/${projectId}`, config)
}

export function getProjectOverview(projectId, config = {}) {
  return request.get(`${BASE_URL}/${projectId}/overview`, config)
}

export function getProjectStorage(projectId, config = {}) {
  return request.get(`${BASE_URL}/${projectId}/storage`, config)
}
