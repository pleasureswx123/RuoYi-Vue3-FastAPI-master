<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VideoPlay } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElEmpty, ElImage, ElResult, ElSkeleton, ElSkeletonItem } from 'element-plus'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'

const props = defineProps({
  thumbnail: { type: Object, default: null },
  video: { type: Object, default: null },
  versionId: { type: [Number, String], required: true },
  alt: { type: String, default: '版本缩略图' }
})
const state = ref('empty')
const objectUrl = ref('')
const videoVisible = ref(false)
const videoState = ref('idle')
const videoUrl = ref('')
let controller = null
let videoController = null

const message = computed(() => {
  if (state.value === 'loading') return '正在加载缩略图'
  if (state.value === 'forbidden') return '缩略图无权访问'
  if (state.value === 'missing') return '缩略图不存在'
  if (state.value === 'error') return '缩略图加载失败'
  return '暂无缩略图'
})

function revokeObjectUrl() {
  if (!objectUrl.value) return
  URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = ''
}

function revokeVideoUrl() {
  if (!videoUrl.value) return
  URL.revokeObjectURL(videoUrl.value)
  videoUrl.value = ''
}

function closeVideoPreview() {
  videoController?.abort()
  videoController = null
  videoVisible.value = false
  videoState.value = 'idle'
  revokeVideoUrl()
}

async function openVideoPreview() {
  if (!props.video?.fileId || videoState.value === 'loading') return
  videoController?.abort()
  revokeVideoUrl()
  const requestController = new AbortController()
  videoController = requestController
  videoVisible.value = true
  videoState.value = 'loading'
  try {
    const blob = await downloadProtectedVersionFile(props.versionId, props.video.fileId, {
      signal: requestController.signal
    })
    if (videoController !== requestController || requestController.signal.aborted) return
    videoUrl.value = URL.createObjectURL(blob)
    videoState.value = 'ready'
  } catch (error) {
    if (requestController.signal.aborted || error?.code === 'ERR_CANCELED') return
    videoState.value = 'error'
  } finally {
    if (videoController === requestController) videoController = null
  }
}

async function loadThumbnail() {
  controller?.abort()
  revokeObjectUrl()
  if (!props.thumbnail?.fileId) {
    state.value = 'empty'
    return
  }
  const requestController = new AbortController()
  controller = requestController
  state.value = 'loading'
  try {
    const blob = await downloadProtectedVersionFile(props.versionId, props.thumbnail.fileId, {
      signal: requestController.signal
    })
    if (controller !== requestController || requestController.signal.aborted) return
    objectUrl.value = URL.createObjectURL(blob)
    state.value = 'ready'
  } catch (error) {
    if (requestController.signal.aborted || error?.code === 'ERR_CANCELED') return
    const status = Number(error?.httpStatus || error?.status || error?.code || 0)
    state.value = status === 403 ? 'forbidden' : status === 404 ? 'missing' : 'error'
  }
}

watch(
  () => [props.versionId, props.thumbnail?.fileId],
  loadThumbnail,
  { immediate: true }
)
watch(
  () => [props.versionId, props.video?.fileId],
  closeVideoPreview
)
onBeforeUnmount(() => {
  controller?.abort()
  videoController?.abort()
  revokeObjectUrl()
  revokeVideoUrl()
})
</script>

<template>
  <div class="file-thumbnail" :data-state="state">
    <ElButton
      v-if="state === 'ready' && video?.fileId"
      class="file-thumbnail__video-trigger"
      text
      :aria-label="`${alt}，点击预览视频`"
      title="点击预览视频"
      @click="openVideoPreview"
    >
      <ElImage class="file-thumbnail__image" :src="objectUrl" :alt="alt" fit="contain" />
      <span class="file-thumbnail__play" aria-hidden="true"><el-icon><VideoPlay /></el-icon></span>
    </ElButton>
    <ElImage
      v-else-if="state === 'ready'"
      class="file-thumbnail__image"
      :src="objectUrl"
      :preview-src-list="[objectUrl]"
      :alt="alt"
      fit="contain"
      title="点击查看大图"
      hide-on-click-modal
      preview-teleported
    />
    <ElSkeleton v-else-if="state === 'loading'" class="file-thumbnail__placeholder" animated>
      <template #template><ElSkeletonItem class="file-thumbnail__skeleton" variant="image" /></template>
    </ElSkeleton>
    <ElEmpty v-else class="file-thumbnail__placeholder" :image-size="20" :description="message" :title="message" />
  </div>

  <ElDialog
    v-model="videoVisible"
    class="file-video-preview"
    :title="alt.replace(/\s*缩略图$/, '')"
    width="min(960px, 92vw)"
    align-center
    append-to-body
    destroy-on-close
    @close="closeVideoPreview"
  >
    <ElSkeleton v-if="videoState === 'loading'" class="file-video-preview__state" :rows="5" animated />
    <ElResult v-else-if="videoState === 'error'" class="file-video-preview__state is-error" icon="error" title="视频加载失败" sub-title="视频暂时无法加载，请重试。"><template #extra><ElButton @click="openVideoPreview">重试</ElButton></template></ElResult>
    <video
      v-else-if="videoState === 'ready'"
      class="file-video-preview__player"
      :src="videoUrl"
      controls
      playsinline
      preload="metadata"
    >
      当前浏览器不支持视频预览。
    </video>
  </ElDialog>
</template>

<style scoped>
.file-thumbnail{position:relative;width:112px;aspect-ratio:16/9;overflow:hidden;background:linear-gradient(135deg,#252a32,#11151a);border:1px solid var(--sg-border);border-radius:9px}.file-thumbnail__image{position:absolute;inset:0;width:100%;height:100%;cursor:zoom-in}.file-thumbnail__image:deep(.el-image__inner){width:100%;height:100%;object-position:center}.file-thumbnail__video-trigger{position:absolute;inset:0;width:100%;height:100%;padding:0;overflow:hidden;color:#fff;cursor:pointer;background:transparent;border:0;border-radius:0}.file-thumbnail__video-trigger .file-thumbnail__image{cursor:pointer}.file-thumbnail__play{position:absolute;top:50%;left:50%;display:grid;width:29px;height:29px;color:#fff;background:rgba(0,0,0,.68);border:1px solid rgba(255,255,255,.72);border-radius:50%;box-shadow:0 3px 10px rgba(0,0,0,.4);transform:translate(-50%,-50%);transition:background .15s,transform .15s;place-items:center}.file-thumbnail__play .el-icon{margin-left:2px;font-size:15px}.file-thumbnail__video-trigger:hover .file-thumbnail__play,.file-thumbnail__video-trigger:focus-visible .file-thumbnail__play{background:var(--sg-accent);transform:translate(-50%,-50%) scale(1.08)}.file-thumbnail__video-trigger:focus-visible{outline:2px solid var(--sg-accent);outline-offset:-2px}.file-thumbnail__placeholder{position:absolute;inset:0;margin:0;padding:0}.file-thumbnail__placeholder:deep(.el-empty__description){margin-top:2px}.file-thumbnail__placeholder:deep(.el-empty__description p){font-size:8px}.file-thumbnail__skeleton{width:100%;height:100%}.file-video-preview__state{min-height:300px;padding:24px}.file-video-preview__state.is-error{color:var(--sg-danger)}.file-video-preview__player{display:block;width:100%;max-height:72vh;background:#050608;object-fit:contain}
</style>
