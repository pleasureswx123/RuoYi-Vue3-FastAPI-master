<script setup>
import { Warning } from '@element-plus/icons-vue'

defineProps({
  title: { type: String, required: true },
  message: { type: String, required: true },
  retryable: { type: Boolean, default: false },
  compact: { type: Boolean, default: false }
})

defineEmits(['retry'])
</script>

<template>
  <section class="project-state" :class="{ 'project-state--compact': compact }" role="alert">
    <el-icon><Warning /></el-icon>
    <div>
      <h2>{{ title }}</h2>
      <p>{{ message }}</p>
    </div>
    <el-button v-if="retryable" plain @click="$emit('retry')">重新加载</el-button>
  </section>
</template>

<style scoped>
.project-state {
  display: grid;
  min-height: 260px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 28px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-lg);
}

.project-state--compact {
  min-height: 0;
  padding: 20px;
}

.project-state > .el-icon {
  color: var(--sg-accent);
  font-size: 28px;
}

h2,
p {
  margin: 0;
}

h2 {
  font-size: 17px;
}

p {
  margin-top: 6px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 640px) {
  .project-state {
    grid-template-columns: auto 1fr;
  }

  .project-state .el-button {
    grid-column: 1 / -1;
  }
}
</style>
