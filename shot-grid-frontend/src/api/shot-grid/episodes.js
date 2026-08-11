import request from '@/utils/request'

const url = (projectId, episodeId = '') => `/shot-grid/projects/${projectId}/episodes${episodeId ? `/${episodeId}` : ''}`

export const listEpisodes = (projectId, params, config = {}) => request.get(url(projectId), { ...config, params })
export const createEpisode = (projectId, data) => request.post(url(projectId), data)
export const updateEpisode = (projectId, episodeId, data) => request.put(url(projectId, episodeId), data)
export const archiveEpisode = (projectId, episodeId, lockVersion) => request.post(`${url(projectId, episodeId)}/archive`, { lockVersion })
