<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Aim, Brush, Crop, Delete, EditPen, TopRight, VideoPlay } from '@element-plus/icons-vue'

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
  canAnnotate: { type: Boolean, default: false },
  feedbackMode: { type: Boolean, default: false },
  draftMediaTimeMs: { type: Number, default: null },
  draftAnnotationCount: { type: Number, default: 0 }
})
const emit = defineEmits(['capture-time', 'start-issue', 'annotations-change', 'clear-note-focus'])
const currentMedia = reactive({ url: '', posterUrl: '', state: 'idle', error: null, file: null, width: 0, height: 0 })
const compareMedia = reactive({ url: '', posterUrl: '', state: 'idle', error: null, file: null, width: 0, height: 0 })
const comparisonVersions = ref([])
const comparisonVersionId = ref('')
const comparisonVersion = ref(null)
const comparisonLoading = ref(false)
const annotationMode = ref(false)
const tool = ref('navigate')
const draftItems = ref([])
const video = ref(null)
const compareVideo = ref(null)
const workspaceRoot = ref(null)
const currentTimeMs = ref(0)
const pendingSeekMs = ref(null)
const dragStart = ref(null)
const dragCurrent = ref(null)
const dragPointerId = ref(null)
const dragPath = ref([])
const noteFocusPulse = ref(false)
let currentController = null
let compareController = null
let historyController = null
let generation = 0
let focusTimer = null

const MAX_FREEHAND_POINTS = 512
const MIN_FREEHAND_POINT_DISTANCE = 0.002

const primaryFile = version => version?.files?.find(file => file.role === 'proxy_media')
  || version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')
const originalFile = version => version?.files?.find(file => file.isPrimary && file.role === 'review_media')
  || version?.files?.find(file => file.role === 'review_media')
const thumbnailFile = version => version?.files?.find(file => file.role === 'thumbnail')
const versionOrder = version => Number(version?.versionNo ?? String(version?.versionNumber || '').match(/\d+/)?.[0] ?? 0)
const mediaKind = file => String(file?.contentType || '').startsWith('video/') ? 'video'
  : String(file?.contentType || '').startsWith('image/') ? 'image' : 'unsupported'
const currentMediaKey = computed(() => [
  props.version?.versionId,
  primaryFile(props.version)?.fileId,
  thumbnailFile(props.version)?.fileId,
  props.version?.mediaDerivationStatus
].join(':'))
const currentKind = computed(() => mediaKind(currentMedia.file))
const compareKind = computed(() => mediaKind(compareMedia.file))
const sourceWidth = computed(() => currentMedia.width || 1)
const sourceHeight = computed(() => currentMedia.height || 1)
const stageStyle = computed(() => ({ aspectRatio: `${sourceWidth.value} / ${sourceHeight.value}` }))
const selectedItems = computed(() => props.selectedNote?.annotations?.items || [])
const selectedSourceVersionId = computed(() => Number(
  props.selectedNote?.originVersionId || props.selectedNote?.versionId || props.version?.versionId
))
const selectedOnCurrentVersion = computed(() => selectedSourceVersionId.value === Number(props.version?.versionId))
const visibleItems = computed(() => [
  ...(selectedOnCurrentVersion.value ? selectedItems.value : []),
  ...draftItems.value
])
const comparisonSelectedItems = computed(() => (
  !selectedOnCurrentVersion.value && selectedSourceVersionId.value === Number(comparisonVersionId.value)
    ? selectedItems.value
    : []
))
const hasMedia = computed(() => Boolean(primaryFile(props.version)))
const usingProxy = computed(() => currentMedia.file?.role === 'proxy_media')
const hasComparisonOptions = computed(() => comparisonVersions.value.length > 0)
const currentVersionLabel = computed(() => comparisonVersionId.value
  ? `当前版 · ${props.version.versionNumber}`
  : props.version.versionNumber)
const recordActionLabel = computed(() => currentKind.value === 'video'
  ? `在 ${formatMediaTime(currentTimeMs.value)} 记录问题`
  : '记录这个画面的问题')
