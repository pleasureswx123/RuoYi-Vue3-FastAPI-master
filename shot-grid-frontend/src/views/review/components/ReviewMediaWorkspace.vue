<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Aim, Crop, Delete, EditPen, RefreshRight, TopRight, VideoPlay } from '@element-plus/icons-vue'

import {
  createVersionPlaybackTicket,
  downloadProtectedVersionFile,
  getTaskVersions,
  getVersionDetail,
  resolvePlaybackUrl
} from '@/api/shot-grid/versions'
import { formatMediaTime, reviewErrorState } from '@/views/review/reviewPresentation'

const props = defineProps({
  version: { type: Object, required: true },
  selectedNote: { type: Object, default: null },
  canDownload: { type: Boolean, default: false },
  canCompare: { type: Boolean, default: false },
  canAnnotate: { type: Boolean, default: false }
})
const emit = defineEmits(['capture-time', 'annotations-change'])
const currentMedia = reactive({ url: '', posterUrl: '', state: 'idle', error: null, file: null, width: 0, height: 0 })
const compareMedia = reactive({ url: '', posterUrl: '', state: 'idle', error: null, file: null, width: 0, height: 0 })
const comparisonVersions = ref([])
const comparisonVersionId = ref('')
const comparisonVersion = ref(null)
const comparisonLoading = ref(false)
const tool = ref('navigate')
const draftItems = ref([])
const video = ref(null)
const currentTimeMs = ref(0)
const dragStart = ref(null)
let currentController = null
let compareController = null
let historyController = null
let generation = 0

const primaryFile = version => version?.files?.find(file => file.role === 'proxy_media')
  || version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')
const originalFile = version => version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')
const thumbnailFile = version => version?.files?.find(file => file.role === 'thumbnail')
const mediaKind = file => String(file?.contentType || '').startsWith('video/') ? 'video'
  : String(file?.contentType || '').startsWith('image/') ? 'image' : 'unsupported'
const currentKind = computed(() => mediaKind(currentMedia.file))
const compareKind = computed(() => mediaKind(compareMedia.file))
const sourceWidth = computed(() => currentMedia.width || 1)
const sourceHeight = computed(() => currentMedia.height || 1)
const stageStyle = computed(() => ({ aspectRatio: `${sourceWidth.value} / ${sourceHeight.value}` }))
const selectedItems = computed(() => props.selectedNote?.annotations?.items || [])
const visibleItems = computed(() => [...selectedItems.value, ...draftItems.value])
const hasMedia = computed(() => Boolean(primaryFile(props.version)))
const usingProxy = computed(() => currentMedia.file?.role === 'proxy_media')
const derivationLabel = computed(() => ({
  pending: '优化预览正在排队，暂用原始媒体',
  processing: '正在生成缩略图和网页代理，暂用原始媒体',
  completed: '已使用优化后的网页审核媒体',
  failed: '优化预览生成失败，已安全降级为原始媒体'
}[props.version?.mediaDerivationStatus] || ''))

function cleanupMedia(target) {
  if (target.url?.startsWith('blob:')) URL.revokeObjectURL(target.url)
  if (target.posterUrl) URL.revokeObjectURL(target.posterUrl)
  Object.assign(target, { url: '', posterUrl: '', state: 'idle', error: null, file: null, width: 0, height: 0 })
}

async function loadMedia(version, target, controller, expectedGeneration) {
  cleanupMedia(target)
  const file = primaryFile(version)
  if (!file) {
    target.state = 'empty'
    return
  }
  if (!props.canDownload) {
    target.state = 'forbidden'
    return
  }
  target.file = file
  target.state = 'loading'
  try {
    if (mediaKind(file) === 'video') {
      const poster = thumbnailFile(version)
      const [ticketResult, posterResult] = await Promise.allSettled([
        createVersionPlaybackTicket(version.versionId, file.fileId, { signal: controller.signal }),
        poster
          ? downloadProtectedVersionFile(version.versionId, poster.fileId, { signal: controller.signal })
          : Promise.resolve(null)
      ])
      if (controller.signal.aborted || expectedGeneration !== generation) return
      if (ticketResult.status === 'rejected') throw ticketResult.reason
      if (posterResult.status === 'fulfilled' && posterResult.value) {
        target.posterUrl = URL.createObjectURL(posterResult.value)
      }
      target.url = resolvePlaybackUrl(ticketResult.value.data?.playbackUrl)
      target.state = 'ready'
      return
    }
    const blob = await downloadProtectedVersionFile(version.versionId, file.fileId, { signal: controller.signal })
    if (controller.signal.aborted || expectedGeneration !== generation) return
    target.url = URL.createObjectURL(blob)
    target.state = 'ready'
  } catch (error) {
    const fallback = originalFile(version)
    if (file?.role === 'proxy_media' && fallback && fallback.fileId !== file.fileId && !controller.signal.aborted) {
      await loadMedia(
        { ...version, files: version.files.filter(item => item.role !== 'proxy_media') },
        target,
        controller,
        expectedGeneration
      )
      return
    }
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && expectedGeneration === generation) {
      target.state = 'error'
      target.error = reviewErrorState(error, '审核媒体加载失败')
    }
  }
}

