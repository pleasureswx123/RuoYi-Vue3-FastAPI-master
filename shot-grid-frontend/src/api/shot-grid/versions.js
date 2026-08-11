import request from '@/utils/request'

const base = (projectId, taskId) => `/shot-grid/projects/${projectId}/tasks/${taskId}/version-submissions`

export const initializeVersionSubmission = (projectId, taskId, data) => request.post(base(projectId, taskId), data)
export const getVersionSubmission = (projectId, taskId, submissionId) => request.get(`${base(projectId, taskId)}/${submissionId}`)
export const retryVersionSubmission = (projectId, taskId, submissionId) => request.post(`${base(projectId, taskId)}/${submissionId}/retry`, {})
export const listTaskVersions = (projectId, taskId, config = {}) => request.get(`/shot-grid/projects/${projectId}/tasks/${taskId}/versions`, config)
export const getTaskVersion = (projectId, taskId, versionId, config = {}) => request.get(`/shot-grid/projects/${projectId}/tasks/${taskId}/versions/${versionId}`, config)
export const getFinalTaskVersion = (projectId, taskId, config = {}) => request.get(`/shot-grid/projects/${projectId}/tasks/${taskId}/versions/final`, config)

const noteBase = (projectId, versionId) => `/shot-grid/projects/${projectId}/versions/${versionId}/notes`
export const listVersionNotes = (projectId, versionId, config = {}) => request.get(noteBase(projectId, versionId), config)
export const createVersionNote = (projectId, versionId, data) => request.post(noteBase(projectId, versionId), data)
export const replyVersionNote = (projectId, versionId, noteId, data) => request.post(`${noteBase(projectId, versionId)}/${noteId}/replies`, data)
export const updateVersionNoteStatus = (projectId, versionId, noteId, status) => request.patch(`${noteBase(projectId, versionId)}/${noteId}/status`, { status })

export const versionFileUrl = (projectId, taskId, versionId, fileId, disposition = 'inline') =>
  `/shot-grid/projects/${projectId}/tasks/${taskId}/versions/${versionId}/files/${fileId}?disposition=${disposition}`

export function uploadProtectedVersionFile(file, onProgress) {
  const data = new FormData()
  data.append('file', file)
  return request.post('/common/files/upload', data, {
    timeout: 0,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    onUploadProgress: ({ loaded, total }) => onProgress?.(total ? Math.round(loaded * 100 / total) : 0)
  })
}
