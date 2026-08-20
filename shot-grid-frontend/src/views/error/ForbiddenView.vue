<script setup>
import { useRouter } from 'vue-router'

import { useSessionStore } from '@/store/modules/session'

const router = useRouter()
const session = useSessionStore()

async function returnToLogin() {
  await session.signOut().catch(() => undefined)
  await router.replace('/login')
}
</script>

<template>
  <main class="error-page">
    <el-result class="error-card" icon="warning" title="403 · 暂无访问权限" sub-title="当前账号无法访问此页面。如需使用，请联系项目管理人或平台管理员。">
      <template #extra><div class="error-card__actions">
        <el-button type="primary" @click="returnToLogin">退出并重新登录</el-button>
        <el-button @click="$router.replace('/')">返回可访问模块</el-button>
      </div></template>
    </el-result>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/styles/error-page';
</style>
