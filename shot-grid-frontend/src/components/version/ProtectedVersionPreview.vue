<script setup>
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { Picture, Refresh, VideoPlay } from '@element-plus/icons-vue'

import {
  createVersionPlaybackTicket,
  downloadProtectedVersionFile,
  resolvePlaybackUrl
} from '@/api/shot-grid/versions'
import { versionErrorState } from './versionPresentation'

const props = defineProps({
  version: { type: Object, required: true },
  canPreview: { type: Boolean, default: false }
})

const preview = reactive({
  state: 'idle',
  url: '',
  posterUrl: '',
  file: null,
  error: null
})

let previewController = null
let previewGeneration = 0
let disposed = false

const previewFile = version => version?.files?.find(file => file.role === 'proxy_media')
  || version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')
  || version?.files?.find(file => file.isPrimary && mediaKind(file) !== 'unsupported')

const originalFile = version => version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')

const thumbnailFile = version => version?.files?.find(file => file.role === 'thumbnail')

function mediaKind(file) {
  const contentType = String(file?.contentType || '').toLowerCase()
  if (contentType.startsWith('image/')) return 'image'
  if (contentType.startsWith('video/')) return 'video'
  return 'unsupported'
}

const kind = computed(() => mediaKind(preview.file))
const fileName = computed(() => preview.file?.businessFileName || preview.file?.originalName || '版本文件')

function cleanupPreview() {
  if (preview.url?.startsWith('blob:')) URL.revokeObjectURL(preview.url)
  if (preview.posterUrl?.startsWith('blob:')) URL.revokeObjectURL(preview.posterUrl)
  Object.assign(preview, { state: 'idle', url: '', posterUrl: '', file: null, error: null })
}

async function loadFile(version, file, controller, generation) {
  preview.file = file
  if (mediaKind(file) === 'unsupported') {
    preview.state = 'unsupported'
    return
  }
  preview.state = 'loading'
  try {
    if (mediaKind(file) === 'video') {
      const poster = thumbnailFile(version)
      const [ticketResult, posterResult] = await Promise.allSettled([
        createVersionPlaybackTicket(version.versionId, file.fileId, { signal: controller.signal }),
        poster
          ? downloadProtectedVersionFile(version.versionId, poster.fileId, { signal: controller.signal })
          : Promise.resolve(null)
      ])
      if (controller.signal.aborted || generation !== previewGeneration) return
      if (ticketResult.status === 'rejected') throw ticketResult.reason
      if (posterResult.status === 'fulfilled' && posterResult.value) {
        preview.posterUrl = URL.createObjectURL(posterResult.value)
      }
      preview.url = resolvePlaybackUrl(ticketResult.value.data?.playbackUrl)
      preview.state = 'ready'
      return
    }

    const blob = await downloadProtectedVersionFile(version.versionId, file.fileId, { signal: controller.signal })
    if (controller.signal.aborted || generation !== previewGeneration) return
    preview.url = URL.createObjectURL(blob)
    preview.state = 'ready'
  } catch (error) {
    const fallback = originalFile(version)
    if (
      file.role === 'proxy_media' &&
      fallback &&
      fallback.fileId !== file.fileId &&
      !controller.signal.aborted &&
      generation === previewGeneration
    ) {
      await loadFile(version, fallback, controller, generation)
      return
    }
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && generation === previewGeneration) {
      preview.state = 'error'
      preview.error = versionErrorState(error, '版本文件预览失败')
    }
  }
}

async function loadPreview() {
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller
  const generation = ++previewGeneration
  cleanupPreview()
  const version = props.version
  const file = previewFile(version)
  if (!file) {
    preview.state = 'empty'
    return
  }
  preview.file = file
  if (!props.canPreview) {
    preview.state = 'forbidden'
    return
  }
  await loadFile(version, file, controller, generation)
  if (previewController === controller) previewController = null
}

function handlePlaybackError() {
  if (preview.state !== 'ready') return
  preview.state = 'error'
  preview.error = {
    title: '浏览器无法播放该视频',
    message: '可下载原文件查看；在线预览可用后即可直接播放。',
    errorKey: null
  }
}

watch(() => [props.version, props.canPreview], loadPreview, { immediate: true })

