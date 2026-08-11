import request from '@/utils/request'

const url = (projectId, shotId = '') => `/shot-grid/projects/${projectId}/shots${shotId ? `/${shotId}` : ''}`
export const listShots = (projectId, params, config = {}) => request.get(url(projectId), { ...config, params })
export const createShot = (projectId, data) => request.post(url(projectId), data)
export const getShot = (projectId, shotId, config = {}) => request.get(url(projectId, shotId), config)
export const updateShot = (projectId, shotId, data) => request.put(url(projectId, shotId), data)
export const archiveShot = (projectId, shotId, lockVersion) => request.put(`${url(projectId, shotId)}/archive`, { lockVersion })
