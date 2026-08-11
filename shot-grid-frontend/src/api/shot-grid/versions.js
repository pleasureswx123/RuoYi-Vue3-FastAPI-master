import request from '@/utils/request'

const base = (projectId, taskId) => `/shot-grid/projects/${projectId}/tasks/${taskId}/version-submissions`

export const initializeVersionSubmission = (projectId, taskId, data) => request.post(base(projectId, taskId), data)
export const getVersionSubmission = (projectId, taskId, submissionId) => request.get(`${base(projectId, taskId)}/${submissionId}`)
export const retryVersionSubmission = (projectId, taskId, submissionId) => request.post(`${base(projectId, taskId)}/${submissionId}/retry`, {})

export function uploadProtectedVersionFile(file, onProgress) {
  const data = new FormData()
  data.append('file', file)
  return request.post('/common/files/upload', data, {
    timeout: 0,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    onUploadProgress: ({ loaded, total }) => onProgress?.(total ? Math.round(loaded * 100 / total) : 0)
  })
}
