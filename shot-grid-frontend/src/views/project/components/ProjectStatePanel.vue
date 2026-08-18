<script setup>
defineProps({
  title: { type: String, required: true },
  message: { type: String, required: true },
  retryable: { type: Boolean, default: false },
  compact: { type: Boolean, default: false }
})

defineEmits(['retry'])
</script>

<template>
  <div class="project-state" :class="{ 'project-state--compact': compact }">
    <el-alert :title="title" :description="message" type="error" show-icon :closable="false" />
    <el-button v-if="retryable" type="danger" plain @click="$emit('retry')">重新加载</el-button>
  </div>
</template>

<style scoped>
.project-state {
  display: grid;
  min-height: 260px;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 28px;
  background: rgba(255, 107, 107, 0.07);
  border: 1px solid rgba(255, 107, 107, 0.18);
  border-radius: var(--sg-radius-lg);
}

.project-state--compact {
  min-height: 0;
  padding: 20px;
}

.project-state :deep(.el-alert) {
  --el-alert-bg-color: transparent;
  padding: 0;
}

.project-state :deep(.el-alert__title) {
  color: var(--sg-text);
  font-size: 17px;
  font-weight: 700;
}

.project-state :deep(.el-alert__description) {
  margin-top: 8px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 640px) {
  .project-state {
    grid-template-columns: 1fr;
  }

  .project-state > .el-button {
    width: max-content;
  }
}
</style>
