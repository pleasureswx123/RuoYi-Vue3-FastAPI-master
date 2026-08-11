<script setup>
import { Compass } from '@element-plus/icons-vue'
</script>

<template>
  <main class="error-page">
    <div class="error-card">
      <span class="error-card__code">404</span>
      <span class="error-card__icon"><el-icon><Compass /></el-icon></span>
      <h1>页面不存在</h1>
      <p>你访问的页面可能已移动、被删除，或链接地址不完整。请从工作台重新进入业务模块。</p>
      <div class="error-card__actions">
        <el-button type="primary" @click="$router.replace('/')">返回可访问模块</el-button>
        <el-button @click="$router.back()">返回上一页</el-button>
      </div>
    </div>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/styles/error-page';
</style>
