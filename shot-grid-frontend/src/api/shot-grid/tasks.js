import request from '@/utils/request'

const projectTasks = (projectId, suffix = '') => `/shot-grid/projects/${projectId}/tasks${suffix}`

export const listTasks = (projectId, params, config = {}) => request.get(projectTasks(projectId), { ...config, params })
export const listMyTasks = (params, config = {}) => request.get('/shot-grid/tasks/mine', { ...config, params })
export const getTask = (projectId, taskId, config = {}) => request.get(projectTasks(projectId, `/${taskId}`), config)
export const assignShotTask = (projectId, shotId, data) => request.post(`/shot-grid/projects/${projectId}/shots/${shotId}/assignment`, data)
export const assignAssetItemTask = (projectId, assetItemId, data) => request.post(`/shot-grid/projects/${projectId}/asset-items/${assetItemId}/assignment`, data)
export const startTask = (projectId, taskId, data = {}) => request.post(projectTasks(projectId, `/${taskId}/start`), data)
