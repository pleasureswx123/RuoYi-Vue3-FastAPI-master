<script setup>
import { computed, nextTick, ref } from 'vue'
import { Moon, Sunny } from '@element-plus/icons-vue'

import { useThemeStore } from '@/store/modules/theme'

const themeStore = useThemeStore()
const switchRef = ref(null)
const transitionOrigin = ref(null)
const transitioning = ref(false)

const switchLabel = computed(() => (themeStore.isDark ? '切换到明亮模式' : '切换到暗黑模式'))

function rememberTransitionOrigin(event) {
  transitionOrigin.value = {
    x: event.clientX,
    y: event.clientY
  }
}

function resolveTransitionOrigin() {
  if (transitionOrigin.value) return transitionOrigin.value

  const element = switchRef.value?.$el
  const rect = element?.getBoundingClientRect?.()
  if (rect) {
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    }
  }

  return {
    x: window.innerWidth / 2,
    y: window.innerHeight / 2
  }
}

async function switchTheme(nextIsDark) {
  if (transitioning.value || nextIsDark === themeStore.isDark) return

  const { x, y } = resolveTransitionOrigin()
  const prefersReducedMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const supportsViewTransition = typeof document.startViewTransition === 'function'
    && typeof document.documentElement.animate === 'function'
    && !prefersReducedMotion

  transitionOrigin.value = null

  if (!supportsViewTransition) {
    themeStore.setDark(nextIsDark)
    return
  }

  transitioning.value = true
  const root = document.documentElement
  let transition = null
  try {
    root.classList.add('sg-theme-transitioning')
    transition = document.startViewTransition(async () => {
      themeStore.setDark(nextIsDark)
      await nextTick()
    })
    await transition.ready

    const endRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    )
    const clipPath = [`circle(0px at ${x}px ${y}px)`, `circle(${endRadius}px at ${x}px ${y}px)`]

    const animation = root.animate(
      {
        clipPath
      },
      {
        duration: 650,
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        fill: 'forwards',
        pseudoElement: '::view-transition-new(root)'
      }
    )
    await Promise.all([transition.finished, animation.finished])
  } catch {
    transition?.skipTransition?.()
    if (themeStore.isDark !== nextIsDark) {
      themeStore.setDark(nextIsDark)
    }
  } finally {
    root.classList.remove('sg-theme-transitioning')
    transitioning.value = false
  }
}
</script>

<template>
  <el-tooltip :content="switchLabel" placement="bottom" :show-after="350">
    <el-switch
      ref="switchRef"
      :model-value="themeStore.isDark"
      class="theme-mode-switch"
      size="small"
      :width="40"
      :disabled="transitioning"
      :active-action-icon="Moon"
      :inactive-action-icon="Sunny"
      :aria-label="switchLabel"
      @pointerdown="rememberTransitionOrigin"
      @change="switchTheme"
    />
  </el-tooltip>
</template>

<style scoped>
.theme-mode-switch {
  flex: 0 0 auto;
  --el-switch-on-color: var(--sg-theme-switch-track);
  --el-switch-off-color: var(--sg-theme-switch-track);
  --el-switch-border-color: var(--sg-theme-switch-border);
}

.theme-mode-switch:deep(.el-switch__core) {
  min-width: 40px;
  height: 20px;
  border: 1px solid var(--sg-theme-switch-border);
  box-shadow: var(--sg-theme-switch-shadow);
}

.theme-mode-switch:deep(.el-switch__action) {
  width: 16px;
  height: 16px;
  color: var(--sg-theme-switch-icon);
  background: var(--sg-theme-switch-action);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
}

.theme-mode-switch:deep(.el-switch__action .el-icon) {
  color: inherit;
  font-size: 12px;
}
</style>
