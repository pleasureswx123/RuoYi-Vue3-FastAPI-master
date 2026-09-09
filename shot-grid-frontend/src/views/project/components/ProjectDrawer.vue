<script setup>
import { ElDrawer } from 'element-plus'
const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  wide: { type: Boolean, default: false },
  closeGuard: { type: Function, default: null }
})

const emit = defineEmits(['close'])

async function beforeClose(done) {
  if (props.busy) return
  if (props.closeGuard && !await props.closeGuard()) return
  if (!props.busy) done()
}

function closeDialog() {
  if (!props.busy) emit('close')
}
</script>

<template>
  <el-drawer
    :model-value="true"
    class="project-drawer"
    :size="wide ? 'min(880px, 100vw)' : 'min(620px, 100vw)'"
    append-to-body
    direction="rtl"
    :before-close="beforeClose"
    destroy-on-close
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    :aria-label="title"
    @close="closeDialog"
  >
    <template #header>
      <div class="project-drawer__heading">
        <p class="sg-eyebrow">SHOT GRID</p>
        <h2>{{ title }}</h2>
        <p v-if="description" class="project-drawer__description">{{ description }}</p>
      </div>
    </template>
    <div class="project-drawer__body" v-loading="busy"><slot /></div>
    <template v-if="$slots.footer" #footer><slot name="footer" /></template>
  </el-drawer>
</template>

<style scoped>
.project-drawer__heading h2,
.project-drawer__description {
  margin: 0;
}

.project-drawer__heading h2 {
  font-size: 23px;
}

.project-drawer__description {
  margin-top: 8px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.project-drawer__body {
  min-height: 1px;
}

:global(.project-drawer) {
  --el-drawer-bg-color: var(--sg-surface-raised);
  border: 1px solid var(--sg-border-strong);
  box-shadow: 0 28px 100px rgba(0, 0, 0, 0.52);
}

:global(.project-drawer .el-drawer__header) {
  margin-right: 0;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--sg-border);
}

:global(.project-drawer .el-drawer__headerbtn) {
  top: 18px;
  right: 20px;
}

:global(.project-drawer .el-drawer__body) {
  min-height: 0;
  overflow: auto;
  padding: 24px 28px 28px;
  color: var(--sg-text);
}

:global(.project-drawer .el-drawer__footer) {
  flex-shrink: 0;
  padding: 16px 28px;
  border-top: 1px solid var(--sg-border);
  background: var(--sg-surface-raised);
}

@media (max-width: 640px) {
  :global(.project-drawer) {
    width: 100vw !important;
  }

  :global(.project-drawer .el-drawer__header),
  :global(.project-drawer .el-drawer__body),
  :global(.project-drawer .el-drawer__footer) {
    padding-right: 18px;
    padding-left: 18px;
  }
}
</style>
