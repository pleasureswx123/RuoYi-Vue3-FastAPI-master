import request, { download } from '@/utils/request'

export const getWorkbench = (params, config = {}) => request.get('/shot-grid/workbench', { ...config, params })
export const globalSearch = (params, config = {}) => request.get('/shot-grid/search', { ...config, params })
export const listBusinessFiles = (params, config = {}) => request.get('/shot-grid/files', { ...config, params })
export const downloadBusinessFile = (url, config = {}) => download(url, undefined, config)
