<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Document, VideoPlay } from '@element-plus/icons-vue'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { tagTypeFromTone } from '@/utils/tag'
import { fileRoleLabel } from '@/views/file/filePresentation'
import ProtectedVersionPreview from './ProtectedVersionPreview.vue'
import { formatFileSize, formatVersionDateTime, versionErrorState, versionStatusMeta } from './versionPresentation'

const props = defineProps({
  version: { type: Object, required: true },
  canDownload: { type: Boolean, default: false },
  showPreview: { type: Boolean, default: true },
  showFilePreviewAction: { type: Boolean, default: false }
})

const downloadingFileId = ref(null)
const downloadError = ref(null)
const activeAiSections = ref([])
const activeCandidateId = ref(null)
const previewingFile = ref(null)
const filePreviewVisible = ref(false)
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
const versionCandidates = computed(() => (
  Array.isArray(props.version?.candidates)
    ? [...props.version.candidates]
        .filter(candidate => Number.isSafeInteger(Number(candidate?.candidateId)) && Number(candidate.candidateId) > 0)
        .sort((left, right) => Number(left.sortOrder ?? left.candidateNo ?? 0) - Number(right.sortOrder ?? right.candidateNo ?? 0))
    : []
))
const activeCandidate = computed(() => (
  versionCandidates.value.find(candidate => Number(candidate.candidateId) === Number(activeCandidateId.value))
  || versionCandidates.value[0]
  || null
))
const previewVersion = computed(() => activeCandidate.value
  ? { ...props.version, files: activeCandidate.value.files || [] }
  : props.version)
const filePreviewCandidate = computed(() => fileCandidate(previewingFile.value))
const filePreviewVersion = computed(() => {
  const targetFile = previewingFile.value
  if (!targetFile) return null
  const candidateFiles = Array.isArray(filePreviewCandidate.value?.files)
    ? filePreviewCandidate.value.files
    : []
  const versionFiles = Array.isArray(props.version?.files) ? props.version.files : []
  const relatedFiles = candidateFiles.length
    ? candidateFiles
    : versionFiles.filter(file => (
        targetFile.candidateId
        && Number(file?.candidateId) === Number(targetFile.candidateId)
      ))
  const files = relatedFiles.some(file => String(file?.fileId) === String(targetFile.fileId))
    ? relatedFiles
    : [targetFile, ...relatedFiles]
  return { ...props.version, files }
})
const filePreviewTitle = computed(() => {
  const candidateNumber = filePreviewCandidate.value?.candidateNumber
  return candidateNumber ? `预览 ${candidateNumber}` : '预览版本文件'
})
const candidateSelectionKey = computed(() => [
  props.version?.versionId,
  props.version?.selectedCandidateId,
  versionCandidates.value.map(candidate => `${candidate.candidateId}:${candidate.isSelected ? 1 : 0}`).join(',')
].join('|'))

function candidateSourceFile(candidate) {
  return candidate?.files?.find(file => file.role === 'review_media')
    || candidate?.files?.find(file => !hiddenDerivedFileRoles.has(file?.role))
    || candidate?.files?.[0]
    || null
}

function candidateFileName(candidate) {
  const file = candidateSourceFile(candidate)
  return file?.businessFileName || file?.originalName || '暂无可访问文件'
}

function fileCandidate(file) {
  return versionCandidates.value.find(candidate => Number(candidate.candidateId) === Number(file?.candidateId)) || null
}

function selectPreviewCandidate(candidate) {
  if (!candidate?.candidateId) return
  activeCandidateId.value = Number(candidate.candidateId)
}

function isPreviewableFile(file) {
  const contentType = String(file?.contentType || '').toLowerCase()
  return contentType.startsWith('video/') || contentType.startsWith('image/')
}

function openFilePreview(file) {
  if (!props.canDownload || !isPreviewableFile(file)) return
  previewingFile.value = file
  filePreviewVisible.value = true
}

function resetFilePreview() {
  filePreviewVisible.value = false
  previewingFile.value = null
}

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
    resetFilePreview()
  }
)

