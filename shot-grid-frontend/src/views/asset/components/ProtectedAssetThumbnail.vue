<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Box, Lock, Picture } from '@element-plus/icons-vue'
import { ElImage } from 'element-plus'

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
    <div v-if="state === 'ready'" class="asset-thumbnail__preview" @click.stop>
      <ElImage
        class="asset-thumbnail__image"
        :src="objectUrl"
        :preview-src-list="[objectUrl]"
        :alt="alt"
        fit="contain"
        hide-on-click-modal
        preview-teleported
      />
    </div>
    <el-skeleton v-else-if="state === 'loading'" class="asset-thumbnail__loading" animated>
      <template #template><el-skeleton-item variant="image" class="asset-thumbnail__skeleton" /></template>
    </el-skeleton>
    <el-empty v-else class="asset-thumbnail__placeholder" :description="message" :image-size="28" :title="message">
      <template #image>
        <el-icon v-if="state === 'forbidden'"><Lock /></el-icon>
        <el-icon v-else-if="state === 'missing' || state === 'error'"><Picture /></el-icon>
        <el-icon v-else><Box /></el-icon>
      </template>
    </el-empty>
  </div>
</template>

<style scoped>
.asset-thumbnail{position:relative;width:100%;height:100%;overflow:hidden;background:var(--sg-surface-soft)}.asset-thumbnail__preview,.asset-thumbnail__image,.asset-thumbnail__loading{position:absolute;inset:0;width:100%;height:100%}.asset-thumbnail__image{cursor:zoom-in}.asset-thumbnail__image:deep(.el-image__inner){width:100%;height:100%;object-position:center}.asset-thumbnail__skeleton{width:100%;height:100%}.asset-thumbnail__placeholder{position:absolute;inset:0;padding:4px}.asset-thumbnail__placeholder:deep(.el-empty__image){height:auto;margin-bottom:3px}.asset-thumbnail__placeholder:deep(.el-empty__description){margin-top:0}.asset-thumbnail__placeholder:deep(.el-empty__description p){color:var(--sg-text-muted);font-size:10px}.asset-thumbnail__placeholder .el-icon{font-size:23px}
</style>
