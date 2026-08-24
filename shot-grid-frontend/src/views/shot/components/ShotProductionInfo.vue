<script setup>
import { computed } from 'vue'

const props = defineProps({
  shot: { type: Object, required: true },
  layout: {
    type: String,
    default: 'wide',
    validator: value => ['wide', 'dialog'].includes(value)
  }
})

const columnCount = computed(() => props.layout === 'dialog' ? 2 : 4)
const contentSpan = computed(() => columnCount.value)
const narrativeSpan = computed(() => props.layout === 'dialog' ? 2 : 2)
</script>

<template>
  <div class="shot-production-info" :class="`shot-production-info--${layout}`" aria-label="镜头完整制作信息">
    <el-descriptions :column="columnCount" :label-width="layout === 'dialog' ? '92px' : '84px'" border>
      <el-descriptions-item label="制作内容" :span="contentSpan">
        <span class="shot-production-info__description">{{ shot.description || '—' }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="景别">{{ shot.shotSize || '—' }}</el-descriptions-item>
      <el-descriptions-item label="机位">{{ shot.cameraPosition || '—' }}</el-descriptions-item>
      <el-descriptions-item label="镜头运动">{{ shot.cameraMovement || '—' }}</el-descriptions-item>
      <el-descriptions-item label="焦段">{{ shot.focalLength || '—' }}</el-descriptions-item>
      <el-descriptions-item label="台词 / 对白" :span="narrativeSpan">{{ shot.dialogue || '—' }}</el-descriptions-item>
      <el-descriptions-item label="音效" :span="narrativeSpan">{{ shot.soundEffect || '—' }}</el-descriptions-item>
      <el-descriptions-item label="色调参考" :span="narrativeSpan">{{ shot.colorReference || '—' }}</el-descriptions-item>
      <el-descriptions-item label="备注" :span="narrativeSpan">{{ shot.remark || '—' }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<style scoped>
.shot-production-info {
  overflow: hidden;
  border: 1px solid var(--sg-border);
  border-radius: 10px;
}

.shot-production-info:deep(.el-descriptions__body),
.shot-production-info:deep(.el-descriptions__table) {
  background: transparent;
}

.shot-production-info:deep(.el-descriptions__table) {
  table-layout: fixed;
}

.shot-production-info:deep(.el-descriptions__cell) {
  padding: 13px !important;
  background: var(--sg-surface-raised) !important;
  border-color: var(--sg-border) !important;
}

.shot-production-info:deep(.el-descriptions__label) {
  min-width: 84px;
  color: var(--sg-text-muted) !important;
  font-size: 10px;
  white-space: nowrap;
}

.shot-production-info:deep(.el-descriptions__content) {
  color: var(--sg-text-secondary) !important;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  word-break: break-word;
}

.shot-production-info__description {
  display: block;
  color: var(--sg-text);
  line-height: 1.65;
}

.shot-production-info--dialog:deep(.el-descriptions__label) {
  min-width: 92px;
}

@media (max-width: 650px) {
  .shot-production-info:deep(.el-descriptions__cell) {
    padding: 10px !important;
  }

  .shot-production-info:deep(.el-descriptions__label) {
    width: 72px !important;
    min-width: 72px;
    white-space: normal;
  }
}
</style>
