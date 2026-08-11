<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Box, Lock, Picture } from '@element-plus/icons-vue'

import { downloadAssetThumbnail } from '@/api/shot-grid/assets'

const props = defineProps({
  thumbnail: { type: Object, default: null },
  alt: { type: String, default: '资产缩略图' }
})
const state = ref('empty')
const objectUrl = ref('')
let controller = null

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

async function loadThumbnail() {
  controller?.abort()
  revokeObjectUrl()
  const url = props.thumbnail?.url
  if (!url) {
    state.value = 'empty'
    return
  }
  const requestController = new AbortController()
  controller = requestController
  state.value = 'loading'
  try {
    const blob = await downloadAssetThumbnail(url, { signal: requestController.signal })
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
onBeforeUnmount(() => {
  controller?.abort()
  revokeObjectUrl()
})
</script>

<template>
  <div class="asset-thumbnail" :data-state="state">
    <img v-if="state === 'ready'" :src="objectUrl" :alt="alt" />
    <div v-else class="asset-thumbnail__placeholder" :title="message">
      <el-icon v-if="state === 'forbidden'"><Lock /></el-icon>
      <el-icon v-else-if="state === 'missing' || state === 'error'"><Picture /></el-icon>
      <el-icon v-else><Box /></el-icon>
      <span>{{ message }}</span>
    </div>
  </div>
</template>

<style scoped>
.asset-thumbnail{display:grid;width:100%;height:100%;overflow:hidden;background:linear-gradient(135deg,#242830,#11151a);place-items:center}.asset-thumbnail img{width:100%;height:100%;object-fit:cover}.asset-thumbnail__placeholder{display:grid;width:100%;height:100%;gap:5px;align-content:center;color:var(--sg-text-muted);font-size:10px;text-align:center;place-items:center}.asset-thumbnail__placeholder .el-icon{font-size:23px}.asset-thumbnail[data-state=loading] .el-icon{animation:asset-thumbnail-pulse 1s ease-in-out infinite}@keyframes asset-thumbnail-pulse{50%{opacity:.35}}
</style>