const hasDraftContext = computed(() => (
  props.draftMediaTimeMs !== null
  || props.draftAnnotationCount > 0
  || draftItems.value.length > 0
))
const hasUnsavedAnnotations = computed(() => props.draftAnnotationCount > 0 || draftItems.value.length > 0)
const activeAnnotationPreview = computed(() => {
  if (!dragStart.value || !dragCurrent.value || !['rectangle', 'arrow', 'freehand'].includes(tool.value)) return null
  return {
    id: 'active-annotation-preview',
    type: tool.value,
    color: tool.value === 'rectangle' ? '#ff6b6b' : tool.value === 'arrow' ? '#68b5ff' : '#ff8a4c',
    strokeWidth: tool.value === 'freehand' ? 0.008 : 0.004,
    points: tool.value === 'freehand' ? dragPath.value : [dragStart.value, dragCurrent.value]
  }
})
const playbackStatus = computed(() => {
  if (usingProxy.value) {
    return { label: '流畅预览', type: 'success', title: '当前使用适合网页播放的审核预览。' }
  }
  if (['pending', 'processing'].includes(props.version?.mediaDerivationStatus)) {
    return { label: '原文件播放', type: 'info', title: '当前可以正常审核；文件较大时加载可能稍慢。' }
  }
  if (props.version?.mediaDerivationStatus === 'failed') {
    return { label: '原文件播放', type: 'warning', title: '当前仍可正常审核；网页预览优化暂未完成。' }
  }
  return null
})
const selectedNoteSummary = computed(() => {
  if (!props.selectedNote) return ''
  if (props.selectedNote.mediaTimeMs !== null && props.selectedNote.mediaTimeMs !== undefined) {
    return `已定位到 ${formatMediaTime(props.selectedNote.mediaTimeMs)}`
  }
  if (selectedItems.value.length) return `已显示 ${selectedItems.value.length} 个画面标注`
  return '已定位到这条修改意见关联的作品'
})

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
    comparisonVersions.value = (response.rows || [])
      .filter(item => Number(item.versionId) !== Number(props.version.versionId))
      .filter(item => versionOrder(item) < versionOrder(props.version))
      .sort((left, right) => versionOrder(right) - versionOrder(left))
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
  if (target === currentMedia && element.tagName === 'VIDEO' && pendingSeekMs.value !== null) {
    element.currentTime = pendingSeekMs.value / 1000
    element.pause()
    updateVideoTime()
  }
  if (target === compareMedia && element.tagName === 'VIDEO') {
    syncComparisonPlayback(video.value?.paused ? 'pause' : 'play')
  }
}

function updateVideoTime() {
  currentTimeMs.value = Math.round(Number(video.value?.currentTime || 0) * 1000)
  if (comparisonVersionId.value && compareVideo.value && Math.abs(compareVideo.value.currentTime - Number(video.value?.currentTime || 0)) > 0.25) {
    compareVideo.value.currentTime = Number(video.value?.currentTime || 0)
  }
}

function handlePrimaryPlay() {
  if (props.selectedNote) emit('clear-note-focus')
  if (!props.feedbackMode && hasUnsavedAnnotations.value) {
    video.value?.pause()
    ElMessage.warning('当前画面标注尚未保存，请先保存问题或清空草稿后再继续播放')
    return
  }
  syncComparisonPlayback('play')
}

function captureCurrentTime({ notify = false } = {}) {
  updateVideoTime()
  video.value?.pause()
  emit('capture-time', currentTimeMs.value)
  if (notify) ElMessage.success(`已记录 ${formatMediaTime(currentTimeMs.value)}，请在右侧补充问题`)
}

function startIssueAtCurrentMedia() {
  if (currentKind.value === 'video') {
    captureCurrentTime({ notify: true })
  } else {
    emit('start-issue')
    ElMessage.success('请在右侧补充问题内容')
  }
}

function toggleAnnotationMode() {
  annotationMode.value = !annotationMode.value
  resetAnnotationGesture()
  if (annotationMode.value) {
    video.value?.pause()
    tool.value = 'rectangle'
    return
  }
  tool.value = 'navigate'
}

function toggleComparison() {
  if (comparisonVersionId.value) {
    comparisonVersionId.value = ''
    return
  }
  const previousVersion = comparisonVersions.value[0]
  if (previousVersion) comparisonVersionId.value = String(previousVersion.versionId)
}

function syncComparisonPlayback(action) {
  const current = video.value
  const comparison = compareVideo.value
  if (!current || !comparison || !comparisonVersionId.value) return
  if (Number.isFinite(current.currentTime)) comparison.currentTime = current.currentTime
  if (action === 'play') {
    const playResult = comparison.play?.()
    playResult?.catch?.(() => {})
  }
  if (action === 'pause') comparison.pause?.()
}

function pointFromEvent(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))
  }
}

