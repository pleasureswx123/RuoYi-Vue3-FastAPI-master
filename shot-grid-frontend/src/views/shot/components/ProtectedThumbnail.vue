<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Loading, Lock, Picture, VideoCamera, VideoPlay, WarningFilled } from '@element-plus/icons-vue'
import { ElButton, ElDialog, ElImage } from 'element-plus'

import { downloadProtectedThumbnail } from '@/api/shot-grid/shots'

const props = defineProps({
  thumbnail: { type: Object, default: null },
  video: { type: Object, default: null },
  alt: { type: String, default: '镜头缩略图' }
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
  return '尚无版本缩略图'
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
  if (!props.video?.url || videoState.value === 'loading') return
  videoController?.abort()
  revokeVideoUrl()
  const requestController = new AbortController()
  videoController = requestController
  videoVisible.value = true
  videoState.value = 'loading'
  try {
    const blob = await downloadProtectedThumbnail(props.video.url, { signal: requestController.signal })
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
  const url = props.thumbnail?.url
  if (!url) { state.value = 'empty'; return }
  const requestController = new AbortController()
  controller = requestController
  state.value = 'loading'
  try {
    const blob = await downloadProtectedThumbnail(url, { signal: requestController.signal })
    if (controller !== requestController || requestController.signal.aborted) return
    objectUrl.value = URL.createObjectURL(blob)
    state.value = 'ready'
  } catch (error) {
    if (requestController.signal.aborted || error?.code === 'ERR_CANCELED') return
    const status = Number(error?.httpStatus || error?.status || error?.code || 0)
    state.value = status === 403 ? 'forbidden' : status === 404 ? 'missing' : 'error'
  }
}

watch(() => props.thumbnail?.url, loadThumbnail, { immediate: true })
watch(() => props.video?.url, closeVideoPreview)
onBeforeUnmount(() => {
  controller?.abort()
  videoController?.abort()
  revokeObjectUrl()
  revokeVideoUrl()
})
</script>

<template>
  <div class="protected-thumbnail" :data-state="state">
    <button
      v-if="state === 'ready' && video?.url"
      class="protected-thumbnail__video-trigger"
      type="button"
      :aria-label="`${alt}，点击预览视频`"
      title="点击预览视频"
      @click.stop="openVideoPreview"
    >
      <ElImage class="protected-thumbnail__image" :src="objectUrl" :alt="alt" fit="contain" />
      <span class="protected-thumbnail__play" aria-hidden="true"><el-icon><VideoPlay /></el-icon></span>
    </button>
    <ElImage v-else-if="state === 'ready'" class="protected-thumbnail__image" :src="objectUrl" :alt="alt" fit="contain" />
    <div v-else class="protected-thumbnail__placeholder" :title="message">
      <el-icon v-if="state === 'forbidden'"><Lock /></el-icon>
      <el-icon v-else-if="state === 'missing' || state === 'error'"><Picture /></el-icon>
      <el-icon v-else><VideoCamera /></el-icon>
      <span>{{ message }}</span>
    </div>

    <ElDialog
      v-model="videoVisible"
      class="shot-video-preview"
      :title="alt.replace(/\s*缩略图$/, '')"
      width="min(960px, 92vw)"
      align-center
      append-to-body
      destroy-on-close
      @close="closeVideoPreview"
    >
      <div v-if="videoState === 'loading'" class="shot-video-preview__state">
        <el-icon class="is-loading"><Loading /></el-icon><span>正在安全加载视频…</span>
      </div>
      <div v-else-if="videoState === 'error'" class="shot-video-preview__state is-error" role="alert">
        <el-icon><WarningFilled /></el-icon><span>视频加载失败，请重试。</span><ElButton @click="openVideoPreview">重试</ElButton>
      </div>
      <video
        v-else-if="videoState === 'ready'"
        class="shot-video-preview__player"
        :src="videoUrl"
        controls
        playsinline
        preload="metadata"
      >
        当前浏览器不支持视频预览。
      </video>
    </ElDialog>
  </div>
</template>

<style scoped>
.protected-thumbnail{position:relative;width:100%;height:100%;overflow:hidden;background:linear-gradient(135deg,#202630,#11151b)}.protected-thumbnail__image{position:absolute;inset:0;width:100%;height:100%}.protected-thumbnail__image:deep(.el-image__inner){width:100%;height:100%;object-position:center}.protected-thumbnail__video-trigger{position:absolute;inset:0;width:100%;height:100%;padding:0;overflow:hidden;color:#fff;cursor:pointer;background:transparent;border:0}.protected-thumbnail__play{position:absolute;top:50%;left:50%;display:grid;width:29px;height:29px;color:#fff;background:rgba(0,0,0,.68);border:1px solid rgba(255,255,255,.72);border-radius:50%;box-shadow:0 3px 10px rgba(0,0,0,.4);transform:translate(-50%,-50%);transition:background .15s,transform .15s;place-items:center}.protected-thumbnail__play .el-icon{margin-left:2px;font-size:15px}.protected-thumbnail__video-trigger:hover .protected-thumbnail__play,.protected-thumbnail__video-trigger:focus-visible .protected-thumbnail__play{background:var(--sg-accent);transform:translate(-50%,-50%) scale(1.08)}.protected-thumbnail__video-trigger:focus-visible{outline:2px solid var(--sg-accent);outline-offset:-2px}.protected-thumbnail__placeholder{position:absolute;inset:0;display:grid;gap:5px;align-content:center;color:var(--sg-text-muted);font-size:10px;text-align:center;place-items:center}.protected-thumbnail__placeholder .el-icon{font-size:22px}.protected-thumbnail[data-state=loading] .el-icon{animation:thumbnail-pulse 1s ease-in-out infinite}.shot-video-preview__state{display:flex;min-height:300px;gap:9px;align-items:center;justify-content:center;color:var(--sg-text-muted)}.shot-video-preview__state.is-error{color:var(--sg-danger)}.shot-video-preview__player{display:block;width:100%;max-height:72vh;background:#050608;object-fit:contain}@keyframes thumbnail-pulse{50%{opacity:.35}}
</style>
