<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, Refresh, User } from '@element-plus/icons-vue'

import { useSessionStore } from '@/store/modules/session'
import { sanitizeInternalRedirect } from '@/router/routeRegistry'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const formRef = ref()
const submitting = ref(false)
const errorMessage = ref('')
const form = reactive({ username: '', password: '', code: '' })

const captcha = computed(() => sessionStore.captcha || {})
const captchaEnabled = computed(() => captcha.value.enabled !== false)
const captchaImage = computed(() => captcha.value.image || captcha.value.img || '')
const captchaLoading = computed(() => Boolean(captcha.value.loading))

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  code: [
    {
      validator: (_rule, value, callback) => {
        if (captchaEnabled.value && !value) callback(new Error('请输入验证码'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

function getSafeRedirect() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  return sanitizeInternalRedirect(redirect, '/')
}

async function refreshCaptcha(clearError = true) {
  if (clearError) errorMessage.value = ''
  try {
    await sessionStore.loadCaptcha()
  } catch (error) {
    errorMessage.value = error?.message || '验证码加载失败，请刷新后重试'
    throw error
  }
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || submitting.value) return

  submitting.value = true
  errorMessage.value = ''
  try {
    await sessionStore.signIn({
      username: form.username.trim(),
      password: form.password,
      code: form.code.trim(),
      uuid: captcha.value.uuid || ''
    })
    await router.replace(getSafeRedirect())
  } catch (error) {
    errorMessage.value = error?.message || '登录失败，请稍后重试'
    form.code = ''
    if (captchaEnabled.value) await refreshCaptcha(false).catch(() => undefined)
  } finally {
    form.password = ''
    submitting.value = false
  }
}

onMounted(() => refreshCaptcha().catch(() => undefined))
</script>

<template>
  <main class="login-page">
    <section class="login-scene" aria-label="Shot Grid 产品介绍">
      <div class="login-scene__frame-lines" aria-hidden="true"></div>
      <div class="login-scene__content">
        <p class="login-scene__eyebrow">AI FILM PRODUCTION</p>
        <h1>让每一个镜头，<br />沿着清晰的制作链路完成。</h1>
        <p>
          Shot Grid 连接项目、镜头、资产、版本与审核，让团队在同一个业务空间中协作。
        </p>
        <div class="login-scene__sequence" aria-hidden="true">
          <span>PROJECT</span><i></i><span>SHOT</span><i></i><span>VERSION</span><i></i><span>REVIEW</span>
        </div>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-form-wrap">
        <div class="login-brand">
          <span class="login-brand__mark" aria-hidden="true"><i></i><i></i><i></i></span>
          <div><strong>SHOT GRID</strong><small>影视制作协作平台</small></div>
        </div>

        <div class="login-heading">
          <p>欢迎回来</p>
          <h2>登录制作工作区</h2>
          <span>使用平台分配的账号继续工作</span>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
          <el-form-item label="账号" prop="username">
            <el-input
              v-model="form.username"
              :prefix-icon="User"
              autocomplete="username"
              placeholder="请输入账号"
              size="large"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              :prefix-icon="Lock"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
              show-password
              size="large"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-form-item v-if="captchaEnabled" label="验证码" prop="code">
            <div class="captcha-field">
              <el-input
                v-model="form.code"
                autocomplete="off"
                placeholder="请输入验证码"
                size="large"
                @keyup.enter="submit"
              />
              <button
                class="captcha-image"
                type="button"
                aria-label="刷新验证码"
                :disabled="captchaLoading"
                @click="refreshCaptcha"
              >
                <img v-if="captchaImage" :src="captchaImage" alt="验证码" />
                <el-icon v-else :class="{ 'is-loading': captchaLoading }"><Refresh /></el-icon>
              </button>
            </div>
          </el-form-item>

          <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>

          <el-button class="login-submit" type="primary" size="large" native-type="submit" :loading="submitting">
            进入工作区
          </el-button>
        </el-form>

        <p class="login-security">登录信息通过平台统一认证，本应用不会持久化保存密码。</p>
      </div>
    </section>
  </main>
</template>

<style scoped lang="scss">
.login-page {
  display: grid;
  min-height: 100vh;
  grid-template-columns: minmax(0, 1.2fr) minmax(420px, 0.8fr);
  background: #090b0f;
}

.login-scene {
  position: relative;
  display: flex;
  min-height: 100vh;
  align-items: flex-end;
  padding: clamp(48px, 7vw, 104px);
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(7, 9, 13, 0.05), rgba(7, 9, 13, 0.92)),
    radial-gradient(circle at 65% 30%, rgba(255, 181, 87, 0.25), transparent 27%),
    linear-gradient(135deg, #232833 0%, #121721 46%, #090b0f 100%);
}

.login-scene::before,
.login-scene::after {
  position: absolute;
  content: '';
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 50%;
}

.login-scene::before {
  top: 12%;
  right: -12%;
  width: min(46vw, 620px);
  aspect-ratio: 1;
}

.login-scene::after {
  top: 26%;
  right: 6%;
  width: min(24vw, 320px);
  aspect-ratio: 1;
}

.login-scene__frame-lines {
  position: absolute;
  inset: 28px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.login-scene__frame-lines::before,
.login-scene__frame-lines::after {
  position: absolute;
  width: 54px;
  height: 54px;
  content: '';
  border-color: var(--sg-accent);
  border-style: solid;
}

.login-scene__frame-lines::before {
  top: -1px;
  left: -1px;
  border-width: 2px 0 0 2px;
}

.login-scene__frame-lines::after {
  right: -1px;
  bottom: -1px;
  border-width: 0 2px 2px 0;
}

.login-scene__content {
  position: relative;
  z-index: 1;
  max-width: 760px;
}

.login-scene__eyebrow {
  margin: 0 0 18px;
  color: var(--sg-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.24em;
}

.login-scene h1 {
  margin: 0;
  font-size: clamp(38px, 5vw, 68px);
  font-weight: 600;
  letter-spacing: -0.055em;
  line-height: 1.14;
}

.login-scene__content > p:not(.login-scene__eyebrow) {
  max-width: 620px;
  margin: 28px 0 38px;
  color: rgba(243, 245, 247, 0.68);
  font-size: 15px;
  line-height: 1.85;
}

.login-scene__sequence {
  display: flex;
  gap: 12px;
  align-items: center;
  color: rgba(243, 245, 247, 0.44);
  font-size: 9px;
  letter-spacing: 0.16em;
}

.login-scene__sequence i {
  width: 30px;
  height: 1px;
  background: rgba(255, 255, 255, 0.2);
}

.login-panel {
  display: grid;
  min-height: 100vh;
  padding: 48px clamp(34px, 5vw, 76px);
  background: rgba(12, 15, 20, 0.98);
  border-left: 1px solid var(--sg-border);
  place-items: center;
}

.login-form-wrap {
  width: min(100%, 420px);
}

.login-brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: clamp(52px, 9vh, 94px);
}

.login-brand__mark {
  display: flex;
  width: 38px;
  height: 38px;
  gap: 3px;
  align-items: flex-end;
  justify-content: center;
  padding: 8px;
  background: var(--sg-accent);
  border-radius: 11px;
}

.login-brand__mark i { width: 4px; background: #17130e; border-radius: 2px; }
.login-brand__mark i:nth-child(1) { height: 10px; }
.login-brand__mark i:nth-child(2) { height: 20px; }
.login-brand__mark i:nth-child(3) { height: 15px; }

.login-brand strong,
.login-brand small {
  display: block;
}

.login-brand strong { font-size: 14px; letter-spacing: 0.14em; }
.login-brand small { margin-top: 3px; color: var(--sg-text-muted); font-size: 10px; }

.login-heading {
  margin-bottom: 34px;
}

.login-heading p {
  margin: 0 0 8px;
  color: var(--sg-accent);
  font-size: 12px;
  font-weight: 700;
}

.login-heading h2 {
  margin: 0 0 10px;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.login-heading span {
  color: var(--sg-text-secondary);
  font-size: 13px;
}

.captcha-field {
  display: grid;
  width: 100%;
  gap: 10px;
  grid-template-columns: minmax(0, 1fr) 122px;
}

.captcha-image {
  display: grid;
  height: 40px;
  padding: 0;
  overflow: hidden;
  color: var(--sg-text-secondary);
  cursor: pointer;
  background: #fff;
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-sm);
  place-items: center;
}

.captcha-image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.captcha-image:disabled { cursor: wait; opacity: 0.65; }

.login-error {
  margin: -2px 0 16px;
  color: var(--sg-danger);
  font-size: 12px;
  line-height: 1.6;
}

.login-submit {
  width: 100%;
  margin-top: 8px;
  color: #17130e;
  font-weight: 700;
}

.login-security {
  margin: 22px 0 0;
  color: var(--sg-text-muted);
  font-size: 11px;
  line-height: 1.6;
  text-align: center;
}

:deep(.el-form-item__label) {
  color: var(--sg-text-secondary);
  font-size: 12px;
}

:deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.035);
  box-shadow: 0 0 0 1px var(--sg-border) inset;
}

@media (max-width: 940px) {
  .login-page { grid-template-columns: 1fr; }
  .login-scene { display: none; }
  .login-panel { border-left: 0; }
}

@media (max-width: 520px) {
  .login-panel { padding: 28px 20px; }
  .login-brand { margin-bottom: 54px; }
}
</style>
