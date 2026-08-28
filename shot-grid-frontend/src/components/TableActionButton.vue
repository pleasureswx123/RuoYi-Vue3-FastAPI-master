<script setup>
import { computed } from 'vue'
import { ElButton } from 'element-plus'
import { useThemeStore } from '@/store/modules/theme'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  type: { type: String, default: '' },
  plain: { type: Boolean, default: true }
})
const themeStore = useThemeStore()
const colors = {
  primary: 'var(--sg-accent)',
  info: 'var(--sg-shot-status-in-progress)',
  warning: 'var(--sg-shot-status-unassigned)',
  danger: 'var(--sg-danger)'
}
const buttonColor = computed(() => Object.hasOwn(colors, props.type) ? colors[props.type] : 'var(--sg-text-secondary)')
const buttonTheme = computed(() => {
  const onColor = themeStore.isDark ? 'var(--sg-on-accent)' : 'var(--el-color-white)'
  return {
    '--el-button-bg-color': props.plain ? 'var(--sg-surface)' : buttonColor.value,
    '--el-button-text-color': props.plain ? buttonColor.value : onColor,
    // 亮色文字在暗色主题的实色悬停背景上对比不足，统一使用深色前景。
    '--el-button-hover-text-color': onColor,
    '--el-button-hover-bg-color': buttonColor.value,
    '--el-button-hover-border-color': buttonColor.value,
    '--el-button-active-text-color': onColor,
    '--el-button-outline-color': buttonColor.value,
    '--el-button-disabled-text-color': 'var(--sg-text-muted)',
    '--el-button-disabled-bg-color': 'var(--sg-fill-soft)',
    '--el-button-disabled-border-color': 'var(--sg-border)'
  }
})
</script>

<template>
  <el-button v-bind="$attrs" size="small" round :plain="plain" :type="type"
             :color="buttonColor" :dark="themeStore.isDark" :style="buttonTheme"
             :aria-label="label" :aria-description="hint || undefined">
    {{ label }}
  </el-button>
</template>
