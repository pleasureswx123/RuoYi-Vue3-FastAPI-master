import request from '@/utils/request'

const projectImportsUrl = (projectId) => `/shot-grid/projects/${projectId}/imports`
const importUrl = (projectId, importType) =>
  `/shot-grid/projects/${projectId}/${importType === 'asset' ? 'assets' : 'shots'}/import`

/** 上传 Excel 并执行预检。FormData 必须交给浏览器生成带 boundary 的 Content-Type。 */
export function previewImport(projectId, importType, file, onUploadProgress) {
  const data = new FormData()
  data.append('file', file)
  return request.post(`${importUrl(projectId, importType)}/preview`, data, {
    headers: { repeatSubmit: false, encrypt: false },
    onUploadProgress
  })
}

/** 正式提交；selectedRows 的每一项必须同时包含 sheetName 和 rowNumber。 */
export function commitImport(projectId, importType, importToken, selectedRows, idempotencyKey) {
  return request.post(`${importUrl(projectId, importType)}/commit`, { importToken, selectedRows }, {
    headers: { 'X-Idempotency-Key': idempotencyKey, repeatSubmit: false }
  })
}

export const listImportBatches = (projectId, params, config = {}) =>
  request.get(projectImportsUrl(projectId), { ...config, params })

/** 查询批次详情也是正式结果的耐久重放入口，刷新页面后不依赖 Preview Token。 */
export const getImportBatch = (projectId, batchId, config = {}) =>
  request.get(`${projectImportsUrl(projectId)}/${batchId}`, config)