watch(
  candidateSelectionKey,
  () => {
    const selectedCandidateId = props.version?.selectedCandidateId
    const preferred = versionCandidates.value.find(candidate => Number(candidate.candidateId) === Number(selectedCandidateId))
      || versionCandidates.value.find(candidate => candidate.isSelected)
      || versionCandidates.value[0]
      || null
    activeCandidateId.value = preferred ? Number(preferred.candidateId) : null
  },
  { immediate: true }
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

    <section v-if="showPreview && versionCandidates.length > 1" class="candidate-preview-switcher" aria-label="切换版本候选预览">
      <div class="candidate-preview-switcher__heading">
        <div><strong>本轮候选</strong><span>共 {{ versionCandidates.length }} 个，可逐个切换预览</span></div>
        <el-tag v-if="activeCandidate?.isSelected" type="success" size="small" effect="plain" round>已选最佳候选</el-tag>
      </div>
      <el-radio-group v-model="activeCandidateId" class="candidate-preview-options" aria-label="选择要预览的候选文件">
        <el-radio-button v-for="candidate in versionCandidates" :key="candidate.candidateId" :value="Number(candidate.candidateId)">
          <span><strong>{{ candidate.candidateNumber }}</strong><small>{{ candidateFileName(candidate) }}</small></span>
        </el-radio-button>
      </el-radio-group>
      <p><strong>当前预览 {{ activeCandidate?.candidateNumber }}</strong><span>{{ activeCandidate?.candidateNote || '该候选未填写补充说明。' }}</span></p>
    </section>

    <ProtectedVersionPreview v-if="showPreview" :version="previewVersion" :can-preview="canDownload" />

    <el-descriptions class="version-facts" :column="2" border size="small">
      <el-descriptions-item label="提交人">{{ version.submitterName || `用户 #${version.submittedBy}` }}</el-descriptions-item>
      <el-descriptions-item label="提交时间">{{ formatVersionDateTime(version.submittedTime) }}</el-descriptions-item>
      <el-descriptions-item label="审核单">{{ version.autoReviewList?.reviewListName || '—' }}</el-descriptions-item>
    </el-descriptions>

    <section class="version-files">
      <div class="subheading"><strong>版本文件</strong><span>{{ deliveryFiles.length }} 个交付文件</span></div>
      <div v-if="deliveryFiles.length" class="file-list">
        <div v-for="file in deliveryFiles" :key="file.fileId" class="file-row" :class="{ 'is-previewing': showPreview && Number(file.candidateId) === Number(activeCandidateId) }">
          <span class="file-icon"><el-icon><Document /></el-icon></span>
          <div>
            <strong>{{ file.businessFileName || file.originalName }}</strong>
            <small>{{ formatFileSize(file.fileSize) }} · {{ file.contentType || '未知类型' }}</small>
          </div>
          <div class="file-tags">
            <el-tag v-if="fileCandidate(file)" size="small" effect="plain" round>{{ fileCandidate(file).candidateNumber }}</el-tag>
            <el-tag size="small" effect="plain" round type="info">{{ fileRoleLabel(file.role) }}</el-tag>
            <el-tag v-if="file.isPrimary" size="small" effect="plain" round type="warning">主审核文件</el-tag>
          </div>
          <div class="file-actions">
            <el-button
              v-if="showPreview && versionCandidates.length > 1 && fileCandidate(file)"
              size="small"
              :type="Number(file.candidateId) === Number(activeCandidateId) ? 'primary' : 'default'"
              plain
              @click="selectPreviewCandidate(fileCandidate(file))"
            >{{ Number(file.candidateId) === Number(activeCandidateId) ? '预览中' : '预览' }}</el-button>
            <el-button
              v-else-if="!showPreview && showFilePreviewAction && canDownload && isPreviewableFile(file)"
              size="small"
              type="primary"
              plain
              :icon="VideoPlay"
              :aria-label="`预览 ${fileCandidate(file)?.candidateNumber || ''} ${file.businessFileName || file.originalName}`"
              @click="openFilePreview(file)"
            >预览</el-button>
            <el-button
              v-if="canDownload"
              :icon="Download"
              :loading="downloadingFileId === file.fileId"
              :disabled="Boolean(downloadingFileId)"
              @click="downloadFile(file)"
            >下载</el-button>
          </div>
        </div>
      </div>
      <el-empty v-else class="empty-files" :image-size="54" description="当前版本没有可访问的交付文件" />
    </section>

    <el-alert v-if="downloadError" class="download-error" :title="downloadError.title" :description="downloadError.message" type="error" :closable="false" show-icon />

    <el-collapse v-if="version.aiParams" v-model="activeAiSections" class="ai-snapshot">
      <el-collapse-item title="AI 参数快照" name="ai-params"><pre>{{ JSON.stringify(version.aiParams, null, 2) }}</pre></el-collapse-item>
    </el-collapse>

    <el-dialog
      v-model="filePreviewVisible"
      class="version-file-preview-dialog"
      :title="filePreviewTitle"
      width="min(920px, calc(100vw - 32px))"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      @closed="previewingFile = null"
    >
      <ProtectedVersionPreview v-if="filePreviewVisible && filePreviewVersion" :version="filePreviewVersion" :can-preview="canDownload" />
      <template #footer><el-button @click="filePreviewVisible = false">关闭</el-button></template>
    </el-dialog>
  </el-card>
</template>

<style scoped lang="scss">
.version-detail-card { background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-md); }
.version-detail-card:deep(.el-card__body) { padding: 22px; }
.version-detail-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.version-detail-card h3 { margin: 3px 0 7px; font-size: 22px; }
.version-detail-card header p:not(.sg-eyebrow) { max-width: 700px; margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.candidate-preview-switcher { display: grid; margin-top: 20px; padding: 14px; background: rgba(255, 182, 87, 0.04); border: 1px solid rgba(255, 182, 87, 0.2); border-radius: 12px; gap: 12px; }
.candidate-preview-switcher__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.candidate-preview-switcher__heading > div { min-width: 0; }
.candidate-preview-switcher__heading strong,
.candidate-preview-switcher__heading span { display: block; }
.candidate-preview-switcher__heading strong { font-size: 12px; }
.candidate-preview-switcher__heading span { margin-top: 4px; color: var(--sg-text-muted); font-size: 10px; }
.candidate-preview-options { display: flex; width: 100%; flex-wrap: wrap; gap: 8px; }
.candidate-preview-options:deep(.el-radio-button) { min-width: 180px; max-width: 280px; }
.candidate-preview-options:deep(.el-radio-button__inner) { display: block; width: 100%; padding: 9px 12px; text-align: left; border: 1px solid var(--sg-border)!important; border-radius: 9px!important; box-shadow: none!important; }
.candidate-preview-options:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { color: var(--sg-accent); background: var(--sg-accent-soft); border-color: var(--sg-accent)!important; }
.candidate-preview-options strong,
.candidate-preview-options small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.candidate-preview-options strong { font-size: 11px; }
.candidate-preview-options small { margin-top: 4px; color: var(--sg-text-muted); font-size: 9px; }
.candidate-preview-switcher > p { display: flex; margin: 0; color: var(--sg-text-secondary); font-size: 10px; gap: 8px; align-items: baseline; }
.candidate-preview-switcher > p strong { flex: 0 0 auto; color: var(--sg-accent); }
.candidate-preview-switcher > p span { min-width: 0; overflow-wrap: anywhere; }
.version-facts { margin: 20px 0; }
.version-facts:deep(.el-descriptions__body),
.version-facts:deep(.el-descriptions__cell) { background: rgba(0, 0, 0, 0.13); border-color: var(--sg-border); }
.subheading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 12px; }
.subheading span { color: var(--sg-text-muted); }
.file-list { display: grid; gap: 8px; }
.file-row { display: grid; padding: 12px; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 12px; align-items: center; }
.file-row.is-previewing { background: rgba(255, 182, 87, 0.045); border-color: rgba(255, 182, 87, 0.42); }
.file-icon { display: grid; width: 34px; height: 34px; color: var(--sg-accent); background: var(--sg-accent-soft); border-radius: 9px; place-items: center; }
.file-row strong,
.file-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-row strong { font-size: 12px; }
.file-row small { margin-top: 5px; color: var(--sg-text-muted); font-size: 10px; }
.file-tags { display: flex; align-items: center; justify-content: flex-end; gap: 6px; flex-wrap: wrap; }
.file-actions { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.empty-files { padding: 18px; background: rgba(255, 255, 255, 0.02); border-radius: 10px; }
.download-error { margin-top: 14px; }
.download-error code { color: inherit; font-size: 10px; }
.ai-snapshot { margin-top: 18px; color: var(--sg-text-secondary); font-size: 12px; }
.ai-snapshot:deep(.el-collapse-item__header),
.ai-snapshot:deep(.el-collapse-item__wrap) { color: var(--sg-text-secondary); background: transparent; border-color: var(--sg-border); }
.ai-snapshot pre { max-height: 260px; padding: 14px; overflow: auto; color: var(--sg-text-secondary); background: rgba(0, 0, 0, 0.18); border-radius: 9px; white-space: pre-wrap; word-break: break-word; }

@media (max-width: 760px) {
  .candidate-preview-switcher__heading { align-items: flex-start; flex-direction: column; }
  .candidate-preview-options:deep(.el-radio-button) { width: 100%; max-width: none; }
  .file-row { grid-template-columns: auto minmax(0, 1fr); }
  .file-tags,
  .file-actions { grid-column: 2; justify-self: start; }
  .file-tags { justify-content: flex-start; }
}
</style>
