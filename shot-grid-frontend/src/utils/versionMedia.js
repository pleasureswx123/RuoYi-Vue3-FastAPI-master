export const VERSION_MEDIA_ERROR_MESSAGES = {
  SG_VERSION_FILE_TOO_LARGE: '文件超过服务端允许的大小，请压缩或更换文件。',
  SG_VERSION_EXTENSION_INVALID: '文件扩展名不在服务端允许范围内。',
  SG_VERSION_DECLARED_MIME_INVALID: '文件声明的媒体类型不受支持。',
  SG_VERSION_FILE_SIGNATURE_INVALID: '文件内容与扩展名或媒体类型不一致，请勿修改扩展名伪装文件。',
  SG_VERSION_TASK_MEDIA_MISMATCH: '镜头任务只能提交视频，资产任务只能提交图片。',
  SG_VERSION_PRODUCTION_ITEM_REQUIRED: '资产制作分项名称缺失，请先补齐后再提交。'
}

export function versionMediaErrorMessage(error, fallback = '版本文件校验失败，请检查文件后重试。') {
  return VERSION_MEDIA_ERROR_MESSAGES[error?.errorKey] || error?.message || fallback
}

export function validateSelectedMedia(file, policy) {
  if (!file || !policy) return null
  const extension = `.${String(file.name || '').split('.').pop().toLowerCase()}`
  if (!policy.extensions.includes(extension)) return '文件扩展名与当前任务不匹配'
  if (file.type && !policy.mimeTypes.includes(file.type.toLowerCase())) return '浏览器识别的媒体类型与当前任务不匹配'
  if (file.size <= 0 || file.size > policy.maxSizeBytes) return `文件须大于 0 且不超过 ${formatBytes(policy.maxSizeBytes)}`
  return null
}

export function formatBytes(bytes) {
  if (bytes >= 1024 ** 3) return `${bytes / 1024 ** 3} GiB`
  return `${bytes / 1024 ** 2} MiB`
}
