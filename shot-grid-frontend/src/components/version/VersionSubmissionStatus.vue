<script setup>
import { computed } from 'vue'
import { CircleCheck, Clock, WarningFilled } from '@element-plus/icons-vue'

import { submissionStatusMeta, submissionStatusOrder } from './versionPresentation'

const props = defineProps({
  submission: { type: Object, required: true },
  pollError: { type: Object, default: null }
})

const meta = computed(() => submissionStatusMeta(props.submission?.submissionStatus))
const activeStep = computed(() => Math.max(0, submissionStatusOrder.indexOf(props.submission?.submissionStatus)))
const isFailed = computed(() => props.submission?.submissionStatus === 'failed')
const isCommitted = computed(() => props.submission?.submissionStatus === 'committed')
</script>

<template>
  <section class="submission-status" :data-tone="meta.tone" role="status">
    <header>
      <span class="submission-status__icon">
        <el-icon><CircleCheck v-if="isCommitted" /><WarningFilled v-else-if="isFailed" /><Clock v-else /></el-icon>
      </span>
      <div>
        <p class="sg-eyebrow">VERSION SUBMISSION</p>
        <h4>{{ meta.label }} · {{ submission.reservedVersionNumber || '版本号分配中' }}</h4>
        <p>{{ meta.description }}</p>
      </div>
      <el-tag :type="meta.tone === 'danger' ? 'danger' : meta.tone === 'success' ? 'success' : 'warning'" effect="dark">
        {{ submission.submissionStatus }}
      </el-tag>
    </header>

    <ol v-if="!isFailed" class="status-track" aria-label="版本发布进度">
      <li
        v-for="(status, index) in submissionStatusOrder"
        :key="status"
        :class="{ active: index === activeStep, completed: index < activeStep || isCommitted }"
      >
        <span>{{ index + 1 }}</span>
        <small>{{ submissionStatusMeta(status).label }}</small>
      </li>
    </ol>

    <dl class="status-facts">
      <div><dt>业务文件名</dt><dd>{{ submission.businessFileName || '—' }}</dd></div>
      <div><dt>提交编号</dt><dd>#{{ submission.submissionId }}</dd></div>
      <div><dt>尝试次数</dt><dd>{{ submission.attemptCount ?? 0 }}</dd></div>
      <div v-if="submission.versionId"><dt>正式版本</dt><dd>#{{ submission.versionId }}</dd></div>
    </dl>

    <p v-if="submission.submissionStatus === 'pending'" class="worker-boundary">
      若长时间停留在“等待发布”，可能是版本 Worker 尚未启用或当前进程未取得 Leader；此时文件只在平台私有区，不能视为版本成功。
    </p>
    <p v-if="submission.replayed" class="worker-boundary">
      后端已按同一幂等键恢复原提交；没有创建重复版本号或重复文件。
    </p>
    <div v-if="isFailed" class="failure-detail" role="alert">
      <strong>{{ submission.lastErrorMessage || '版本发布失败，尚未形成正式版本。' }}</strong>
      <code v-if="submission.lastErrorKey">{{ submission.lastErrorKey }}</code>
    </div>
    <div v-if="pollError" class="poll-error" role="alert">
      <strong>{{ pollError.title }}</strong>
      <span>{{ pollError.message }}</span>
      <code v-if="pollError.errorKey">{{ pollError.errorKey }}</code>
    </div>
  </section>
</template>

<style scoped lang="scss">
.submission-status {
  padding: 22px;
  background: rgba(255, 182, 87, 0.045);
  border: 1px solid rgba(255, 182, 87, 0.2);
  border-radius: var(--sg-radius-md);
}

.submission-status[data-tone='success'] { background: rgba(56, 189, 130, 0.06); border-color: rgba(56, 189, 130, 0.24); }
.submission-status[data-tone='danger'] { background: rgba(244, 92, 92, 0.06); border-color: rgba(244, 92, 92, 0.25); }

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
  display: grid;
  padding: 0;
  margin: 24px 0;
  list-style: none;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.status-track li { position: relative; display: grid; gap: 7px; color: var(--sg-text-muted); text-align: center; place-items: center; }
.status-track li::before { position: absolute; top: 12px; right: 50%; left: -50%; height: 1px; content: ''; background: var(--sg-border); }
.status-track li:first-child::before { display: none; }
.status-track li span { position: relative; z-index: 1; display: grid; width: 25px; height: 25px; font-size: 10px; background: var(--sg-surface-raised); border: 1px solid var(--sg-border-strong); border-radius: 50%; place-items: center; }
.status-track li.completed span,
.status-track li.active span { color: #17120b; background: var(--sg-accent); border-color: var(--sg-accent); }
.status-track li.completed,
.status-track li.active { color: var(--sg-text-secondary); }

.status-facts { display: grid; margin: 0; grid-template-columns: 2fr repeat(3, 1fr); gap: 10px; }
.status-facts div { min-width: 0; padding: 11px 13px; background: rgba(0, 0, 0, 0.14); border-radius: 9px; }
.status-facts dt { color: var(--sg-text-muted); font-size: 10px; }
.status-facts dd { margin: 5px 0 0; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.worker-boundary { margin: 14px 0 0; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.65; }
.failure-detail,
.poll-error { display: flex; padding: 12px 14px; margin-top: 14px; color: #ffb5ad; background: rgba(244, 92, 92, 0.08); border-radius: 9px; gap: 8px; flex-wrap: wrap; font-size: 12px; }
.failure-detail code,
.poll-error code { color: inherit; }

@media (max-width: 720px) {
  .submission-status header { grid-template-columns: auto minmax(0, 1fr); }
  .submission-status header .el-tag { grid-column: 2; justify-self: start; }
  .status-track small { display: none; }
  .status-facts { grid-template-columns: 1fr 1fr; }
}
</style>
