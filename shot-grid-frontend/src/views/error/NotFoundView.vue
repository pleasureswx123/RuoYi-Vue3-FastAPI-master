<template>
  <main class="error-page">
    <el-result class="error-card" icon="info" title="404 · 页面不存在" sub-title="你访问的页面可能已移动、被删除，或链接地址不完整。请从工作台重新进入业务模块。">
      <template #extra><div class="error-card__actions">
        <el-button type="primary" @click="$router.replace('/')">返回可访问模块</el-button>
        <el-button @click="$router.back()">返回上一页</el-button>
      </div></template>
    </el-result>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/styles/error-page';
</style>
