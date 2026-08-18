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
    <el-result class="error-card" icon="error" title="服务暂时不可用" sub-title="平台暂时无法完成身份或业务导航加载。为避免把服务异常伪装成空数据，本次访问已停止。">
      <template #extra><div class="error-card__actions">
        <el-button type="primary" @click="$router.go(0)">重新加载</el-button>
        <el-button @click="returnToLogin">退出并重新登录</el-button>
      </div></template>
    </el-result>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/styles/error-page';
</style>
