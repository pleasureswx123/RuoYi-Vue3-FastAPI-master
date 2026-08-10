import request from '@/utils/request'

function memberUrl(projectId, userId = '') {
  return `/shot-grid/projects/${projectId}/members${userId ? `/${userId}` : ''}`
}

export function listProjectMembers(projectId, config = {}) {
  return request.get(memberUrl(projectId), config)
}

export function addProjectMember(projectId, data) {
  return request.post(memberUrl(projectId), data)
}

export function updateProjectMember(projectId, userId, data) {
  return request.put(memberUrl(projectId, userId), data)
}

export function removeProjectMember(projectId, userId) {
  return request.delete(memberUrl(projectId, userId))
}
