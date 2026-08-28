<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '@/store/modules/session'
import { sanitizeInternalRedirect } from '@/router/routeRegistry'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const retrying = ref(false)

async function retryPage() {
  if (retrying.value) return
  const retry = sanitizeInternalRedirect(route.query.retry, '/')
  const target = router.resolve(retry).path === route.path ? '/' : retry
  retrying.value = true
  try {
    // 重新进入原业务地址，由路由守卫重试账号和导航，不能只刷新公开的异常页。
    await router.replace(target)
  } catch {
    ElMessage.error('重新加载失败，请稍后重试')
  } finally {
    retrying.value = false
  }
}

async function returnToLogin() {
  await session.signOut().catch(() => undefined)
  await router.replace('/login')
}
</script>

<template>
  <main class="error-page">
    <el-result class="error-card" icon="error" title="服务暂时不可用" sub-title="平台暂时无法加载账号信息或页面内容，请稍后重新加载。">
      <template #extra><div class="error-card__actions">
        <el-button type="primary" :loading="retrying" @click="retryPage">重新加载</el-button>
        <el-button :disabled="retrying" @click="returnToLogin">退出并重新登录</el-button>
      </div></template>
    </el-result>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/styles/error-page';
</style>
