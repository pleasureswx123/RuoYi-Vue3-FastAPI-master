import request from '@/utils/request'

const BASE_URL = '/shot-grid/project-creation'

export const listProjectStorageRoots = (config = {}) => request.get(`${BASE_URL}/storage-roots`, config)
export const searchProjectUsers = (keyword, config = {}) => request.get(`${BASE_URL}/users`, { ...config, params: { keyword: keyword || undefined, limit: 30 } })
export const previewProjectPath = (params, config = {}) => request.get(`${BASE_URL}/path-preview`, { ...config, params })
