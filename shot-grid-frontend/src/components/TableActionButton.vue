<script setup>
import { computed } from 'vue'
import { ElButton } from 'element-plus'
import { useThemeStore } from '@/store/modules/theme'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  type: { type: String, default: '' },
  color: { type: String, default: undefined },
  plain: { type: Boolean, default: true },
  round: { type: Boolean, default: true },
  elementPalette: { type: Boolean, default: false }
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
  if (props.elementPalette) {
    // 操作列使用标准蓝色主按钮，交互及禁用状态由 Element Plus 处理。
    const background = themeStore.isDark ? '#141414' : '#ffffff'
    return {
      '--el-color-primary': '#409eff',
      '--el-color-primary-dark-2': '#337ecc',
      ...Object.fromEntries([3, 5, 7, 8, 9].map(level => [
        `--el-color-primary-light-${level}`,
        `color-mix(in srgb, #409eff ${(10 - level) * 10}%, ${background})`
      ]))
    }
  }
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
  <el-button v-bind="$attrs" size="small" :round="round" :plain="plain" :type="type"
             :color="elementPalette ? color : buttonColor" :dark="themeStore.isDark" :style="buttonTheme"
             :aria-label="label" :aria-description="hint || undefined">
    {{ label }}
  </el-button>
</template>