function pointDistance(left, right) {
  return Math.hypot(right.x - left.x, right.y - left.y)
}

function appendFreehandPoint(points, point, { force = false } = {}) {
  const lastPoint = points.at(-1)
  if (!lastPoint) return [point]
  const distance = pointDistance(lastPoint, point)
  if (distance === 0 || (!force && distance < MIN_FREEHAND_POINT_DISTANCE)) return points
  if (points.length >= MAX_FREEHAND_POINTS) return [...points.slice(0, -1), point]
  return [...points, point]
}

function freehandPoints(item) {
  return item.points.map(point => `${point.x * 1000},${point.y * 1000}`).join(' ')
}

function freehandStrokeWidth(item) {
  return Math.max(3, Math.min(16, Number(item.strokeWidth || 0.008) * 1000))
}

function beginAnnotation(event) {
  if (!props.canAnnotate || tool.value === 'navigate') return
  dragStart.value = pointFromEvent(event)
  dragCurrent.value = dragStart.value
  dragPointerId.value = event.pointerId
  dragPath.value = tool.value === 'freehand' ? [dragStart.value] : []
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function moveAnnotation(event) {
  if (!dragStart.value || dragPointerId.value !== event.pointerId) return
  dragCurrent.value = pointFromEvent(event)
  if (tool.value === 'freehand') {
    dragPath.value = appendFreehandPoint(dragPath.value, dragCurrent.value)
  }
}

function resetAnnotationGesture(event = null) {
  if (event && dragPointerId.value !== null && event.currentTarget.hasPointerCapture?.(dragPointerId.value)) {
    event.currentTarget.releasePointerCapture?.(dragPointerId.value)
  }
  dragStart.value = null
  dragCurrent.value = null
  dragPointerId.value = null
  dragPath.value = []
}

function arrowStyle(item, width = sourceWidth.value, height = sourceHeight.value) {
  const [start, end] = item.points
  const aspectRatio = width / height
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
  if (!dragStart.value || dragPointerId.value !== event.pointerId || !props.canAnnotate || tool.value === 'navigate') return
  const end = pointFromEvent(event)
  const start = dragStart.value
  const freehandPath = tool.value === 'freehand'
    ? appendFreehandPoint(dragPath.value, end, { force: true })
    : []
  resetAnnotationGesture(event)
  const id = `annotation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  let item = null
  if (tool.value === 'point') {
    item = { id, type: 'point', color: '#ffb657', strokeWidth: 0.004, points: [end] }
  } else if (tool.value === 'rectangle') {
    item = { id, type: 'rectangle', color: '#ff6b6b', strokeWidth: 0.004, points: [start, end] }
  } else if (tool.value === 'arrow') {
    item = { id, type: 'arrow', color: '#68b5ff', strokeWidth: 0.004, points: [start, end] }
  } else if (tool.value === 'freehand') {
    item = { id, type: 'freehand', color: '#ff8a4c', strokeWidth: 0.008, points: freehandPath }
  } else if (tool.value === 'text') {
    const text = await requestAnnotationText()
    if (!text) return
    item = { id, type: 'text', color: '#ffd166', strokeWidth: 0, points: [end], text }
  }
  if (!item) return
  draftItems.value = [...draftItems.value, item]
  if (currentKind.value === 'video') captureCurrentTime()
  else emit('start-issue')
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
  annotationMode.value = false
  tool.value = 'navigate'
  resetAnnotationGesture()
  draftItems.value = []
  emitAnnotations()
}

function loadDraft(annotations = null, sourceTimeMs = null) {
  annotationMode.value = false
  tool.value = 'navigate'
  resetAnnotationGesture()
  draftItems.value = JSON.parse(JSON.stringify(annotations?.items || []))
  seekToDraft(sourceTimeMs)
}

function undoLastAnnotation() {
  if (!draftItems.value.length) return
  draftItems.value = draftItems.value.slice(0, -1)
  emitAnnotations()
}

function pulseMediaFocus() {
  noteFocusPulse.value = false
  if (focusTimer) clearTimeout(focusTimer)
  setTimeout(() => {
    noteFocusPulse.value = true
    focusTimer = setTimeout(() => { noteFocusPulse.value = false }, 1800)
  }, 0)
}

function seekToDraft(sourceTimeMs = null) {
  workspaceRoot.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  annotationMode.value = false
  tool.value = 'navigate'
  pulseMediaFocus()
  pendingSeekMs.value = null
  if (sourceTimeMs === null || sourceTimeMs === undefined) return
  const timeMs = Number(sourceTimeMs)
  if (!Number.isFinite(timeMs) || timeMs < 0) return
  pendingSeekMs.value = timeMs
  if (video.value) {
    video.value.currentTime = timeMs / 1000
    video.value.pause()
    updateVideoTime()
  }
}

function seekToNote() {
  if (!props.selectedNote) {
    pendingSeekMs.value = null
    noteFocusPulse.value = false
    if (focusTimer) clearTimeout(focusTimer)
    return
  }
  workspaceRoot.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  tool.value = 'navigate'
  annotationMode.value = false
  if (!selectedOnCurrentVersion.value && props.canCompare && selectedSourceVersionId.value) {
    comparisonVersionId.value = String(selectedSourceVersionId.value)
  }
  pulseMediaFocus()
  pendingSeekMs.value = null
  const sourceTimeMs = props.selectedNote?.mediaTimeMs
  if (sourceTimeMs === null || sourceTimeMs === undefined) return
  const timeMs = Number(sourceTimeMs)
  if (!Number.isFinite(timeMs) || timeMs < 0) return
  pendingSeekMs.value = timeMs
  if (video.value) {
    video.value.currentTime = timeMs / 1000
    video.value.pause()
    updateVideoTime()
  }
}

function isSelectedItem(item) {
  return selectedItems.value.some(selected => selected.id === item.id)
}

function isDraftItem(item) {
  return draftItems.value.some(draft => draft.id === item.id)
}

watch(currentMediaKey, async () => {
  annotationMode.value = false
  tool.value = 'navigate'
  resetAnnotationGesture()
  await loadCurrentMedia()
}, { immediate: true })
watch(() => props.version?.versionId, async () => {
  await loadComparisonOptions()
}, { immediate: true })
watch(comparisonVersionId, loadComparison)
watch(() => props.selectedNote?.noteId, seekToNote, { immediate: true })

onBeforeUnmount(() => {
  generation += 1
  currentController?.abort()
  compareController?.abort()
  historyController?.abort()
  if (focusTimer) clearTimeout(focusTimer)
  cleanupMedia(currentMedia)
  cleanupMedia(compareMedia)
})

defineExpose({ clearDraft, loadDraft, seekToDraft, seekToNote })
</script>

<template>
  <section ref="workspaceRoot" class="media-workspace">
    <header class="media-heading">
      <div><p class="sg-eyebrow">{{ feedbackMode ? 'REVIEW FEEDBACK' : 'REVIEW MEDIA' }}</p><h3>{{ feedbackMode ? '审核人标注画面' : '播放并检查作品' }}</h3><small>{{ feedbackMode ? '选择右侧意见，即可回到对应时间并查看画面标注。' : '直接播放作品；发现问题时，记录当前画面并在右侧补充说明。' }}</small></div>
    </header>

    <div v-if="!feedbackMode" class="review-flow" aria-label="审核操作流程">
      <span><b>1</b>播放检查</span><i aria-hidden="true">→</i>
      <span><b>2</b>发现问题就记录</span><i aria-hidden="true">→</i>
      <span><b>3</b>完成后提交结论</span>
    </div>

    <div v-if="selectedNote" class="note-focus-banner" :class="{ 'is-pulsing': noteFocusPulse }"><el-tag type="primary" effect="plain" size="small" round>正在查看意见</el-tag><strong>{{ selectedNoteSummary }}</strong><el-button text size="small" @click="emit('clear-note-focus')">退出定位</el-button><p>{{ selectedNote.content }}</p></div>

    <div class="media-columns" :class="{ 'has-comparison': comparisonVersionId }">
      <article class="media-column">
        <div class="media-label"><strong>{{ feedbackMode ? `反馈版本 · ${version.versionNumber}` : currentVersionLabel }} <el-tag v-if="playbackStatus" :type="playbackStatus.type" effect="plain" size="small" round :title="playbackStatus.title">{{ playbackStatus.label }}</el-tag></strong><span v-if="currentKind === 'video'">{{ formatMediaTime(currentTimeMs) }}</span></div>
        <div v-if="currentMedia.state === 'ready' && currentKind !== 'unsupported'" class="media-stage" :class="{ 'is-note-focus': noteFocusPulse }" :style="stageStyle">
          <img v-if="currentKind === 'image'" :src="currentMedia.url" alt="当前审核图片" @load="onMediaReady($event, currentMedia)" />
          <video v-else ref="video" :src="currentMedia.url" :poster="currentMedia.posterUrl || undefined" controls preload="metadata" @loadedmetadata="onMediaReady($event, currentMedia)" @play="handlePrimaryPlay" @pause="syncComparisonPlayback('pause')" @seeking="syncComparisonPlayback('seek')" @timeupdate="updateVideoTime" />
          <div class="annotation-layer" :data-active="annotationMode && tool !== 'navigate'" @pointerdown="beginAnnotation" @pointermove="moveAnnotation" @pointerup="finishAnnotation" @pointercancel="resetAnnotationGesture">
            <template v-for="item in visibleItems" :key="item.id">
              <span v-if="item.type === 'point'" class="annotation-point" :class="{ 'is-selected-note': isSelectedItem(item) || (noteFocusPulse && isDraftItem(item)) }" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'rectangle' && item.points.length > 1" class="annotation-rectangle" :class="{ 'is-selected-note': isSelectedItem(item) || (noteFocusPulse && isDraftItem(item)) }" :style="{ left: `${Math.min(item.points[0].x,item.points[1].x) * 100}%`, top: `${Math.min(item.points[0].y,item.points[1].y) * 100}%`, width: `${Math.abs(item.points[1].x-item.points[0].x) * 100}%`, height: `${Math.abs(item.points[1].y-item.points[0].y) * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'arrow' && item.points.length > 1" class="annotation-arrow" :class="{ 'is-selected-note': isSelectedItem(item) || (noteFocusPulse && isDraftItem(item)) }" :style="arrowStyle(item)"><i /></span>
              <svg v-else-if="item.type === 'freehand' && item.points.length" class="annotation-freehand" :class="{ 'is-selected-note': isSelectedItem(item) || (noteFocusPulse && isDraftItem(item)) }" :style="{ color: item.color }" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true"><polyline v-if="item.points.length > 1" :points="freehandPoints(item)" :stroke="item.color" :stroke-width="freehandStrokeWidth(item)" /><circle v-else :cx="item.points[0].x * 1000" :cy="item.points[0].y * 1000" :r="freehandStrokeWidth(item) / 2" :fill="item.color" /></svg>
              <span v-else-if="item.type === 'text' && item.points.length" class="annotation-text" :class="{ 'is-selected-note': isSelectedItem(item) || (noteFocusPulse && isDraftItem(item)) }" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, color: item.color }">{{ item.text }}</span>
            </template>
            <span v-if="activeAnnotationPreview?.type === 'rectangle'" class="annotation-rectangle is-drawing" :style="{ left: `${Math.min(activeAnnotationPreview.points[0].x,activeAnnotationPreview.points[1].x) * 100}%`, top: `${Math.min(activeAnnotationPreview.points[0].y,activeAnnotationPreview.points[1].y) * 100}%`, width: `${Math.abs(activeAnnotationPreview.points[1].x-activeAnnotationPreview.points[0].x) * 100}%`, height: `${Math.abs(activeAnnotationPreview.points[1].y-activeAnnotationPreview.points[0].y) * 100}%`, color: activeAnnotationPreview.color, borderColor: activeAnnotationPreview.color }" />
            <span v-else-if="activeAnnotationPreview?.type === 'arrow'" class="annotation-arrow is-drawing" :style="arrowStyle(activeAnnotationPreview)"><i /></span>
            <svg v-else-if="activeAnnotationPreview?.type === 'freehand' && activeAnnotationPreview.points.length" class="annotation-freehand is-drawing" :style="{ color: activeAnnotationPreview.color }" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true"><polyline v-if="activeAnnotationPreview.points.length > 1" :points="freehandPoints(activeAnnotationPreview)" :stroke="activeAnnotationPreview.color" :stroke-width="freehandStrokeWidth(activeAnnotationPreview)" /><circle v-else :cx="activeAnnotationPreview.points[0].x * 1000" :cy="activeAnnotationPreview.points[0].y * 1000" :r="freehandStrokeWidth(activeAnnotationPreview) / 2" :fill="activeAnnotationPreview.color" /></svg>
          </div>
        </div>
        <div v-else class="media-empty"><el-skeleton v-if="currentMedia.state === 'loading'" animated :rows="4" /><el-empty v-else :image-size="52" :description="!hasMedia ? '当前版本没有审核文件' : currentMedia.state === 'forbidden' ? '没有媒体下载权限' : currentMedia.state === 'error' ? currentMedia.error?.message : currentKind === 'unsupported' ? '该文件类型暂不支持内嵌预览' : '正在准备媒体…'" /></div>
        <div v-if="annotationMode" class="annotation-toolbar" role="toolbar" aria-label="画面标注方式">
          <div><strong>{{ tool === 'navigate' ? '查看模式，可操作视频播放控件' : '已暂停，请直接在画面上标注' }}</strong><span>{{ tool === 'navigate' ? '选择点、框选、箭头、涂抹或文字后，即可继续标注' : '标注会自动归入右侧正在编辑的问题' }}</span></div>
          <div class="annotation-toolbar__actions">
            <el-button size="small" :type="tool === 'navigate' ? 'primary' : 'default'" :icon="VideoPlay" title="切换为查看模式，可使用视频播放控件" @click="tool = 'navigate'">查看画面</el-button>
            <el-button size="small" :type="tool === 'point' ? 'primary' : 'default'" :icon="Aim" @click="tool = 'point'">点</el-button>
            <el-button size="small" :type="tool === 'rectangle' ? 'primary' : 'default'" :icon="Crop" @click="tool = 'rectangle'">框选</el-button>
            <el-button size="small" :type="tool === 'arrow' ? 'primary' : 'default'" :icon="TopRight" @click="tool = 'arrow'">箭头</el-button>
            <el-button size="small" :type="tool === 'freehand' ? 'primary' : 'default'" :icon="Brush" @click="tool = 'freehand'">涂抹</el-button>
            <el-button size="small" :type="tool === 'text' ? 'primary' : 'default'" :icon="EditPen" @click="tool = 'text'">文字</el-button>
            <el-button size="small" v-if="draftItems.length" @click="undoLastAnnotation">撤销上一步</el-button>
            <el-button size="small" v-if="draftItems.length" :icon="Delete" @click="clearDraft">清空</el-button>
          </div>
        </div>
        <div v-if="!feedbackMode && hasDraftContext" class="draft-link" aria-live="polite">
          <el-tag type="primary" effect="light" size="small" round>正在记录问题</el-tag>
          <strong v-if="draftMediaTimeMs !== null">时间 {{ formatMediaTime(draftMediaTimeMs) }}</strong>
          <strong v-if="draftAnnotationCount">标注 {{ draftAnnotationCount }} 处</strong>
          <span>{{ hasUnsavedAnnotations ? '标注未保存，保存或清空后才能继续播放' : '请在右侧补充说明并保存' }}</span>
        </div>
      </article>

      <article v-if="comparisonVersionId" class="media-column">
        <div class="media-label"><strong>历史版 · {{ comparisonVersion?.versionNumber || '加载中' }}</strong><span>{{ compareKind === 'video' ? '跟随当前版同步播放' : '只读对比' }}</span></div>
        <div v-if="compareMedia.state === 'ready' && compareKind !== 'unsupported'" class="media-stage" :class="{ 'is-note-focus': noteFocusPulse && comparisonSelectedItems.length }" :style="{ aspectRatio: `${compareMedia.width || 1} / ${compareMedia.height || 1}` }">
          <img v-if="compareKind === 'image'" :src="compareMedia.url" alt="对比版本图片" @load="onMediaReady($event, compareMedia)" />
          <video v-else ref="compareVideo" :src="compareMedia.url" :poster="compareMedia.posterUrl || undefined" :controls="false" muted preload="metadata" @loadedmetadata="onMediaReady($event, compareMedia)" />
          <div v-if="comparisonSelectedItems.length" class="annotation-layer">
            <template v-for="item in comparisonSelectedItems" :key="item.id">
              <span v-if="item.type === 'point'" class="annotation-point is-selected-note" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'rectangle' && item.points.length > 1" class="annotation-rectangle is-selected-note" :style="{ left: `${Math.min(item.points[0].x,item.points[1].x) * 100}%`, top: `${Math.min(item.points[0].y,item.points[1].y) * 100}%`, width: `${Math.abs(item.points[1].x-item.points[0].x) * 100}%`, height: `${Math.abs(item.points[1].y-item.points[0].y) * 100}%`, borderColor: item.color }" />
              <span v-else-if="item.type === 'arrow' && item.points.length > 1" class="annotation-arrow is-selected-note" :style="arrowStyle(item, compareMedia.width || 1, compareMedia.height || 1)"><i /></span>
              <svg v-else-if="item.type === 'freehand' && item.points.length" class="annotation-freehand is-selected-note" :style="{ color: item.color }" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true"><polyline v-if="item.points.length > 1" :points="freehandPoints(item)" :stroke="item.color" :stroke-width="freehandStrokeWidth(item)" /><circle v-else :cx="item.points[0].x * 1000" :cy="item.points[0].y * 1000" :r="freehandStrokeWidth(item) / 2" :fill="item.color" /></svg>
              <span v-else-if="item.type === 'text' && item.points.length" class="annotation-text is-selected-note" :style="{ left: `${item.points[0].x * 100}%`, top: `${item.points[0].y * 100}%`, color: item.color }">{{ item.text }}</span>
            </template>
          </div>
        </div>
        <div v-else class="media-empty"><el-skeleton v-if="compareMedia.state === 'loading'" animated :rows="4" /><el-empty v-else :image-size="52" :description="compareMedia.state === 'error' ? compareMedia.error?.message : '正在准备历史版本…'" /></div>
      </article>
      <div v-if="!feedbackMode && currentMedia.state === 'ready' && (canAnnotate || hasComparisonOptions)" class="record-action" :class="{ 'is-compare-only': !canAnnotate }">
        <div v-if="canAnnotate" class="record-action__primary">
          <el-button type="primary" :icon="Aim" @click="startIssueAtCurrentMedia">{{ recordActionLabel }}</el-button>
          <span>暂停作品并在右侧记录问题</span>
        </div>
        <div v-else class="record-action__summary"><strong>历史版本对比</strong><span>当前仅支持查看历史版本。</span></div>
        <div class="record-action__tools">
          <el-button v-if="canAnnotate" :type="annotationMode ? 'primary' : 'default'" plain :icon="Aim" @click="toggleAnnotationMode">{{ annotationMode ? '退出标注' : '标注此画面' }}</el-button>
          <el-select v-if="comparisonVersionId" v-model="comparisonVersionId" aria-label="选择对比版本" placeholder="选择历史版本" :loading="comparisonLoading">
            <el-option v-for="item in comparisonVersions" :key="item.versionId" :label="`${item.versionNumber} · ${item.changelog || '未填写修改说明'}`" :value="String(item.versionId)" />
          </el-select>
          <el-button v-if="hasComparisonOptions" :type="comparisonVersionId ? 'primary' : 'default'" plain @click="toggleComparison">{{ comparisonVersionId ? '退出对比' : '与上一版对比' }}</el-button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.media-workspace{display:grid;gap:14px;padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}
.media-heading,.media-label,.annotation-toolbar,.annotation-toolbar__actions,.record-action,.record-action__primary,.record-action__tools,.draft-link{display:flex;gap:10px;align-items:center}
.media-heading,.media-label,.annotation-toolbar,.record-action{justify-content:space-between}
.media-heading h3{margin:3px 0 0;font-size:17px}.media-heading small,.media-label span{color:var(--sg-text-muted);font-size:10px}
.review-flow{display:flex;gap:9px;align-items:center;padding:10px 12px;color:var(--sg-text-secondary);font-size:10px;background:linear-gradient(90deg,rgba(255,179,71,.09),rgba(104,181,255,.045));border:1px solid rgba(255,179,71,.22);border-radius:9px}
.review-flow span{display:flex;gap:6px;align-items:center;font-weight:650}.review-flow b{display:grid;width:20px;height:20px;color:var(--sg-accent);font-size:9px;background:var(--sg-accent-soft);border-radius:50%;place-items:center}.review-flow i{color:var(--sg-text-muted);font-style:normal}
.annotation-toolbar{padding:11px 12px;background:rgba(104,181,255,.07);border:1px solid rgba(104,181,255,.24);border-radius:9px}.annotation-toolbar>div:first-child{display:grid;gap:3px}.annotation-toolbar strong{font-size:11px}.annotation-toolbar span{color:var(--sg-text-muted);font-size:9px}.annotation-toolbar__actions{justify-content:flex-end;flex-wrap:wrap}
.media-columns{display:grid;align-items:start;gap:14px}.media-columns.has-comparison{grid-template-columns:repeat(2,minmax(0,1fr))}.media-column{display:grid;min-width:0;align-content:start;gap:10px}.media-label strong{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.media-stage{position:relative;overflow:hidden;max-height:620px;background:#050608;border:1px solid var(--sg-border-strong);border-radius:10px}.media-stage img,.media-stage video{display:block;width:100%;height:100%;object-fit:contain}.media-empty{display:grid;min-height:260px;color:var(--sg-text-muted);text-align:center;background:#080a0d;border:1px dashed var(--sg-border);border-radius:10px;place-items:center}
.record-action{grid-column:1/-1;padding:10px 12px;background:rgba(255,179,71,.06);border:1px solid rgba(255,179,71,.18);border-radius:9px}.record-action__primary{min-width:0}.record-action__primary span{color:var(--sg-text-muted);font-size:9px}.record-action__summary{display:grid;min-width:0;gap:3px}.record-action__summary strong{font-size:11px}.record-action__summary span{color:var(--sg-text-muted);font-size:9px}.record-action__tools{min-width:0;margin-left:auto;justify-content:flex-end;flex-wrap:wrap}.record-action__tools .el-select{width:230px;max-width:100%}.draft-link{flex-wrap:wrap;padding:9px 11px;background:rgba(104,181,255,.075);border:1px solid rgba(104,181,255,.24);border-radius:9px}.draft-link strong{font-size:10px}.draft-link span{margin-left:auto;color:var(--sg-text-secondary);font-size:9px}
.annotation-layer{position:absolute;inset:0;pointer-events:none}.annotation-layer[data-active=true]{cursor:crosshair;pointer-events:auto;touch-action:none}.annotation-point{position:absolute;width:18px;height:18px;border:3px solid;border-radius:50%;box-shadow:0 0 0 2px rgba(0,0,0,.6);transform:translate(-50%,-50%)}.annotation-rectangle{position:absolute;border:3px solid;box-shadow:0 0 0 1px rgba(0,0,0,.55)}.annotation-arrow{position:absolute;height:3px;background:currentColor;box-shadow:0 1px 2px rgba(0,0,0,.7);transform-origin:left center}.annotation-arrow i{position:absolute;top:50%;right:-2px;width:12px;height:12px;border-top:3px solid currentColor;border-right:3px solid currentColor;transform:translateY(-50%) rotate(45deg)}.annotation-freehand{position:absolute;z-index:1;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}.annotation-freehand polyline{fill:none;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}.annotation-freehand circle{vector-effect:non-scaling-stroke}.annotation-rectangle.is-drawing{border-style:dashed}.annotation-arrow.is-drawing,.annotation-rectangle.is-drawing,.annotation-freehand.is-drawing{z-index:3;pointer-events:none;filter:drop-shadow(0 0 5px currentColor)}.annotation-text{position:absolute;max-width:min(280px,60%);padding:5px 8px;font-size:12px;font-weight:700;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;background:rgba(0,0,0,.72);border:1px solid currentColor;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.4);transform:translateY(-50%)}
.note-focus-banner{display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;align-items:center;padding:10px 12px;background:rgba(104,181,255,.07);border:1px solid rgba(104,181,255,.22);border-radius:9px}.note-focus-banner strong{font-size:10px}.note-focus-banner p{grid-column:1/-1;margin:0;color:var(--sg-text-muted);font-size:9px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.note-focus-banner.is-pulsing{animation:note-focus-banner 1.2s ease-out}.media-stage.is-note-focus{box-shadow:0 0 0 2px rgba(104,181,255,.65),0 0 24px rgba(104,181,255,.18)}.annotation-point.is-selected-note,.annotation-rectangle.is-selected-note,.annotation-arrow.is-selected-note,.annotation-freehand.is-selected-note,.annotation-text.is-selected-note{z-index:2;filter:drop-shadow(0 0 6px currentColor);animation:selected-annotation 1s ease-in-out 2}.annotation-point.is-selected-note{box-shadow:0 0 0 5px rgba(255,255,255,.35),0 0 18px currentColor}
@keyframes note-focus-banner{0%{transform:translateY(-3px);box-shadow:0 0 0 0 rgba(104,181,255,.45)}100%{transform:translateY(0);box-shadow:0 0 0 12px rgba(104,181,255,0)}}@keyframes selected-annotation{50%{opacity:.45}}
@media(max-width:950px){.media-heading,.annotation-toolbar,.record-action{align-items:flex-start;flex-direction:column}.annotation-toolbar__actions,.record-action__tools{justify-content:flex-start}.record-action__tools,.record-action__tools .el-select{width:100%}.media-columns.has-comparison{grid-template-columns:1fr}.review-flow{align-items:flex-start;flex-direction:column}.review-flow i{display:none}.record-action__primary{align-items:flex-start;flex-direction:column}.draft-link span{width:100%;margin-left:0}}
</style>