async function loadCurrentMedia() {
  currentController?.abort()
  const controller = new AbortController()
  currentController = controller
  const expectedGeneration = ++generation
  draftItems.value = []
  emitAnnotations()
  await loadMedia(props.version, currentMedia, controller, expectedGeneration)
}

async function loadComparisonOptions() {
  historyController?.abort()
  comparisonVersions.value = []
  comparisonVersionId.value = ''
  comparisonVersion.value = null
  cleanupMedia(compareMedia)
  if (!props.canCompare || !props.version?.taskId) return
  const controller = new AbortController()
  historyController = controller
  try {
    const response = await getTaskVersions(props.version.taskId, {
      pageNum: 1, pageSize: 100, orderByColumn: 'versionNo', isAsc: 'descending'
    }, { signal: controller.signal })
    if (historyController !== controller || controller.signal.aborted) return
    comparisonVersions.value = (response.rows || []).filter(item => Number(item.versionId) !== Number(props.version.versionId))
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') ElMessage.error(reviewErrorState(error, '历史版本加载失败').message)
  }
}

async function loadComparison() {
  compareController?.abort()
  cleanupMedia(compareMedia)
  comparisonVersion.value = null
  if (!comparisonVersionId.value) return
  const controller = new AbortController()
  compareController = controller
  const expectedGeneration = generation
  comparisonLoading.value = true
  try {
    const response = await getVersionDetail(Number(comparisonVersionId.value), { signal: controller.signal })
    if (compareController !== controller || controller.signal.aborted || expectedGeneration !== generation) return
    comparisonVersion.value = response.data
    await loadMedia(response.data, compareMedia, controller, expectedGeneration)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') ElMessage.error(reviewErrorState(error, '对比版本加载失败').message)
  } finally {
    if (compareController === controller) comparisonLoading.value = false
  }
}

function onMediaReady(event, target) {
  const element = event.currentTarget
  target.width = Number(element.naturalWidth || element.videoWidth || 1)
  target.height = Number(element.naturalHeight || element.videoHeight || 1)
}

function updateVideoTime() {
  currentTimeMs.value = Math.round(Number(video.value?.currentTime || 0) * 1000)
}

function captureCurrentTime() {
  updateVideoTime()
  emit('capture-time', currentTimeMs.value)
  ElMessage.success(`已捕获时间点 ${formatMediaTime(currentTimeMs.value)}`)
}

function pointFromEvent(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))
  }
}

function beginAnnotation(event) {
  if (!props.canAnnotate || tool.value === 'navigate') return
  dragStart.value = pointFromEvent(event)
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function arrowStyle(item) {
  const [start, end] = item.points
  const aspectRatio = sourceWidth.value / sourceHeight.value
  const dx = end.x - start.x
  const dyInWidthUnits = (end.y - start.y) / aspectRatio
  return {
    left: `${start.x * 100}%`,
    top: `${start.y * 100}%`,
    width: `${Math.hypot(dx, dyInWidthUnits) * 100}%`,
    color: item.color,
    transform: `rotate(${Math.atan2(dyInWidthUnits, dx)}rad)`
  }
}

async function requestAnnotationText() {
  try {
    const result = await ElMessageBox.prompt('输入要标记在画面上的文字', '添加文字批注', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：这里需要降低高光',
      inputType: 'textarea',
      inputValidator: value => {
        const normalized = String(value || '').trim()
        if (!normalized) return '请输入批注文字'
        if (normalized.length > 1000) return '批注文字不能超过 1000 个字符'
        return true
      }
    })
    return String(result.value || '').trim()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return null
    throw error
  }
}

