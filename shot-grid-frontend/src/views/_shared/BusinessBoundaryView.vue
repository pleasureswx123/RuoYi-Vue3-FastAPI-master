<script setup>
defineProps({
  eyebrow: { type: String, required: true },
  title: { type: String, required: true },
  description: { type: String, required: true },
  icon: { type: Object, required: true },
  boundaryText: { type: String, required: true }
})
</script>

<template>
  <section class="sg-page">
    <header class="sg-page-heading">
      <div>
        <p class="sg-eyebrow">{{ eyebrow }}</p>
        <h2 class="sg-page-title">{{ title }}</h2>
        <p class="sg-page-description">{{ description }}</p>
      </div>
    </header>

    <div class="sg-boundary-panel">
      <div>
        <span class="sg-boundary-panel__icon"><el-icon><component :is="icon" /></el-icon></span>
        <h2>业务数据功能待接入</h2>
        <p>{{ boundaryText }}</p>
        <span class="sg-boundary-panel__meta">
          <i class="sg-boundary-panel__dot"></i>
          第一批仅完成应用基座 · 未使用 Mock 数据
        </span>
      </div>
    </div>
  </section>
</template>
