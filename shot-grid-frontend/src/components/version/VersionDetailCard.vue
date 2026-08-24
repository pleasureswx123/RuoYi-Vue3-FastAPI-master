<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Document } from '@element-plus/icons-vue'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { tagTypeFromTone } from '@/utils/tag'
import { fileRoleLabel } from '@/views/file/filePresentation'
import ProtectedVersionPreview from './ProtectedVersionPreview.vue'
import { formatFileSize, formatVersionDateTime, versionErrorState, versionStatusMeta } from './versionPresentation'

const props = defineProps({
  version: { type: Object, required: true },
  canDownload: { type: Boolean, default: false },
  showPreview: { type: Boolean, default: true }
})

const downloadingFileId = ref(null)
const downloadError = ref(null)
const activeAiSections = ref([])
let downloadController = null
let versionGeneration = 0
let disposed = false

const statusMeta = computed(() => versionStatusMeta(props.version?.versionStatus))
const hiddenDerivedFileRoles = new Set(['thumbnail', 'proxy_media'])
const deliveryFiles = computed(() => (
  Array.isArray(props.version?.files)
    ? props.version.files.filter(file => !hiddenDerivedFileRoles.has(file?.role))
    : []
))

function safeDownloadName(value) {
  const normalized = Array.from(String(value || 'version-file'))
    .map(character => character.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(character) ? '_' : character)
    .join('')
    .trim()
  return normalized || 'version-file'
}

async function downloadFile(file) {
  if (!file?.fileId || downloadingFileId.value) return
  downloadController?.abort()
  const controller = new AbortController()
  downloadController = controller
  const generation = versionGeneration
  const versionId = Number(props.version.versionId)
  const fileId = String(file.fileId)
  downloadingFileId.value = fileId
  downloadError.value = null
  let objectUrl = null
  try {
    const blob = await downloadProtectedVersionFile(versionId, fileId, { signal: controller.signal })
    if (
      disposed ||
      downloadController !== controller ||
      controller.signal.aborted ||
      versionGeneration !== generation ||
      Number(props.version?.versionId) !== versionId
    ) return
    objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = safeDownloadName(file.businessFileName || file.originalName)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && versionGeneration === generation) {
      downloadError.value = versionErrorState(error, '版本文件下载失败')
    }
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    if (downloadController === controller) {
      downloadController = null
      downloadingFileId.value = null
    }
  }
}

watch(
  () => props.version?.versionId,
  () => {
    versionGeneration += 1
    downloadController?.abort()
    downloadController = null
    downloadingFileId.value = null
    downloadError.value = null
    activeAiSections.value = []
  }
)

onBeforeUnmount(() => {
  disposed = true
  versionGeneration += 1
  downloadController?.abort()
})
</script>

<template>
  <el-card class="version-detail-card" shadow="never">
    <header>
      <div>
        <p class="sg-eyebrow">VERSION DETAIL</p>
        <h3>{{ version.versionNumber }}</h3>
        <p>{{ version.changelog }}</p>
      </div>
      <el-tag size="small" effect="light" round :type="tagTypeFromTone(statusMeta.tone)">{{ statusMeta.label }}</el-tag>
    </header>

    <ProtectedVersionPreview v-if="showPreview" :version="version" :can-preview="canDownload" />

    <el-descriptions class="version-facts" :column="2" border size="small">
      <el-descriptions-item label="提交人">{{ version.submitterName || `用户 #${version.submittedBy}` }}</el-descriptions-item>
      <el-descriptions-item label="提交时间">{{ formatVersionDateTime(version.submittedTime) }}</el-descriptions-item>
      <el-descriptions-item label="审核单">{{ version.autoReviewList?.reviewListName || '—' }}</el-descriptions-item>
    </el-descriptions>

    <section class="version-files">
      <div class="subheading"><strong>版本文件</strong><span>{{ deliveryFiles.length }} 个交付文件</span></div>
      <div v-if="deliveryFiles.length" class="file-list">
        <div v-for="file in deliveryFiles" :key="file.fileId" class="file-row">
          <span class="file-icon"><el-icon><Document /></el-icon></span>
          <div>
            <strong>{{ file.businessFileName || file.originalName }}</strong>
            <small>{{ formatFileSize(file.fileSize) }} · {{ file.contentType || '未知类型' }}</small>
          </div>
          <div class="file-tags">
            <el-tag size="small" effect="plain" round type="info">{{ fileRoleLabel(file.role) }}</el-tag>
            <el-tag v-if="file.isPrimary" size="small" effect="plain" round type="warning">主审核文件</el-tag>
          </div>
          <el-button
            v-if="canDownload"
            :icon="Download"
            :loading="downloadingFileId === file.fileId"
            :disabled="Boolean(downloadingFileId)"
            @click="downloadFile(file)"
          >下载</el-button>
        </div>
      </div>
      <el-empty v-else class="empty-files" :image-size="54" description="当前版本没有可访问的交付文件" />
    </section>

    <el-alert v-if="downloadError" class="download-error" :title="downloadError.title" :description="downloadError.message" type="error" :closable="false" show-icon />

    <el-collapse v-if="version.aiParams" v-model="activeAiSections" class="ai-snapshot">
      <el-collapse-item title="AI 参数快照" name="ai-params"><pre>{{ JSON.stringify(version.aiParams, null, 2) }}</pre></el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<style scoped lang="scss">
.version-detail-card { background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-md); }
.version-detail-card:deep(.el-card__body) { padding: 22px; }
.version-detail-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.version-detail-card h3 { margin: 3px 0 7px; font-size: 22px; }
.version-detail-card header p:not(.sg-eyebrow) { max-width: 700px; margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.version-facts { margin: 20px 0; }
.version-facts:deep(.el-descriptions__body),
.version-facts:deep(.el-descriptions__cell) { background: rgba(0, 0, 0, 0.13); border-color: var(--sg-border); }
.subheading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 12px; }
.subheading span { color: var(--sg-text-muted); }
.file-list { display: grid; gap: 8px; }
.file-row { display: grid; padding: 12px; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 12px; align-items: center; }
.file-icon { display: grid; width: 34px; height: 34px; color: var(--sg-accent); background: var(--sg-accent-soft); border-radius: 9px; place-items: center; }
.file-row strong,
.file-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-row strong { font-size: 12px; }
.file-row small { margin-top: 5px; color: var(--sg-text-muted); font-size: 10px; }
.file-tags { display: flex; align-items: center; justify-content: flex-end; gap: 6px; flex-wrap: wrap; }
.empty-files { padding: 18px; background: rgba(255, 255, 255, 0.02); border-radius: 10px; }
.download-error { margin-top: 14px; }
.download-error code { color: inherit; font-size: 10px; }
.ai-snapshot { margin-top: 18px; color: var(--sg-text-secondary); font-size: 12px; }
.ai-snapshot:deep(.el-collapse-item__header),
.ai-snapshot:deep(.el-collapse-item__wrap) { color: var(--sg-text-secondary); background: transparent; border-color: var(--sg-border); }
.ai-snapshot pre { max-height: 260px; padding: 14px; overflow: auto; color: var(--sg-text-secondary); background: rgba(0, 0, 0, 0.18); border-radius: 9px; white-space: pre-wrap; word-break: break-word; }

@media (max-width: 760px) {
  .file-row { grid-template-columns: auto minmax(0, 1fr); }
  .file-tags,
  .file-row .el-button { grid-column: 2; justify-self: start; }
  .file-tags { justify-content: flex-start; }
}
</style>
