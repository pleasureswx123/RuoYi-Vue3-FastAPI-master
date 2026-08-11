import request from '@/utils/request'

const url = (projectId, assetId = '') => `/shot-grid/projects/${projectId}/assets${assetId ? `/${assetId}` : ''}`
export const listAssets = (projectId, params, config = {}) => request.get(url(projectId), { ...config, params })
export const createAsset = (projectId, data) => request.post(url(projectId), data)
export const getAsset = (projectId, assetId, config = {}) => request.get(url(projectId, assetId), config)
export const updateAsset = (projectId, assetId, data) => request.put(url(projectId, assetId), data)
export const archiveAsset = (projectId, assetId, lockVersion) => request.post(`${url(projectId, assetId)}/archive`, { lockVersion })
export const listAssetItems = (projectId, assetId, config = {}) => request.get(`${url(projectId, assetId)}/items`, config)
export const createAssetItem = (projectId, assetId, data) => request.post(`${url(projectId, assetId)}/items`, data)