onBeforeUnmount(() => {
  disposed = true
  previewGeneration += 1
  previewController?.abort()
  previewController = null
  cleanupPreview()
})
</script>

<template>
  <section class="version-preview">
    <header>
      <div><strong>版本预览</strong><span>{{ fileName }}</span></div>
      <el-button v-if="preview.state === 'error' && !disposed" text :icon="Refresh" @click="loadPreview">重新加载</el-button>
    </header>

    <el-skeleton v-if="preview.state === 'loading'" class="preview-state" :rows="5" animated />
    <el-empty v-else-if="preview.state === 'empty'" class="preview-state" :image-size="64" description="当前版本没有可预览的主文件" />
    <el-result v-else-if="preview.state === 'forbidden'" class="preview-state" icon="warning" title="没有预览权限" sub-title="当前账号没有版本文件预览权限。" />
    <el-result v-else-if="preview.state === 'unsupported'" class="preview-state" icon="info" title="暂不支持网页预览" sub-title="可使用下方下载按钮保存文件。" />
    <el-result v-else-if="preview.state === 'error'" class="preview-state is-error" icon="error" :title="preview.error?.title" :sub-title="preview.error?.message" />
    <div v-else-if="preview.state === 'ready'" class="preview-stage" :class="{ 'preview-stage--image': kind === 'image' }">
      <template v-if="kind === 'image'">
        <el-image
          class="preview-thumbnail"
          :src="preview.url"
          :preview-src-list="[preview.url]"
          :alt="`${version.versionNumber} 版本缩略图`"
          fit="cover"
          hide-on-click-modal
          preview-teleported
        />
        <div class="preview-hint"><strong>点击查看大图</strong><span>支持缩放、旋转，也可以点击遮罩或按 Esc 关闭。</span></div>
      </template>
      <video v-else-if="kind === 'video'" :src="preview.url" :poster="preview.posterUrl || undefined" controls playsinline preload="metadata" @error="handlePlaybackError">
        当前浏览器不支持视频预览。
      </video>
      <el-tag class="preview-media-tag" type="info" effect="dark" size="small" round><el-icon><component :is="kind === 'video' ? VideoPlay : Picture" /></el-icon>{{ kind === 'video' ? '视频' : '图片' }}</el-tag>
    </div>
  </section>
</template>

<style scoped lang="scss">
.version-preview { margin: 20px 0; overflow: hidden; background: #0b0f14; border: 1px solid var(--sg-border); border-radius: 12px; }
.version-preview > header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; padding: 0 14px; background: rgba(255, 255, 255, 0.025); border-bottom: 1px solid var(--sg-border); gap: 14px; }
.version-preview > header div { min-width: 0; }
.version-preview > header strong,
.version-preview > header span { display: block; }
.version-preview > header strong { font-size: 12px; }
.version-preview > header span { margin-top: 3px; overflow: hidden; color: var(--sg-text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.preview-stage { position: relative; display: grid; min-height: 320px; max-height: 520px; place-items: center; }
.preview-stage video { display: block; width: 100%; max-width: 100%; height: 100%; max-height: 520px; object-fit: contain; background: #070a0e; }
.preview-stage video { min-height: 320px; }
.preview-stage--image { min-height: 0; max-height: none; justify-content: start; padding: 16px; grid-template-columns: auto minmax(0, 1fr); gap: 16px; }
.preview-thumbnail { width: 160px; height: 160px; overflow: hidden; cursor: zoom-in; background: #070a0e; border: 1px solid var(--sg-border); border-radius: 10px; }
.preview-hint { min-width: 0; align-self: center; }
.preview-hint strong,
.preview-hint span { display: block; }
.preview-hint strong { font-size: 12px; }
.preview-hint span { margin-top: 7px; color: var(--sg-text-muted); font-size: 10px; line-height: 1.6; }
.preview-media-tag { position: absolute; top: 12px; right: 12px; pointer-events: none; }
.preview-media-tag .el-icon { margin-right: 4px; }
.preview-state { min-height: 230px; padding: 28px; color: var(--sg-text-muted); }
.preview-state.is-error { color: #ffb5ad; }

@media (max-width: 760px) {
  .preview-stage,
  .preview-stage video { min-height: 220px; }
  .preview-stage--image { min-height: 0; }
  .preview-thumbnail { width: 120px; height: 120px; }
}
</style>
