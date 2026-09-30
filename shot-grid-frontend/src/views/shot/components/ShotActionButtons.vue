<script setup>
import TableActionButton from '@/components/TableActionButton.vue'

defineProps({ actions: { type: Array, required: true } })
</script>

<template>
  <div class="shot-row-actions" role="group" aria-label="镜头操作" @click.stop @keydown.stop>
    <TableActionButton v-for="action in actions" :key="action.key" element-palette :round="false"
                       v-bind="action.button" @click="action.run" />
  </div>
</template>

<style scoped>
.shot-row-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.shot-row-actions :deep(.el-button) { margin-left: 0; padding: 5px; }
</style>
