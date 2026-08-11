<script setup>
import ReviewAnnotationPanel from '@/components/review/ReviewAnnotationPanel.vue'
defineProps({ versionId: { type: String, required: true } })
</script>
<template><section class="page"><span class="eyebrow">VERSION / {{ versionId }}</span><h1>版本审核</h1><ReviewAnnotationPanel :version-id="versionId" /></section></template>
