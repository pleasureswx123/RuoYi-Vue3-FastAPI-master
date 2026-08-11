<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Document, WarningFilled } from '@element-plus/icons-vue'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { formatFileSize, formatVersionDateTime, versionErrorState, versionStatusMeta } from './versionPresentation'

const props = defineProps({
  version: { type: Object, required: true },
  canDownload: { type: Boolean, default: false }
})

const downloadingFileId = ref(null)
const downloadError = ref(null)
let downloadController = null
let versionGeneration = 0
let disposed = false

const statusMeta = computed(() => versionStatusMeta(props.version?.versionStatus))

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
  }
)

onBeforeUnmount(() => {
  disposed = true
  versionGeneration += 1
  downloadController?.abort()
})
</script>

<template>
  <article class="version-detail-card">
    <header>
      <div>
        <p class="sg-eyebrow">VERSION DETAIL</p>
        <h3>{{ version.versionNumber }}</h3>
        <p>{{ version.changelog }}</p>
      </div>
      <span class="version-state" :data-tone="statusMeta.tone">{{ statusMeta.label }}</span>
    </header>

    <dl class="version-facts">
      <div><dt>提交人</dt><dd>{{ version.submitterName || `用户 #${version.submittedBy}` }}</dd></div>
      <div><dt>提交时间</dt><dd>{{ formatVersionDateTime(version.submittedTime) }}</dd></div>
      <div><dt>版本锁</dt><dd>{{ version.lockVersion }}</dd></div>
      <div><dt>审核单</dt><dd>{{ version.autoReviewList?.reviewListName || '—' }}</dd></div>
    </dl>

    <section class="version-files">
      <div class="subheading"><strong>版本文件</strong><span>{{ version.files?.length || 0 }} 个</span></div>
      <div v-if="version.files?.length" class="file-list">
        <div v-for="file in version.files" :key="file.fileId" class="file-row">
          <span class="file-icon"><el-icon><Document /></el-icon></span>
          <div>
            <strong>{{ file.businessFileName || file.originalName }}</strong>
            <small>{{ file.role }} · {{ formatFileSize(file.fileSize) }} · {{ file.contentType || '未知类型' }}</small>
          </div>
          <el-tag v-if="file.isPrimary" size="small" type="warning">主审核文件</el-tag>
          <el-button
            v-if="canDownload"
            :icon="Download"
            :loading="downloadingFileId === file.fileId"
            :disabled="Boolean(downloadingFileId)"
            @click="downloadFile(file)"
          >下载</el-button>
        </div>
      </div>
      <div v-else class="empty-files">当前版本没有可访问文件。</div>
    </section>

    <div v-if="downloadError" class="download-error" role="alert">
      <el-icon><WarningFilled /></el-icon>
      <div><strong>{{ downloadError.title }}</strong><p>{{ downloadError.message }}</p><code v-if="downloadError.errorKey">{{ downloadError.errorKey }}</code></div>
    </div>

    <details v-if="version.aiParams" class="ai-snapshot">
      <summary>AI 参数快照</summary>
      <pre>{{ JSON.stringify(version.aiParams, null, 2) }}</pre>
    </details>
  </article>
</template>

<style scoped lang="scss">
.version-detail-card { padding: 22px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.version-detail-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.version-detail-card h3 { margin: 3px 0 7px; font-size: 22px; }
.version-detail-card header p:not(.sg-eyebrow) { max-width: 700px; margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.version-state { padding: 6px 10px; color: var(--sg-text-secondary); font-size: 11px; background: rgba(255, 255, 255, 0.05); border-radius: 999px; white-space: nowrap; }
.version-state[data-tone='success'] { color: #7ee0ac; background: rgba(56, 189, 130, 0.1); }
.version-state[data-tone='warning'] { color: #f4c878; background: rgba(255, 182, 87, 0.1); }
.version-state[data-tone='danger'] { color: #ff9a90; background: rgba(244, 92, 92, 0.1); }
.version-facts { display: grid; margin: 20px 0; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.version-facts div { padding: 11px 13px; background: rgba(0, 0, 0, 0.13); border-radius: 9px; }
.version-facts dt { color: var(--sg-text-muted); font-size: 10px; }
.version-facts dd { margin: 5px 0 0; font-size: 12px; }
.subheading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 12px; }
.subheading span { color: var(--sg-text-muted); }
.file-list { display: grid; gap: 8px; }
.file-row { display: grid; padding: 12px; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 12px; align-items: center; }
.file-icon { display: grid; width: 34px; height: 34px; color: var(--sg-accent); background: var(--sg-accent-soft); border-radius: 9px; place-items: center; }
.file-row strong,
.file-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-row strong { font-size: 12px; }
.file-row small { margin-top: 5px; color: var(--sg-text-muted); font-size: 10px; }
.empty-files { padding: 26px; color: var(--sg-text-muted); text-align: center; background: rgba(255, 255, 255, 0.02); border-radius: 10px; }
.download-error { display: flex; padding: 12px 14px; margin-top: 14px; color: #ffb5ad; background: rgba(244, 92, 92, 0.08); border-radius: 9px; gap: 10px; }
.download-error strong,
.download-error p { display: block; margin: 0; }
.download-error p { margin-top: 4px; font-size: 11px; }
.download-error code { color: inherit; font-size: 10px; }
.ai-snapshot { margin-top: 18px; color: var(--sg-text-secondary); font-size: 12px; }
.ai-snapshot pre { max-height: 260px; padding: 14px; overflow: auto; color: var(--sg-text-secondary); background: rgba(0, 0, 0, 0.18); border-radius: 9px; white-space: pre-wrap; word-break: break-word; }

@media (max-width: 760px) {
  .version-facts { grid-template-columns: 1fr 1fr; }
  .file-row { grid-template-columns: auto minmax(0, 1fr); }
  .file-row .el-tag,
  .file-row .el-button { grid-column: 2; justify-self: start; }
}
</style>
