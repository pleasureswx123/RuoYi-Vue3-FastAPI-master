<script setup>
defineProps({ code: { type: String, required: true }, title: { type: String, required: true }, description: { type: String, required: true } })
</script>
<template><main class="error-page"><span class="error-code">{{ code }}</span><h1>{{ title }}</h1><p>{{ description }}</p><RouterLink class="primary-link" to="/workbench">返回工作台</RouterLink></main></template>
