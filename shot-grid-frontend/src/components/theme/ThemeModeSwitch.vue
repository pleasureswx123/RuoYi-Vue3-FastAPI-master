<script setup>
import { computed } from 'vue'
import { Moon, Sunny } from '@element-plus/icons-vue'

import { useThemeStore } from '@/store/modules/theme'

const themeStore = useThemeStore()

const isDark = computed({
  get: () => themeStore.isDark,
  set: value => themeStore.setDark(value)
})
const switchLabel = computed(() => (themeStore.isDark ? '切换到明亮模式' : '切换到暗黑模式'))
</script>

<template>
  <el-tooltip :content="switchLabel" placement="bottom" :show-after="350">
    <el-switch
      v-model="isDark"
      class="theme-mode-switch"
      size="small"
      :width="40"
      :active-action-icon="Moon"
      :inactive-action-icon="Sunny"
      :aria-label="switchLabel"
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
