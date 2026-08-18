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

    <el-result class="sg-boundary-panel" title="业务数据功能待接入" :sub-title="boundaryText">
      <template #icon><el-icon class="sg-boundary-panel__icon"><component :is="icon" /></el-icon></template>
      <template #extra>
        <el-tag class="sg-boundary-panel__tag" type="info" effect="plain" size="small" round>
          第一批仅完成应用基座 · 未使用 Mock 数据
        </el-tag>
      </template>
    </el-result>
  </section>
</template>

<style scoped>
.sg-boundary-panel__icon { font-size: 28px; }
.sg-boundary-panel:deep(.el-result__title p) { color: var(--sg-text); font-size: 21px; font-weight: 600; }
</style>
