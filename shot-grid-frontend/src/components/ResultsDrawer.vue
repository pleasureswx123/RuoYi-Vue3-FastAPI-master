<script setup>
import { ref } from 'vue'
import { ElDrawer } from 'element-plus'

const width = ref('min(440px, 40vw)')
let startX = 0
let startWidth = 0

function startResize(event) {
  startX = event.clientX
  // 非模态抽屉从实际可见宽度起拖，兼容窗口大小改变后的再次拖动。
  startWidth = event.currentTarget.closest('.el-drawer').getBoundingClientRect().width
}

function resize(event) {
  const maximum = document.documentElement.clientWidth / 2
  const minimum = Math.min(260, maximum * 0.75)
  width.value = Math.min(maximum, Math.max(minimum, startWidth + startX - event.clientX)) + 'px'
}
</script>

<template>
  <ElDrawer
    class="sg-results-resizable"
    :style="{ '--sg-results-width': width }"
    direction="rtl"
    resizable
    @resize-start="startResize"
    @resize="resize"
  >
    <template v-if="$slots.header" #header><slot name="header" /></template>
    <slot />
  </ElDrawer>
</template>

<style>
.el-drawer.rtl.sg-results-resizable {
  /* Element Plus 拖动时会写入内联宽度；保留非模态抽屉的半屏上限。 */
  width: var(--sg-results-width) !important;
  max-width: 50%;
  --el-drawer-dragger-size: 10px;
}
.sg-results-resizable > .el-drawer__dragger::before {
  left: 0;
  background-color: var(--el-border-color);
}
</style>
