<script setup>
import { Edit } from '@element-plus/icons-vue'

defineProps({
  label: { type: String, required: true },
  title: { type: String, default: '' },
  disabled: Boolean
})
defineEmits(['edit'])
</script>

<template>
  <div class="shot-table-field" :title="disabled ? title : undefined">
    <div class="shot-table-field__value"><slot /></div>
    <el-button
      class="shot-table-field__edit" text circle size="small" :icon="disabled ? undefined : Edit"
      :aria-label="label" :title="title || label" :disabled="disabled" @click.stop="$emit('edit', $event)"
    />
  </div>
</template>

<style scoped>
.shot-table-field { display: flex; align-items: center; gap: 4px; }
.shot-table-field__value { flex: 1; min-width: 0; overflow: hidden; overflow-wrap: anywhere; }
.shot-table-field__edit { flex: none; }
.shot-table-field__edit:disabled { display: none; }
.shot-table-field :deep(small) { display: block; color: var(--sg-text-muted); font-size: 11px; }
</style>