async function finishAnnotation(event) {
  if (!dragStart.value || !props.canAnnotate || tool.value === 'navigate') return
  const end = pointFromEvent(event)
  const start = dragStart.value
  dragStart.value = null
  const id = `annotation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  let item = null
  if (tool.value === 'point') {
    item = { id, type: 'point', color: '#ffb657', strokeWidth: 0.004, points: [end] }
  } else if (tool.value === 'rectangle') {
    item = { id, type: 'rectangle', color: '#ff6b6b', strokeWidth: 0.004, points: [start, end] }
  } else if (tool.value === 'arrow') {
    item = { id, type: 'arrow', color: '#68b5ff', strokeWidth: 0.004, points: [start, end] }
  } else if (tool.value === 'text') {
    const text = await requestAnnotationText()
    if (!text) return
    item = { id, type: 'text', color: '#ffd166', strokeWidth: 0, points: [end], text }
  }
  if (!item) return
  draftItems.value = [...draftItems.value, item]
  if (currentKind.value === 'video') captureCurrentTime()
  emitAnnotations()
}

function emitAnnotations() {
  emit('annotations-change', draftItems.value.length ? {
    schemaVersion: 1,
    sourceWidth: sourceWidth.value,
    sourceHeight: sourceHeight.value,
    items: draftItems.value
  } : null)
}

function clearDraft() {
  draftItems.value = []
  emitAnnotations()
}

function seekToNote() {
  const sourceTimeMs = props.selectedNote?.mediaTimeMs
  if (sourceTimeMs === null || sourceTimeMs === undefined) return
  const timeMs = Number(sourceTimeMs)
  if (video.value && Number.isFinite(timeMs) && timeMs >= 0) {
    video.value.currentTime = timeMs / 1000
    video.value.pause()
    updateVideoTime()
  }
}

watch(() => props.version?.versionId, async () => {
  await loadCurrentMedia()
  await loadComparisonOptions()
}, { immediate: true })
watch(comparisonVersionId, loadComparison)
watch(() => props.selectedNote?.noteId, seekToNote)

onBeforeUnmount(() => {
  generation += 1
  currentController?.abort()
  compareController?.abort()
  historyController?.abort()
  cleanupMedia(currentMedia)
  cleanupMedia(compareMedia)
})

defineExpose({ clearDraft, seekToNote })
</script>

<template>
  <section class="media-workspace">
    <header class="media-heading">
      <div><p class="sg-eyebrow">REVIEW MEDIA</p><h3>审核媒体与画面批注</h3><small>媒体通过鉴权文件接口加载；批注坐标按原始画面归一化保存。</small></div>
      <div class="media-actions">
        <el-select v-if="canCompare" v-model="comparisonVersionId" clearable filterable placeholder="选择 A/B 对比版本" :loading="comparisonLoading"><el-option v-for="item in comparisonVersions" :key="item.versionId" :label="`${item.versionNumber} · ${item.changelog}`" :value="String(item.versionId)" /></el-select>
        <el-button v-if="canAnnotate" :type="tool === 'navigate' ? 'primary' : 'default'" :icon="VideoPlay" @click="tool = 'navigate'">浏览</el-button>
        <el-button v-if="canAnnotate" :type="tool === 'point' ? 'primary' : 'default'" :icon="Aim" @click="tool = 'point'">点标注</el-button>
        <el-button v-if="canAnnotate" :type="tool === 'rectangle' ? 'primary' : 'default'" :icon="Crop" @click="tool = 'rectangle'">框选</el-button>
        <el-button v-if="canAnnotate" :type="tool === 'arrow' ? 'primary' : 'default'" :icon="TopRight" @click="tool = 'arrow'">箭头</el-button>
        <el-button v-if="canAnnotate" :type="tool === 'text' ? 'primary' : 'default'" :icon="EditPen" @click="tool = 'text'">文字</el-button>
        <el-button v-if="draftItems.length" :icon="Delete" @click="clearDraft">清空草稿</el-button>
      </div>
    </header>

    <div class="media-columns" :class="{ 'has-comparison': comparisonVersionId }">
      <article class="media-column">
        <el-alert v-if="derivationLabel" class="media-derivation" :title="derivationLabel" :type="version.mediaDerivationStatus === 'failed' ? 'warning' : version.mediaDerivationStatus === 'completed' ? 'success' : 'info'" :closable="false" show-icon />
        <div class="media-label"><strong>A · {{ version.versionNumber }} <em v-if="usingProxy">网页代理</em></strong><span v-if="currentKind === 'video'">{{ formatMediaTime(currentTimeMs) }}</span></div>
        <div v-if="currentMedia.state === 'ready' && currentKind !== 'unsupported'" class="media-stage" :style="stageStyle">
          <img v-if="currentKind === 'image'" :src="currentMedia.url" alt="当前审核图片" @load="onMediaReady($event, currentMedia)" />
          <video v-else ref="video" :src="currentMedia.url" :poster="currentMedia.posterUrl || undefined" controls preload="metadata" @loadedmetadata="onMediaReady($event, currentMedia)" @timeupdate="updateVideoTime" />
          <div class="annotation-layer" :data-active="tool !== 'navigate'" @pointerdown="beginAnnotation" @pointerup="finishAnnotation">
            <template v-for="item in visibleItems" :key="item.id">
              <span v-if="item.type === 'point'" class="annotation-point" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'rectangle' && item.points.length > 1" class="annotation-rectangle" :style="{ left: `${Math.min(item.points[0].x,item.points[1].x) * 100}%`, top: `${Math.min(item.points[0].y,item.points[1].y) * 100}%`, width: `${Math.abs(item.points[1].x-item.points[0].x) * 100}%`, height: `${Math.abs(item.points[1].y-item.points[0].y) * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'arrow' && item.points.length > 1" class="annotation-arrow" :style="arrowStyle(item)"><i /></span>
              <span v-else-if="item.type === 'text' && item.points.length" class="annotation-text" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, color: item.color }">{{ item.text }}</span>
            </template>
          </div>
        </div>
        <div v-else class="media-empty"><el-skeleton v-if="currentMedia.state === 'loading'" animated :rows="4" /><strong v-else>{{ !hasMedia ? '当前版本没有审核文件' : currentMedia.state === 'forbidden' ? '没有媒体下载权限' : currentMedia.state === 'error' ? currentMedia.error?.message : currentKind === 'unsupported' ? '该文件类型暂不支持内嵌预览' : '正在准备媒体…' }}</strong></div>
        <el-button v-if="currentKind === 'video' && currentMedia.state === 'ready'" :icon="Aim" @click="captureCurrentTime">把当前帧时间带入意见</el-button>
      </article>

      <article v-if="comparisonVersionId" class="media-column">
        <div class="media-label"><strong>B · {{ comparisonVersion?.versionNumber || '加载中' }}</strong><span>只读对比</span></div>
        <div v-if="compareMedia.state === 'ready' && compareKind !== 'unsupported'" class="media-stage" :style="{ aspectRatio: `${compareMedia.width || 1} / ${compareMedia.height || 1}` }">
          <img v-if="compareKind === 'image'" :src="compareMedia.url" alt="对比版本图片" @load="onMediaReady($event, compareMedia)" />
          <video v-else :src="compareMedia.url" :poster="compareMedia.posterUrl || undefined" controls preload="metadata" @loadedmetadata="onMediaReady($event, compareMedia)" />
        </div>
        <div v-else class="media-empty"><strong>{{ compareMedia.state === 'error' ? compareMedia.error?.message : '正在加载对比版本…' }}</strong></div>
        <el-button :icon="RefreshRight" @click="comparisonVersionId = ''">退出对比</el-button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.media-workspace{display:grid;gap:15px;padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.media-heading,.media-actions,.media-label{display:flex;gap:10px;align-items:center;justify-content:space-between}.media-heading h3{margin:3px 0 0;font-size:16px}.media-heading small,.media-label span{color:var(--sg-text-muted);font-size:10px}.media-actions{justify-content:flex-end;flex-wrap:wrap}.media-actions .el-select{width:230px}.media-columns{display:grid;gap:14px}.media-columns.has-comparison{grid-template-columns:repeat(2,minmax(0,1fr))}.media-column{display:grid;min-width:0;gap:10px}.media-stage{position:relative;overflow:hidden;max-height:620px;background:#050608;border:1px solid var(--sg-border-strong);border-radius:10px}.media-stage img,.media-stage video{display:block;width:100%;height:100%;object-fit:contain}.annotation-layer{position:absolute;inset:0;pointer-events:none}.annotation-layer[data-active=true]{cursor:crosshair;pointer-events:auto}.annotation-point{position:absolute;width:18px;height:18px;border:3px solid;border-radius:50%;box-shadow:0 0 0 2px rgba(0,0,0,.6);transform:translate(-50%,-50%)}.annotation-rectangle{position:absolute;border:3px solid;box-shadow:0 0 0 1px rgba(0,0,0,.55)}.annotation-arrow{position:absolute;height:3px;background:currentColor;box-shadow:0 1px 2px rgba(0,0,0,.7);transform-origin:left center}.annotation-arrow i{position:absolute;top:50%;right:-2px;width:12px;height:12px;border-top:3px solid currentColor;border-right:3px solid currentColor;transform:translateY(-50%) rotate(45deg)}.annotation-text{position:absolute;max-width:min(280px,60%);padding:5px 8px;font-size:12px;font-weight:700;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;background:rgba(0,0,0,.72);border:1px solid currentColor;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.4);transform:translateY(-50%)}.media-empty{display:grid;min-height:260px;color:var(--sg-text-muted);text-align:center;background:#080a0d;border:1px dashed var(--sg-border);border-radius:10px;place-items:center}@media(max-width:950px){.media-heading{align-items:flex-start;flex-direction:column}.media-actions{justify-content:flex-start}.media-columns.has-comparison{grid-template-columns:1fr}}
.media-label em{padding:3px 6px;color:var(--sg-success);font-size:9px;font-style:normal;background:rgba(98,212,155,.1);border-radius:999px}
</style>
