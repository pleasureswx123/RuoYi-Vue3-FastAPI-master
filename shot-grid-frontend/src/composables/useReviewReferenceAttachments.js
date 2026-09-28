import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadReviewReferenceFile } from '@/api/shot-grid/reviews'

export const MAX_REFERENCE_FILES = 5
export const MAX_REFERENCE_FILE_SIZE = 20 * 1024 * 1024
export const REFERENCE_ACCEPT = '.bmp,.jpg,.jpeg,.png,.gif,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.mp4,.mov'
const extensions = new Set(REFERENCE_ACCEPT.split(',').map(item => item.slice(1)))
const fileIdPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i

// 单条与批量反馈共用选择、上传及取消逻辑；文件引用仍由业务接口在事务内建立。
export function useReviewReferenceAttachments({ canEdit = () => true, isCurrent = () => true } = {}) {
  const referenceAttachments = ref([])
  let controller = null
  let generation = 0
  let disposed = false
  let sequence = 0
  const revoke = file => { if (file?.previewUrl) URL.revokeObjectURL(file.previewUrl) }

  function resetReferenceAttachments(files = []) {
    generation += 1
    controller?.abort()
    controller = null
    referenceAttachments.value.forEach(revoke)
    referenceAttachments.value = files
  }
  function addReferenceFile(uploadFile) {
    const file = uploadFile?.raw
    if (disposed || controller || !canEdit() || !(file instanceof File)) return
    if (referenceAttachments.value.length >= MAX_REFERENCE_FILES) return ElMessage.warning('最多添加 5 个参考文件')
    if (!file.name.includes('.') || !extensions.has(file.name.split('.').pop().toLowerCase())) return ElMessage.warning('仅支持图片、PDF、Office、文本和 MP4/MOV 参考文件')
    if (file.size > MAX_REFERENCE_FILE_SIZE) return ElMessage.warning('单个参考文件不能超过 20 MiB')
    if (referenceAttachments.value.some(item => item.originalName === file.name && Number(item.fileSize) === file.size)) return ElMessage.warning('该参考文件已经添加')
    referenceAttachments.value.push({
      clientKey: `reference-${++sequence}`, raw: file, originalName: file.name,
      contentType: file.type || null, fileSize: file.size,
      previewUrl: /\.(?:bmp|gif|jpe?g|png)$/i.test(file.name) ? URL.createObjectURL(file) : '',
      uploadProgress: 0, fileId: ''
    })
  }
  function removeReferenceFile(file) {
    if (disposed || controller || !canEdit()) return
    const target = referenceAttachments.value.find(item => file.fileId ? item.fileId === file.fileId : item.clientKey === file.clientKey)
    revoke(target)
    referenceAttachments.value = referenceAttachments.value.filter(item => item !== target)
  }
  async function uploadPendingReferenceFiles() {
    if (controller) throw new Error('参考文件正在上传，请稍候')
    const token = generation
    const uploadController = new AbortController()
    controller = uploadController
    const assertCurrent = () => {
      if (disposed || generation !== token || uploadController.signal.aborted || !isCurrent()) throw new Error('当前反馈已关闭或任务已变化，请重新核对')
    }
    try {
      assertCurrent()
      for (const attachment of referenceAttachments.value.filter(file => file.raw && !file.fileId)) {
        assertCurrent()
        const response = await uploadReviewReferenceFile(attachment.raw, {
          signal: uploadController.signal,
          onUploadProgress: event => {
            if (generation === token && !uploadController.signal.aborted) attachment.uploadProgress = event.total ? Math.min(100, Math.round(event.loaded / event.total * 100)) : 0
          }
        })
        assertCurrent()
        if (!fileIdPattern.test(response?.fileId || '')) throw new Error('参考文件上传结果无效，请重试')
        attachment.fileId = response.fileId
        attachment.uploadProgress = 100
      }
      assertCurrent()
      return referenceAttachments.value.map(file => file.fileId)
    } finally { if (controller === uploadController) controller = null }
  }
  onBeforeUnmount(() => { disposed = true; resetReferenceAttachments() })
  return { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles }
}
