<script setup>
import { Close } from '@element-plus/icons-vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  wide: { type: Boolean, default: false }
})

defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div class="project-modal-backdrop" @mousedown.self="!busy && $emit('close')">
      <section
        class="project-modal"
        :class="{ 'project-modal--wide': wide }"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header>
          <div>
            <p class="sg-eyebrow">SHOT GRID</p>
            <h2>{{ title }}</h2>
            <p v-if="description" class="project-modal__description">{{ description }}</p>
          </div>
          <button class="project-modal__close" type="button" :disabled="busy" aria-label="关闭" @click="$emit('close')">
            <el-icon><Close /></el-icon>
          </button>
        </header>
        <div class="project-modal__body"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.project-modal-backdrop {
  position: fixed;
  z-index: 3000;
  inset: 0;
  display: grid;
  overflow: auto;
  padding: 28px;
  background: rgba(4, 6, 9, 0.78);
  backdrop-filter: blur(10px);
  place-items: start center;
}

.project-modal {
  width: min(100%, 620px);
  margin: auto;
  background: var(--sg-surface-raised);
  border: 1px solid var(--sg-border-strong);
  border-radius: var(--sg-radius-lg);
  box-shadow: 0 28px 100px rgba(0, 0, 0, 0.52);
}

.project-modal--wide {
  width: min(100%, 880px);
}

header {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 26px 28px 22px;
  border-bottom: 1px solid var(--sg-border);
}

h2,
.project-modal__description {
  margin: 0;
}

h2 {
  font-size: 23px;
}

.project-modal__description {
  margin-top: 8px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.project-modal__close {
  display: grid;
  width: 38px;
  height: 38px;
  color: var(--sg-text-secondary);
  cursor: pointer;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--sg-border);
  border-radius: 10px;
  place-items: center;
}

.project-modal__close:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.project-modal__body {
  padding: 26px 28px 30px;
}

@media (max-width: 640px) {
  .project-modal-backdrop {
    padding: 0;
  }

  .project-modal {
    min-height: 100vh;
    border-radius: 0;
  }

  header,
  .project-modal__body {
    padding-right: 20px;
    padding-left: 20px;
  }
}
</style>
