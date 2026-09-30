<script setup>
import { computed, ref } from 'vue'
import { Delete, Document, UploadFilled } from '@element-plus/icons-vue'
import ReviewReferenceFiles from './ReviewReferenceFiles.vue'
import { MAX_REFERENCE_FILES, REFERENCE_ACCEPT } from '@/composables/useReviewReferenceAttachments'

const props = defineProps({ files: { type: Array, default: () => [] }, disabled: Boolean, readonly: Boolean, purpose: { type: String, default: '反馈' } })
const emit = defineEmits(['add', 'remove'])
const uploadRef = ref(null)
const savedFiles = computed(() => props.files.filter(file => file.downloadUrl))
const localFiles = computed(() => props.files.filter(file => !file.downloadUrl))
function selectFile(file) {
  uploadRef.value?.clearFiles()
  if (!props.disabled && !props.readonly) emit('add', file)
}
function formatSize(bytes) {
  const size = Number(bytes || 0)
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / 1024 / 1024).toFixed(1)} MiB`
}
</script>

<template>
  <div class="issue-reference-compose">
    <div v-if="!readonly" class="issue-reference-compose__heading">
      <el-upload ref="uploadRef" :auto-upload="false" :show-file-list="false" multiple :accept="REFERENCE_ACCEPT" :disabled="disabled || files.length >= MAX_REFERENCE_FILES" :on-change="selectFile">
        <el-button :icon="UploadFilled" :disabled="disabled || files.length >= MAX_REFERENCE_FILES">添加图片或参考资料</el-button>
      </el-upload>
      <span>最多 5 个，每个不超过 20 MiB</span>
    </div>
    <p v-if="!readonly" class="issue-reference-compose__hint">支持图片、文档或短视频参考。</p>
    <ReviewReferenceFiles v-if="savedFiles.length" :files="savedFiles" compact :removable="!readonly && !disabled" @remove="emit('remove', $event)" />
    <div v-if="localFiles.length" class="issue-reference-pending-list">
      <article v-for="file in localFiles" :key="file.clientKey" class="issue-reference-pending">
        <el-image v-if="file.previewUrl" class="issue-reference-pending__preview" :src="file.previewUrl" :alt="file.originalName" :preview-src-list="[file.previewUrl]" preview-teleported fit="cover" />
        <div v-else class="issue-reference-pending__icon" aria-hidden="true"><el-icon><Document /></el-icon></div>
        <div class="issue-reference-pending__info"><strong :title="file.originalName">{{ file.originalName }}</strong><small>{{ formatSize(file.fileSize) }} · {{ file.fileId ? `已上传，待提交${purpose}` : `提交${purpose}时上传` }}</small><el-progress v-if="file.uploadProgress > 0 && file.uploadProgress < 100" :percentage="file.uploadProgress" :stroke-width="4" :show-text="false" /></div>
        <el-button v-if="!readonly" text type="danger" :icon="Delete" :disabled="disabled" :aria-label="`移除参考文件 ${file.originalName}`" @click="emit('remove', file)">移除</el-button>
      </article>
    </div>
  </div>
</template>

<style scoped>
.issue-reference-compose{display:grid;width:100%;gap:8px}
.issue-reference-compose__heading{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}
.issue-reference-compose__heading>span,.issue-reference-compose__hint{margin:0;color:var(--sg-text-muted);font-size:12px;line-height:1.5}
.issue-reference-pending-list{display:grid;gap:7px}
.issue-reference-pending{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px;align-items:center;min-width:0;padding:8px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:8px}
.issue-reference-pending__preview,.issue-reference-pending__icon{width:38px;height:38px;overflow:hidden;border-radius:6px}
.issue-reference-pending__icon{display:grid;color:var(--sg-accent);font-size:18px;background:var(--sg-accent-soft);place-items:center}
.issue-reference-pending__info{display:grid;min-width:0;gap:3px}
.issue-reference-pending strong{overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.issue-reference-pending small{color:var(--sg-text-muted);font-size:12px}
.issue-reference-pending .el-button{margin:0}
</style>
