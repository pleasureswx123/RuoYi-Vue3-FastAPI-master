<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VideoPlay } from '@element-plus/icons-vue'
import { ElEmpty, ElIcon, ElImage, ElSkeleton, ElSkeletonItem } from 'element-plus'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'

const props = defineProps({
  versionId: { type: [Number, String], required: true },
  candidate: { type: Object, required: true },
  active: { type: Boolean, default: false },
  canPreview: { type: Boolean, default: false }
})

const state = ref('empty')
const objectUrl = ref('')
let controller = null

const reviewMedia = computed(() => props.candidate?.files?.find(file => file.role === 'review_media') || null)
const thumbnail = computed(() => props.candidate?.files?.find(file => file.role === 'thumbnail')
  || (String(reviewMedia.value?.contentType || '').startsWith('image/') ? reviewMedia.value : null))
const isVideo = computed(() => String(reviewMedia.value?.contentType || '').startsWith('video/'))
const stateMessage = computed(() => {
  if (!props.canPreview) return '无预览权限'
  if (state.value === 'loading') return '正在加载画面'
  if (state.value === 'forbidden') return '无预览权限'
  if (state.value === 'missing') return '暂无候选画面'
  if (state.value === 'error') return '画面加载失败'
  return '暂无候选画面'
})

function revokeObjectUrl() {
  if (!objectUrl.value) return
  URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = ''
}

async function loadThumbnail() {
  controller?.abort()
  revokeObjectUrl()
  if (!props.canPreview) {
    state.value = 'forbidden'
    return
  }
  if (!thumbnail.value?.fileId) {
    state.value = 'empty'
    return
  }
  const requestController = new AbortController()
  controller = requestController
  state.value = 'loading'
  try {
    const blob = await downloadProtectedVersionFile(props.versionId, thumbnail.value.fileId, {
      signal: requestController.signal
    })
    if (controller !== requestController || requestController.signal.aborted) return
    objectUrl.value = URL.createObjectURL(blob)
    state.value = 'ready'
  } catch (error) {
    if (requestController.signal.aborted || error?.code === 'ERR_CANCELED') return
    const status = Number(error?.httpStatus || error?.status || error?.code || 0)
    state.value = status === 403 ? 'forbidden' : status === 404 ? 'missing' : 'error'
  } finally {
    if (controller === requestController) controller = null
  }
}

watch(
  () => [props.versionId, thumbnail.value?.fileId, props.canPreview],
  loadThumbnail,
  { immediate: true }
)

onBeforeUnmount(() => {
  controller?.abort()
  revokeObjectUrl()
})
</script>

<template>
  <div class="candidate-thumbnail" :class="{ 'is-active': active }" :data-state="state">
    <ElImage
      v-if="state === 'ready'"
      class="candidate-thumbnail__image"
      :src="objectUrl"
      :alt="`${candidate.candidateNumber} 候选画面`"
      fit="cover"
    />
    <ElSkeleton v-else-if="state === 'loading'" class="candidate-thumbnail__placeholder" animated>
      <template #template><ElSkeletonItem class="candidate-thumbnail__skeleton" variant="image" /></template>
    </ElSkeleton>
    <ElEmpty v-else class="candidate-thumbnail__placeholder" :image-size="28" :description="stateMessage" />
    <span v-if="state === 'ready' && isVideo" class="candidate-thumbnail__play" aria-hidden="true"><ElIcon><VideoPlay /></ElIcon></span>
    <span class="candidate-thumbnail__status">{{ active ? '正在预览' : '点击切换' }}</span>
  </div>
</template>

<style scoped>
.candidate-thumbnail{position:relative;width:100%;aspect-ratio:16/9;overflow:hidden;background:linear-gradient(135deg,#252a32,#11151a);border:1px solid var(--sg-border);border-radius:10px}.candidate-thumbnail__image,.candidate-thumbnail__placeholder{position:absolute;inset:0;width:100%;height:100%}.candidate-thumbnail__image:deep(.el-image__inner){width:100%;height:100%}.candidate-thumbnail__placeholder{margin:0;padding:0}.candidate-thumbnail__placeholder:deep(.el-empty__description){margin-top:3px}.candidate-thumbnail__placeholder:deep(.el-empty__description p){color:rgba(255,255,255,.62);font-size:9px}.candidate-thumbnail__skeleton{width:100%;height:100%}.candidate-thumbnail__play{position:absolute;top:50%;left:50%;display:grid;width:34px;height:34px;color:#fff;background:rgba(0,0,0,.62);border:1px solid rgba(255,255,255,.72);border-radius:50%;box-shadow:0 4px 14px rgba(0,0,0,.35);transform:translate(-50%,-50%);transition:background .18s,transform .18s;place-items:center}.candidate-thumbnail__play .el-icon{margin-left:2px;font-size:17px}.candidate-thumbnail__status{position:absolute;right:8px;bottom:8px;padding:4px 8px;color:#fff;font-size:9px;font-weight:700;background:rgba(0,0,0,.7);border:1px solid rgba(255,255,255,.18);border-radius:999px;backdrop-filter:blur(5px)}.candidate-thumbnail.is-active .candidate-thumbnail__play{background:var(--sg-accent);transform:translate(-50%,-50%) scale(1.06)}.candidate-thumbnail.is-active .candidate-thumbnail__status{color:#18120a;background:var(--sg-accent)}
</style>
