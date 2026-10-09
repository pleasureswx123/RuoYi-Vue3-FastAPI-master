<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'

import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'

const props = defineProps({
  target: { type: Object, required: true },
  taskId: { type: Number, default: null },
  projectId: { type: Number, default: null },
  canReadReferences: Boolean
})

const detail = ref(null)
const loading = ref(false)
const error = ref('')
let generation = 0
let controller
async function loadReferences() {
  const token = ++generation
  controller?.abort()
  detail.value = null
  error.value = ''
  loading.value = false
  if (!props.canReadReferences || !props.taskId || !props.projectId) return
  controller = new AbortController()
  loading.value = true
  try {
    const { data } = await getTaskDetail(props.taskId, { signal: controller.signal })
    if (token !== generation) return
    if (Number(data.taskId) !== props.taskId || Number(data.project?.projectId) !== props.projectId) throw new Error('资料范围已变化')
    detail.value = data
  } catch (failure) {
    if (token === generation) error.value = [403, 404].includes(Number(failure?.httpStatus || failure?.status))
      ? '暂无权限读取制作资料，或任务已不可见。' : '资料加载失败，请重试。'
  } finally { if (token === generation) loading.value = false }
}
const referenceState = computed(() => !props.canReadReferences ? '暂无权限读取项目资料与参考附件。'
  : loading.value ? '正在加载资料…' : error.value || (!detail.value ? '资料暂不可用。' : ''))
watch(() => [props.taskId, props.projectId, props.canReadReferences, props.target], loadReferences, { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })

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
          <p>对照当前项目资料、制作目标与任务要求；本版具体改动以版本修改说明为准。</p>
        </div>
        <el-tag size="small" effect="plain" round>{{ isShot ? '镜头视频' : '资产图片' }}</el-tag>
      </header>
    </template>

    <section class="review-basis-section" aria-label="项目资料">
      <h4>项目资料</h4>
      <el-descriptions class="asset-production-info" :column="1" label-width="96px" size="small" border>
        <el-descriptions-item label="资料说明">{{ referenceState || detail?.projectReferenceDescription || '暂无资料说明。' }}</el-descriptions-item>
        <el-descriptions-item label="参考附件"><ReviewReferenceFiles v-if="detail?.projectReferenceFiles?.length" :files="detail.projectReferenceFiles" compact /><span v-else>{{ referenceState || '暂无参考附件。' }}</span></el-descriptions-item>
      </el-descriptions>
      <el-button v-if="error && canReadReferences" link type="primary" :loading="loading" @click="loadReferences">重新加载资料</el-button>
    </section>
    <section class="review-basis-section" :aria-label="isShot ? '镜头信息' : '资产信息'">
    <h4>{{ isShot ? '镜头信息' : '资产信息' }}</h4>
    <ShotProductionInfo v-if="isShot" :shot="target.shot" />
    <el-descriptions v-else-if="asset" class="asset-production-info" :column="4" label-width="96px" size="small" border>
      <el-descriptions-item label="资产名称" :span="2">{{ asset.assetName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产类型">{{ assetTypeLabel }}</el-descriptions-item>
      <el-descriptions-item label="制作分项">{{ asset.productionItem || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产描述" :span="4">{{ asset.assetDescription || '—' }}</el-descriptions-item>
      <el-descriptions-item label="分项补充要求" :span="4">{{ asset.itemDescription || '—' }}</el-descriptions-item>
      <el-descriptions-item label="分项备注" :span="2">{{ asset.itemRemark || '—' }}</el-descriptions-item>
      <el-descriptions-item label="资产备注" :span="2">{{ asset.assetRemark || '—' }}</el-descriptions-item>
    </el-descriptions>

    </section>
    <section class="review-basis-section" aria-label="制作要求">
      <h4>制作要求</h4>
      <el-descriptions class="asset-production-info" :column="1" label-width="96px" size="small" border>
        <el-descriptions-item :label="isShot && hasAdditionalRequirements ? '任务补充要求' : '制作要求'">{{ requirements || '暂无额外制作要求。' }}</el-descriptions-item>
        <el-descriptions-item label="参考说明">{{ referenceState || detail?.referenceDescription || '暂无参考说明。' }}</el-descriptions-item>
        <el-descriptions-item label="参考附件"><ReviewReferenceFiles v-if="detail?.referenceFiles?.length" :files="detail.referenceFiles" compact /><span v-else>{{ referenceState || '暂无参考附件。' }}</span></el-descriptions-item>
      </el-descriptions>
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
  padding: 8px 10px !important;
  background: var(--sg-surface-raised) !important;
  border-color: var(--sg-border) !important;
}

.asset-production-info:deep(.el-descriptions__label) {
  min-width: 84px;
  color: var(--sg-text-muted) !important;
  font-size: 12px;
  font-weight: 500;
  white-space: normal;
}

.asset-production-info:deep(.el-descriptions__content) {
  color: var(--sg-text-secondary) !important;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.review-basis-section + .review-basis-section { margin-top: 16px; }
.review-basis-section h4 { margin: 0 0 8px; font-size: 14px; }

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
