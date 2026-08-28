<script setup>
import { computed } from 'vue'

import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'

const props = defineProps({
  target: { type: Object, required: true }
})

const isShot = computed(() => props.target?.targetType === 'shot')
const asset = computed(() => props.target?.asset || null)
const requirements = computed(() => String(props.target?.requirements || '').trim())
const primaryDescription = computed(() => String(
  isShot.value
    ? props.target?.shot?.description
    : asset.value?.itemDescription || asset.value?.assetDescription || ''
).trim())
const hasAdditionalRequirements = computed(() => (
  Boolean(requirements.value) && requirements.value !== primaryDescription.value
))
const assetTypeLabel = computed(() => ({
  Character: '角色',
  Environment: '场景',
  Prop: '道具'
})[asset.value?.assetType] || asset.value?.assetType || '—')
</script>

<template>
  <el-card class="review-production-target" shadow="never">
    <template #header>
      <header class="review-production-target__heading">
        <div>
          <p class="sg-eyebrow">AUDIT BASIS</p>
          <h3>审核依据</h3>
          <p>依据制作目标核对当前版本；本版具体改动仍以版本修改说明为准。</p>
        </div>
        <el-tag size="small" effect="plain" round>{{ isShot ? '镜头视频' : '资产图片' }}</el-tag>
      </header>
    </template>

    <ShotProductionInfo v-if="isShot" :shot="target.shot" />
    <el-descriptions v-else-if="asset" class="asset-production-info" :column="4" label-width="84px" border>
      <el-descriptions-item label="资产名称" :span="2">{{ asset.assetName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产类型">{{ assetTypeLabel }}</el-descriptions-item>
      <el-descriptions-item label="制作分项">{{ asset.productionItem || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产描述" :span="4">{{ asset.assetDescription || '—' }}</el-descriptions-item>
      <el-descriptions-item label="分项补充要求" :span="4">{{ asset.itemDescription || '—' }}</el-descriptions-item>
      <el-descriptions-item label="分项备注" :span="2">{{ asset.itemRemark || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产备注" :span="2">{{ asset.assetRemark || '—' }}</el-descriptions-item>
    </el-descriptions>

    <section v-if="hasAdditionalRequirements" class="review-production-target__additional" aria-label="任务补充要求">
      <strong>任务补充要求</strong>
      <p>{{ requirements }}</p>
    </section>
  </el-card>
</template>

<style scoped>
.review-production-target {
  background: var(--sg-surface);
  border-color: var(--sg-border);
}

.review-production-target__heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.review-production-target__heading h3,
.review-production-target__heading p {
  margin: 0;
}

.review-production-target__heading h3 {
  font-size: 17px;
}

.review-production-target__heading p:not(.sg-eyebrow) {
  margin-top: 5px;
  color: var(--sg-text-muted);
  font-size: 10px;
}

.asset-production-info:deep(.el-descriptions__body),
.asset-production-info:deep(.el-descriptions__table) {
  background: transparent;
}

.asset-production-info:deep(.el-descriptions__table) {
  table-layout: fixed;
}

.asset-production-info:deep(.el-descriptions__cell) {
  padding: 13px !important;
  background: var(--sg-surface-raised) !important;
  border-color: var(--sg-border) !important;
}

.asset-production-info:deep(.el-descriptions__label) {
  min-width: 84px;
  color: var(--sg-text-muted) !important;
  font-size: 10px;
  white-space: nowrap;
}

.asset-production-info:deep(.el-descriptions__content) {
  color: var(--sg-text-secondary) !important;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.review-production-target__additional {
  display: grid;
  gap: 6px;
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--sg-accent-soft);
  border-radius: 9px;
}

.review-production-target__additional strong {
  color: var(--sg-accent);
  font-size: 11px;
}

.review-production-target__additional p {
  margin: 0;
  color: var(--sg-text-secondary);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

@media (max-width: 650px) {
  .review-production-target__heading {
    flex-direction: column;
  }

  .asset-production-info:deep(.el-descriptions__label) {
    width: 72px !important;
    min-width: 72px;
    white-space: normal;
  }
}
</style>
