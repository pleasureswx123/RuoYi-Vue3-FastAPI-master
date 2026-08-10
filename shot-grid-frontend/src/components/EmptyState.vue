<script setup>
defineProps({ title: { type: String, required: true }, description: { type: String, default: '' } })
</script>

<template>
  <section class="empty-state">
    <span class="empty-state__mark" aria-hidden="true">SG</span>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
  </section>
</template>
