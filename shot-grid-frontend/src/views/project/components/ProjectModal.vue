<script setup>
const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  wide: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

function closeDialog() {
  if (!props.busy) emit('close')
}
</script>

<template>
  <el-dialog
    :model-value="true"
    class="project-dialog"
    :width="wide ? 'min(880px, calc(100vw - 32px))' : 'min(620px, calc(100vw - 32px))'"
    append-to-body
    align-center
    destroy-on-close
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    :aria-label="title"
    @close="closeDialog"
  >
    <template #header>
      <div class="project-dialog__heading">
        <p class="sg-eyebrow">SHOT GRID</p>
        <h2>{{ title }}</h2>
        <p v-if="description" class="project-dialog__description">{{ description }}</p>
      </div>
    </template>
    <div class="project-dialog__body" v-loading="busy"><slot /></div>
  </el-dialog>
</template>

<style scoped>
.project-dialog__heading h2,
.project-dialog__description {
  margin: 0;
}

.project-dialog__heading h2 {
  font-size: 23px;
}

.project-dialog__description {
  margin-top: 8px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.project-dialog__body {
  min-height: 1px;
}

:global(.project-dialog) {
  --el-dialog-bg-color: var(--sg-surface-raised);
  --el-dialog-border-radius: var(--sg-radius-lg);
  margin: 16px auto;
  border: 1px solid var(--sg-border-strong);
  box-shadow: 0 28px 100px rgba(0, 0, 0, 0.52);
}

:global(.project-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--sg-border);
}

:global(.project-dialog .el-dialog__headerbtn) {
  top: 18px;
  right: 20px;
}

:global(.project-dialog .el-dialog__body) {
  padding: 24px 28px 28px;
  color: var(--sg-text);
}

@media (max-width: 640px) {
  :global(.project-dialog) {
    width: calc(100vw - 16px) !important;
  }

  :global(.project-dialog .el-dialog__header),
  :global(.project-dialog .el-dialog__body) {
    padding-right: 18px;
    padding-left: 18px;
  }
}
</style>
