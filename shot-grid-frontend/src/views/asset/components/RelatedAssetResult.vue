<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getVersionDetail } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import ProtectedVersionPreview from '@/components/version/ProtectedVersionPreview.vue'
import VersionFolderButton from '@/components/version/VersionFolderButton.vue'

const props = defineProps({ projectId: { type: Number, required: true }, item: { type: Object, required: true } })
const session = useSessionStore()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const canQuery = computed(() => allowed('shotgrid:version:query'))
const canDownload = computed(() => canQuery.value && allowed('shotgrid:file:download'))
const expanded = ref(false)
const loading = ref(false)
const error = ref('')
const version = ref(null)
const selectedId = ref(null)
const candidates = computed(() => version.value?.candidates || [])
const preview = computed(() => version.value ? { ...version.value, files: candidates.value.find(candidate => candidate.candidateId === selectedId.value)?.files || version.value.files || [] } : null)
const file = computed(() => preview.value?.files.find(file => file.role === 'review_media'))
let controller
function reset() { controller?.abort(); expanded.value = false; loading.value = false; error.value = ''; version.value = null; selectedId.value = null }
async function load() {
  if (!canQuery.value || loading.value) return
  expanded.value = true; loading.value = true; error.value = ''
  const request = new AbortController(); controller = request
  try {
    const { data } = await getVersionDetail(props.item.version.versionId, { signal: request.signal })
    if (request.signal.aborted) return
    if (Number(data.projectId) !== props.projectId || Number(data.versionId) !== Number(props.item.version.versionId) || !props.item.task?.taskId || Number(data.taskId) !== Number(props.item.task.taskId)) throw new Error('成果与关联任务归属不匹配')
    version.value = data
    selectedId.value = data.candidates?.find(candidate => Number(candidate.candidateId) === Number(data.selectedCandidateId))?.candidateId || data.candidates?.[0]?.candidateId || null
  } catch (failure) { if (!request.signal.aborted) error.value = failure.message || '成果加载失败' }
  finally { if (controller === request) loading.value = false }
}
watch(() => [props.projectId, props.item.task?.taskId, props.item.version?.versionId, session.permissions.join('|')], reset)
onBeforeUnmount(reset)
</script>
<template>
  <div class="related-result">
    <el-button v-if="!expanded" size="small" :disabled="!canQuery" @click="load">预览成果 / 文件夹</el-button>
    <template v-else>
      <el-button link size="small" @click="reset">收起预览</el-button>
      <el-skeleton v-if="loading" animated :rows="2" />
      <el-alert v-else-if="error" :title="error" type="warning" :closable="false"><el-button text @click="load">重试</el-button></el-alert>
      <template v-else-if="preview">
        <el-select v-if="candidates.length > 1" v-model="selectedId" aria-label="选择关联成果候选">
          <el-option v-for="candidate in candidates" :key="candidate.candidateId" :value="candidate.candidateId" :label="`${candidate.candidateNumber}${Number(candidate.candidateId) === Number(version.selectedCandidateId) ? ' · 本轮最佳' : ''}`" />
        </el-select>
        <ProtectedVersionPreview :version="preview" :can-preview="canDownload" />
        <VersionFolderButton v-if="file" :version="version" :file="file" :can-download="canDownload" />
      </template>
    </template>
  </div>
</template>
<style scoped>
.related-result { display: grid; justify-items: start; gap: 8px; width: 100%; min-width: 0; }
.related-result > :deep(section) { width: 100%; }
.related-result :deep(.preview-stage), .related-result :deep(.preview-stage video) { min-height: 160px; max-height: 240px; }
.related-result :deep(.preview-stage--image) { min-height: 0; max-height: none; padding: 8px; }
.related-result :deep(.preview-thumbnail) { height: 200px; }
.related-result :deep(.preview-state) { min-height: 120px; }
</style>
