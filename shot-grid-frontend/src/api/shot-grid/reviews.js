import request from '@/utils/request'

const base = projectId => `/shot-grid/projects/${projectId}/review-lists`

export const listReviewLists = (projectId, params = {}) => request.get(base(projectId), { params })
export const getReviewList = (projectId, reviewListId) => request.get(`${base(projectId)}/${reviewListId}`)
export const listEligibleReviewVersions = (projectId, keyword = '') => request.get(`${base(projectId)}/eligible-versions`, { params: { keyword: keyword || undefined } })
export const createReviewList = (projectId, data) => request.post(base(projectId), data)
export const reorderReviewList = (projectId, reviewListId, data) => request.put(`${base(projectId)}/${reviewListId}/order`, data)
export const archiveReviewList = (projectId, reviewListId, lockVersion) => request.post(`${base(projectId)}/${reviewListId}/archive`, { lockVersion })
