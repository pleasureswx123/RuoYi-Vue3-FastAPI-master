<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Delete, Document, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { downloadReviewReferenceFile } from '@/api/shot-grid/reviews'

const props = defineProps({
  files: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  removable: { type: Boolean, default: false }
})
const emit = defineEmits(['remove'])

const previewUrls = reactive({})
const previewStates = reactive({})
const downloadingFileId = ref('')
const controllers = new Map()

const imagePreviewUrls = computed(() => props.files
  .map(file => previewUrls[file.fileId])
  .filter(Boolean))

function isImage(file) {
  return String(file?.contentType || '').toLowerCase().startsWith('image/')
    || /\.(?:bmp|gif|jpe?g|png)$/i.test(String(file?.originalName || ''))
}

function formatFileSize(bytes) {
  const size = Number(bytes || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`
  return `${(size / 1024 / 1024).toFixed(1)} MiB`
}

function safeDownloadName(value) {
  const normalized = Array.from(String(value || 'reference-file'))
    .map(character => character.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(character) ? '_' : character)
    .join('')
    .trim()
  return normalized || 'reference-file'
}

function revokePreview(fileId) {
  if (!previewUrls[fileId]) return
  URL.revokeObjectURL(previewUrls[fileId])
  delete previewUrls[fileId]
}

async function loadImagePreview(file) {
  if (!isImage(file) || !file?.fileId || previewStates[file.fileId] === 'loading') return
  controllers.get(file.fileId)?.abort()
  revokePreview(file.fileId)
  const controller = new AbortController()
  controllers.set(file.fileId, controller)
  previewStates[file.fileId] = 'loading'
  try {
    const blob = await downloadReviewReferenceFile(file, { signal: controller.signal })
    if (controllers.get(file.fileId) !== controller || controller.signal.aborted) return
    previewUrls[file.fileId] = URL.createObjectURL(blob)
    previewStates[file.fileId] = 'ready'
  } catch (error) {
    if (!controller.signal.aborted && error?.code !== 'ERR_CANCELED') previewStates[file.fileId] = 'error'
  } finally {
    if (controllers.get(file.fileId) === controller) controllers.delete(file.fileId)
  }
}

async function downloadFile(file) {
  if (!file?.fileId || downloadingFileId.value) return
  downloadingFileId.value = file.fileId
  let objectUrl = ''
  try {
    const blob = await downloadReviewReferenceFile(file)
    objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = safeDownloadName(file.originalName)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch {
    ElMessage.error('参考文件下载失败，请稍后重试')
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    downloadingFileId.value = ''
  }
}

function resetPreviews() {
  controllers.forEach(controller => controller.abort())
  controllers.clear()
  Object.keys(previewUrls).forEach(revokePreview)
  Object.keys(previewStates).forEach(fileId => delete previewStates[fileId])
}

watch(
  () => props.files.map(file => `${file.fileId}:${file.downloadUrl}`).join('|'),
  () => {
    resetPreviews()
    props.files.forEach(loadImagePreview)
  },
  { immediate: true }
)

onBeforeUnmount(resetPreviews)
</script>

<template>
  <section v-if="files.length" class="review-reference-files" :class="{ 'is-compact': compact }" aria-label="参考内容">
    <header><strong>参考内容</strong><span>{{ files.length }} 个文件</span></header>
    <div class="review-reference-files__list">
      <article v-for="file in files" :key="file.fileId" class="review-reference-file">
        <el-skeleton v-if="isImage(file) && previewStates[file.fileId] === 'loading'" class="review-reference-file__preview" animated>
          <template #template><el-skeleton-item variant="image" /></template>
        </el-skeleton>
        <el-image
          v-else-if="previewUrls[file.fileId]"
          class="review-reference-file__preview"
          :src="previewUrls[file.fileId]"
          :preview-src-list="imagePreviewUrls"
          :initial-index="Math.max(0, imagePreviewUrls.indexOf(previewUrls[file.fileId]))"
          :alt="file.originalName"
          fit="cover"
          preview-teleported
          hide-on-click-modal
        />
        <div v-else class="review-reference-file__icon" aria-hidden="true"><el-icon><Document /></el-icon></div>
        <div class="review-reference-file__meta">
          <strong :title="file.originalName">{{ file.originalName }}</strong>
          <small>{{ formatFileSize(file.fileSize) }}</small>
        </div>
        <div class="review-reference-file__actions">
          <el-button
            text
            type="primary"
            :icon="Download"
            :loading="downloadingFileId === file.fileId"
            :disabled="Boolean(downloadingFileId)"
            :aria-label="`下载参考文件 ${file.originalName}`"
            @click="downloadFile(file)"
          >下载</el-button>
          <el-button v-if="removable" text type="danger" :icon="Delete" :aria-label="`移除参考文件 ${file.originalName}`" @click="emit('remove', file)">移除</el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.review-reference-files{display:grid;gap:8px;padding:10px;background:color-mix(in srgb,var(--sg-accent) 6%,transparent);border:1px solid color-mix(in srgb,var(--sg-accent) 26%,var(--sg-border));border-radius:9px}.review-reference-files>header{display:flex;gap:8px;align-items:center;justify-content:space-between}.review-reference-files>header strong{font-size:10px}.review-reference-files>header span{color:var(--sg-text-muted);font-size:8px}.review-reference-files__list{display:grid;gap:7px}.review-reference-file{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px;align-items:center;min-width:0;padding:7px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:8px}.review-reference-file__preview,.review-reference-file__icon{width:38px;height:38px;overflow:hidden;border-radius:6px}.review-reference-file__preview:deep(.el-skeleton__image){width:100%;height:100%}.review-reference-file__icon{display:grid;color:var(--sg-accent);font-size:18px;background:var(--sg-accent-soft);place-items:center}.review-reference-file__meta{display:grid;min-width:0;gap:3px}.review-reference-file__meta strong{overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.review-reference-file__meta small{color:var(--sg-text-muted);font-size:8px}.review-reference-file__actions{display:flex;gap:3px;align-items:center}.review-reference-file .el-button{margin:0}.review-reference-files.is-compact{padding:8px}.review-reference-files.is-compact .review-reference-file{grid-template-columns:32px minmax(0,1fr) auto}.review-reference-files.is-compact .review-reference-file__preview,.review-reference-files.is-compact .review-reference-file__icon{width:32px;height:32px}
</style>
