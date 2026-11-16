<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElButton, ElSkeleton } from 'element-plus'
import { getVersionDetail } from '@/api/shot-grid/versions'
import ReviewCandidateThumbnail from '@/views/review/components/ReviewCandidateThumbnail.vue'

const props = defineProps({
  versionId: { type: [Number, String], default: null },
  taskId: { type: [Number, String], required: true },
  canPreview: { type: Boolean, default: false }
})
const candidate = ref(null)
const state = ref('empty')
let controller
async function load() {
  controller?.abort()
  candidate.value = null
  state.value = 'empty'
  if (!props.versionId || !props.canPreview) return
  const request = new AbortController()
  controller = request
  state.value = 'loading'
  try {
    const { data } = await getVersionDetail(props.versionId, { signal: request.signal })
    if (request.signal.aborted) return
    if (Number(data.taskId) !== Number(props.taskId) || Number(data.versionId) !== Number(props.versionId)) throw new Error('版本归属不匹配')
    candidate.value = data.candidates?.find(item => Number(item.candidateId) === Number(data.selectedCandidateId)) || data.candidates?.[0] || { files: data.files || [] }
    state.value = 'ready'
  } catch (error) {
    if (!request.signal.aborted && error?.code !== 'ERR_CANCELED') state.value = 'error'
  }
}
watch(() => [props.versionId, props.taskId, props.canPreview], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="task-preview">
    <ReviewCandidateThumbnail v-if="candidate" :version-id="versionId" :candidate="candidate" :can-preview="canPreview" />
    <el-skeleton v-else-if="state === 'loading'" animated :rows="1" />
    <el-button v-else-if="state === 'error'" link size="small" @click.stop="load">预览失败 · 重试</el-button>
    <span v-else>{{ versionId ? (canPreview ? '暂无画面' : '无预览权限') : '尚未提交' }}</span>
  </div>
</template>

<style scoped>
.task-preview { width: 88px; min-height: 50px; display: grid; place-items: center; background: var(--sg-surface-raised); border-radius: 6px; color: var(--sg-text-muted); font-size: 11px; }
.task-preview :deep(.candidate-thumbnail__status) { display: none; }
</style>
