<script setup>
import { computed } from 'vue'
import { CircleCheck, Clock, WarningFilled } from '@element-plus/icons-vue'

import { tagTypeFromTone } from '@/utils/tag'
import { submissionStatusMeta, submissionStatusOrder } from './versionPresentation'

const props = defineProps({
  submission: { type: Object, required: true },
  pollError: { type: Object, default: null }
})

const meta = computed(() => submissionStatusMeta(props.submission?.submissionStatus))
const activeStep = computed(() => Math.max(0, submissionStatusOrder.indexOf(props.submission?.submissionStatus)))
const isFailed = computed(() => props.submission?.submissionStatus === 'failed')
const isCommitted = computed(() => props.submission?.submissionStatus === 'committed')
const stepsActive = computed(() => isCommitted.value ? submissionStatusOrder.length : activeStep.value)
</script>

<template>
  <el-card class="submission-status" :data-tone="meta.tone" shadow="never" role="status">
    <header>
      <span class="submission-status__icon">
        <el-icon><CircleCheck v-if="isCommitted" /><WarningFilled v-else-if="isFailed" /><Clock v-else /></el-icon>
      </span>
      <div>
        <p class="sg-eyebrow">VERSION SUBMISSION</p>
        <h4>{{ meta.label }} · {{ submission.reservedVersionNumber || '版本号分配中' }}</h4>
        <p>{{ meta.description }}</p>
      </div>
      <el-tag :type="tagTypeFromTone(meta.tone)" effect="dark" size="small" round>
        {{ meta.label }}
      </el-tag>
    </header>

    <el-steps
      v-if="!isFailed"
      class="status-track"
      :active="stepsActive"
      finish-status="success"
      process-status="process"
      align-center
      aria-label="版本发布进度"
    >
      <el-step
        v-for="(status, index) in submissionStatusOrder"
        :key="status"
        :title="submissionStatusMeta(status).label"
        :description="index === activeStep && !isCommitted ? '当前阶段' : ''"
      />
    </el-steps>

    <el-descriptions class="status-facts" :column="4" border size="small">
      <el-descriptions-item label="业务文件名">{{ submission.businessFileName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="提交编号">#{{ submission.submissionId }}</el-descriptions-item>
      <el-descriptions-item label="尝试次数">{{ submission.attemptCount ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="正式版本">{{ submission.versionId ? `#${submission.versionId}` : '尚未形成' }}</el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="submission.submissionStatus === 'pending'"
      class="worker-boundary"
      title="仍在等待后台发布"
      description="若长时间停留在此阶段，可能是版本 Worker 尚未启用或当前进程未取得 Leader；文件此时只在平台私有区，不能视为版本成功。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="submission.replayed"
      class="worker-boundary"
      title="已恢复原提交"
      description="后端已按同一幂等键恢复原提交，没有创建重复版本号或重复文件。"
      type="success"
      :closable="false"
      show-icon
    />
    <el-alert v-if="isFailed" class="failure-detail" title="版本发布失败" :description="[submission.lastErrorMessage || '尚未形成正式版本，请查看诊断后重试。', submission.lastErrorKey].filter(Boolean).join(' · ')" type="error" :closable="false" show-icon />
    <el-alert v-if="pollError" class="poll-error" :title="pollError.title" :description="[pollError.message, pollError.errorKey].filter(Boolean).join(' · ')" type="error" :closable="false" show-icon />
  </el-card>
</template>

<style scoped lang="scss">
.submission-status {
  --el-card-bg-color: rgba(255, 182, 87, 0.045);
  --el-card-border-color: rgba(255, 182, 87, 0.2);
  background: var(--el-card-bg-color);
  border-color: var(--el-card-border-color);
  border-radius: var(--sg-radius-md);
}

.submission-status:deep(.el-card__body) { padding: 22px; }
.submission-status[data-tone='success'] { --el-card-bg-color: rgba(56, 189, 130, 0.06); --el-card-border-color: rgba(56, 189, 130, 0.24); }
.submission-status[data-tone='danger'] { --el-card-bg-color: rgba(244, 92, 92, 0.06); --el-card-border-color: rgba(244, 92, 92, 0.25); }

.submission-status header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
}

.submission-status__icon {
  display: grid;
  width: 40px;
  height: 40px;
  color: var(--sg-accent);
  background: var(--sg-accent-soft);
  border-radius: 12px;
  place-items: center;
}

.submission-status h4 { margin: 3px 0 6px; font-size: 16px; }
.submission-status header p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.65; }

.status-track {
  margin: 24px 0;
}

.status-track:deep(.el-step__title) { color: var(--sg-text-secondary); font-size: 11px; }
.status-track:deep(.el-step__description) { color: var(--sg-accent); font-size: 9px; }
.status-track:deep(.el-step__line) { background: var(--sg-border); }
.status-facts:deep(.el-descriptions__body),
.status-facts:deep(.el-descriptions__table) { background: transparent; }
.status-facts:deep(.el-descriptions__cell) { background: rgba(0, 0, 0, 0.14) !important; border-color: var(--sg-border) !important; }
.status-facts:deep(.el-descriptions__label) { color: var(--sg-text-muted) !important; font-size: 10px; }
.status-facts:deep(.el-descriptions__content) { color: var(--sg-text-secondary) !important; font-size: 12px; overflow-wrap: anywhere; }
.worker-boundary,
.failure-detail,
.poll-error { margin-top: 14px; }
.failure-detail code,
.poll-error code { color: inherit; }

@media (max-width: 720px) {
  .submission-status header { grid-template-columns: auto minmax(0, 1fr); }
  .submission-status header .el-tag { grid-column: 2; justify-self: start; }
  .status-track:deep(.el-step__title) { font-size: 9px; }
  .status-track:deep(.el-step__description) { display: none; }
  .status-facts { overflow-x: auto; }
}
</style>
