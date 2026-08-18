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
    <el-result class="error-card" icon="warning" title="403 · 无权访问此业务模块" sub-title="当前账号未获得所需的 Shot Grid 导航或业务权限。项目成员关系和具体操作仍由后端逐接口校验。">
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
