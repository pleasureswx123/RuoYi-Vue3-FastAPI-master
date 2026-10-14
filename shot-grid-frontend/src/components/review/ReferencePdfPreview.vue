<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps({ src: { type: String, required: true } })
const emit = defineEmits(['error'])
const canvas = ref(null)
const pageNumber = ref(1)
const pageCount = ref(0)
const loading = ref(true)
let documentTask = null
let pdf = null
let renderTask = null
let generation = 0

async function renderPage() {
  if (!pdf || !canvas.value) return
  const token = generation
  loading.value = true
  try {
    const page = await pdf.getPage(pageNumber.value)
    if (token !== generation) return
    const base = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({ scale: Math.min(1.5, 1600 / base.width, 2400 / base.height) })
    canvas.value.width = viewport.width
    canvas.value.height = viewport.height
    renderTask = page.render({ canvasContext: canvas.value.getContext('2d'), viewport })
    await renderTask.promise
  } catch (error) {
    if (token === generation && error?.name !== 'RenderingCancelledException') emit('error')
  } finally {
    if (token === generation) loading.value = false
  }
}

function release() {
  generation += 1
  renderTask?.cancel()
  renderTask = null
  documentTask?.destroy().catch(() => {})
  documentTask = null
  pdf = null
}

watch(() => props.src, async src => {
  release()
  const token = generation
  pageNumber.value = 1
  pageCount.value = 0
  loading.value = true
  try {
    documentTask = getDocument({ url: src, isEvalSupported: false })
    const loaded = await documentTask.promise
    if (token !== generation) return
    pdf = loaded
    pageCount.value = loaded.numPages
    await renderPage()
  } catch {
    if (token === generation) { loading.value = false; emit('error') }
  }
}, { immediate: true, flush: 'post' })

onBeforeUnmount(release)
</script>

<template>
  <section v-loading="loading" class="reference-pdf" element-loading-text="正在渲染 PDF…">
    <el-scrollbar max-height="62vh"><canvas ref="canvas" :aria-label="`PDF 第 ${pageNumber} 页`" /></el-scrollbar>
    <el-pagination v-model:current-page="pageNumber" :disabled="loading" :page-size="1" :total="pageCount" layout="prev, pager, next, total" @current-change="renderPage" />
  </section>
</template>

<style scoped>
.reference-pdf{display:grid;gap:12px;width:100%;min-height:220px;min-width:0}.reference-pdf canvas{display:block;max-width:100%;height:auto;margin:auto;background:white}
</style>
