<script setup>
import { computed } from 'vue'
import { finalBadge } from './finalPresentation'
const props = defineProps({ row: { type: Object, required: true } })
const badge = computed(() => finalBadge(props.row))
</script>
<template><el-tag v-if="badge" size="small" :type="badge.type" effect="light" class="final-version-tag">{{ badge.label }}</el-tag></template>
<style scoped>.el-tag.final-version-tag { max-width: 100%; height: auto; white-space: normal; line-height: 1.5; text-align: left; }</style>
