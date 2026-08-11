import request from '@/utils/request'

const base = (projectId) => `/shot-grid/projects/${projectId}`
export const listScenes = (projectId, episodeId, params, config = {}) => request.get(`${base(projectId)}/episodes/${episodeId}/scenes`, { ...config, params })
export const getScene = (projectId, sceneId, config = {}) => request.get(`${base(projectId)}/scenes/${sceneId}`, config)
export const createScene = (projectId, episodeId, data) => request.post(`${base(projectId)}/episodes/${episodeId}/scenes`, data)
export const updateScene = (projectId, sceneId, data) => request.put(`${base(projectId)}/scenes/${sceneId}`, data)
export const archiveScene = (projectId, sceneId, lockVersion) => request.put(`${base(projectId)}/scenes/${sceneId}/archive`, { lockVersion })
