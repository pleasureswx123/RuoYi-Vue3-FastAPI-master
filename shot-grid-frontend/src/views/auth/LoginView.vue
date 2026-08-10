<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const submitting = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '', code: '', uuid: '' })

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await userStore.signIn(form)
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/workbench'
    await router.replace(target)
  } catch (reason) {
    error.value = reason.message || '登录失败，请重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-intro"><span class="eyebrow">SHOT GRID</span><h1>让每一个镜头<br>都有清晰的下一步。</h1><p>独立的影视制作协作工作台，连接项目、镜头、资产与审核。</p></section>
    <el-card class="login-card" shadow="never">
      <h2>欢迎回来</h2><p>使用平台账号进入工作台</p>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="账号"><el-input v-model="form.username" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" /></el-form-item>
        <el-button native-type="submit" type="primary" size="large" :loading="submitting">进入 Shot Grid</el-button>
      </el-form>
    </el-card>
  </main>
</template>
