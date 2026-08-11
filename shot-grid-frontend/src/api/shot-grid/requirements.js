import request from '@/utils/request'
const base = (projectId) => `/shot-grid/projects/${projectId}/asset-requirements`
export const listRequirements = (projectId, params) => request.get(base(projectId), { params })
export const listRequirementCandidates = (projectId, requirementId, params) => request.get(`${base(projectId)}/${requirementId}/candidates`, { params })
export const bindRequirement = (projectId, requirementId, assetId, lockVersion) => request.put(`${base(projectId)}/${requirementId}/bind`, { assetId, lockVersion })
export const closeRequirement = (projectId, requirementId, lockVersion, reason) => request.put(`${base(projectId)}/${requirementId}/close`, { lockVersion, reason })
