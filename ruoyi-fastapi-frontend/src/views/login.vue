<template>
  <main class="admin-login" :style="{ '--company-logo-image': `url(${companyLogoUrl})` }">
    <section class="brand-scene" aria-label="SHOT GRID 管理平台介绍">
      <div class="brand-scene__frame" aria-hidden="true"></div>
      <img
        class="brand-scene__company-logo"
        :src="companyLogoUrl"
        alt="LAPUTTA"
        width="1231"
        height="267"
      />

      <div class="brand-scene__content">
        <p class="brand-scene__eyebrow">SHOT GRID · MANAGEMENT CONSOLE</p>
        <h1>连接制作现场，<br />也守住平台边界。</h1>
        <p class="brand-scene__description">
          面向项目、成员、角色、存储与系统配置的统一管理入口，让影视制作协作始终运行在清晰、可靠的权限体系中。
        </p>
        <ul class="brand-scene__capabilities" aria-label="平台管理能力">
          <li><span>01</span>项目治理</li>
          <li><span>02</span>权限配置</li>
          <li><span>03</span>存储运维</li>
        </ul>
      </div>

      <p class="brand-scene__caption">AI 影视短片制作 · 平台管理端</p>
    </section>

    <section class="login-panel" aria-label="登录区域">
      <div class="login-panel__glow" aria-hidden="true"></div>
      <div class="login-card">
        <div class="mobile-company-logo" role="img" aria-label="LAPUTTA"></div>

        <div class="product-brand">
          <span class="product-brand__mark" aria-hidden="true">
            <el-icon><Histogram /></el-icon>
          </span>
          <span class="product-brand__copy">
            <strong>SHOT GRID</strong>
            <small>影视制作平台 · 管理控制台</small>
          </span>
        </div>

        <header class="login-heading">
          <p>ADMINISTRATION</p>
          <h2>登录管理平台</h2>
          <span>使用平台管理员账号继续操作</span>
        </header>

        <el-form
          ref="loginRef"
          :model="loginForm"
          :rules="loginRules"
          class="login-form"
          label-position="top"
          aria-label="登录管理平台"
        >
          <el-form-item label="用户名称" prop="username">
            <el-input
              v-model="loginForm.username"
              :prefix-icon="User"
              :disabled="loading"
              type="text"
              size="large"
              autocomplete="username"
              placeholder="请输入用户名称"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="loginForm.password"
              :prefix-icon="Lock"
              :disabled="loading"
              type="password"
              size="large"
              autocomplete="current-password"
              placeholder="请输入密码"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item v-if="captchaEnabled" label="验证码" prop="code">
            <div class="captcha-field">
              <el-input
                v-model="loginForm.code"
                :disabled="loading"
                size="large"
                autocomplete="off"
                placeholder="请输入验证码"
                @keyup.enter="handleLogin"
              />
              <el-button
                class="captcha-button"
                :disabled="captchaLoading || loading"
                aria-label="刷新验证码"
                @click="getCode"
              >
                <img v-if="codeUrl" :src="codeUrl" alt="验证码，点击刷新" />
                <el-icon v-else :class="{ 'is-loading': captchaLoading }"><Refresh /></el-icon>
              </el-button>
            </div>
          </el-form-item>

          <div class="login-options">
            <el-checkbox v-model="loginForm.rememberMe" :disabled="loading">记住密码</el-checkbox>
            <span>仅建议在个人设备上使用</span>
          </div>

          <el-form-item class="login-action">
            <el-button
              class="login-submit"
              :loading="loading"
              :disabled="loading"
              size="large"
              type="primary"
              @click="handleLogin"
            >
              {{ loading ? '正在登录…' : '进入管理平台' }}
            </el-button>
          </el-form-item>

          <div v-if="register" class="register-entry">
            <span>还没有平台账号？</span>
            <router-link class="register-entry__link" to="/register">申请注册</router-link>
          </div>
        </el-form>

        <div class="login-notice">
          <el-icon aria-hidden="true"><CircleCheckFilled /></el-icon>
          <span>账号、角色与菜单权限由平台统一管理</span>
        </div>
        <footer class="login-footer">© {{ currentYear }} LAPUTTA · SHOT GRID 管理平台</footer>
      </div>
    </section>
  </main>
</template>

<script setup>
import { CircleCheckFilled, Histogram, Lock, Refresh, User } from '@element-plus/icons-vue'
import Cookies from 'js-cookie'

import { getCodeImg } from '@/api/login'
import useUserStore from '@/store/modules/user'
import { decrypt, encrypt } from '@/utils/jsencrypt'

const companyLogoUrl = `${import.meta.env.BASE_URL}company_logo.svg`
const currentYear = new Date().getFullYear()
const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const loginRef = ref()

const loginForm = ref({
  username: '',
  password: '',
  rememberMe: false,
  code: '',
  uuid: ''
})

const loginRules = {
  username: [{ required: true, trigger: 'blur', message: '请输入用户名称' }],
  password: [{ required: true, trigger: 'blur', message: '请输入密码' }],
  code: [{ required: true, trigger: 'change', message: '请输入验证码' }]
}

const codeUrl = ref('')
const loading = ref(false)
const captchaLoading = ref(false)
// 验证码开关
const captchaEnabled = ref(true)
// 注册开关
const register = ref(false)
const redirect = ref()

watch(
  route,
  (newRoute) => {
    redirect.value = newRoute.query && newRoute.query.redirect
  },
  { immediate: true }
)

async function handleLogin() {
  if (loading.value) return

  // 校验本身也是异步过程，先占用提交锁，避免双击或连续回车并发登录。
  loading.value = true
  try {
    const valid = await loginRef.value?.validate().catch(() => false)
    if (!valid) return

    if (loginForm.value.rememberMe) {
      Cookies.set('username', loginForm.value.username, { expires: 30 })
      Cookies.set('password', encrypt(loginForm.value.password), { expires: 30 })
      Cookies.set('rememberMe', 'true', { expires: 30 })
    } else {
      Cookies.remove('username')
      Cookies.remove('password')
      Cookies.remove('rememberMe')
    }

    await userStore.login(loginForm.value)
    const query = route.query
    const otherQueryParams = Object.keys(query).reduce((acc, key) => {
      if (key !== 'redirect') acc[key] = query[key]
      return acc
    }, {})
    await router.push({ path: redirect.value || '/', query: otherQueryParams })
  } catch {
    if (captchaEnabled.value) await getCode().catch(() => undefined)
  } finally {
    loading.value = false
  }
}

async function getCode() {
  if (captchaLoading.value) return

  captchaLoading.value = true
  try {
    const response = await getCodeImg()
    captchaEnabled.value = response.captchaEnabled === undefined ? true : response.captchaEnabled
    register.value = response.registerEnabled === undefined ? false : response.registerEnabled
    if (captchaEnabled.value) {
      codeUrl.value = `data:image/gif;base64,${response.img}`
      loginForm.value.uuid = response.uuid
    } else {
      codeUrl.value = ''
      loginForm.value.code = ''
      loginForm.value.uuid = ''
    }
  } finally {
    captchaLoading.value = false
  }
}

function getCookie() {
  const username = Cookies.get('username')
  const password = Cookies.get('password')
  const rememberMe = Cookies.get('rememberMe')

  loginForm.value.username = username || ''
  loginForm.value.rememberMe = rememberMe === 'true'

  if (!password) return
  try {
    loginForm.value.password = decrypt(password)
  } catch {
    Cookies.remove('password')
    Cookies.remove('rememberMe')
    loginForm.value.password = ''
    loginForm.value.rememberMe = false
  }
}

getCode().catch(() => undefined)
getCookie()
</script>

<style lang="scss" scoped>
.admin-login {
  --login-accent: #9a4a00;
  --login-accent-strong: #824000;
  --login-accent-on-dark: #f5ad55;
  --login-button-bg: #9a4a00;
  --login-button-hover-bg: #7c3a00;
  --login-button-active-bg: #632e00;
  --login-panel: #f3f5f8;
  --login-card: rgba(255, 255, 255, 0.94);
  --login-text: #17202d;
  --login-text-secondary: #627085;
  --login-border: #dce2ea;
  --login-fill: #f6f7f9;

  display: grid;
  min-height: 100vh;
  color: var(--login-text);
  background: var(--login-panel);
  grid-template-columns: minmax(0, 1.15fr) minmax(460px, 0.85fr);
}

.brand-scene {
  position: relative;
  display: flex;
  min-height: 100vh;
  padding: clamp(52px, 6vw, 96px);
  overflow: hidden;
  color: #f5f7fa;
  background:
    radial-gradient(circle at 78% 21%, rgba(234, 145, 36, 0.24), transparent 24%),
    radial-gradient(circle at 15% 83%, rgba(59, 75, 99, 0.28), transparent 28%),
    linear-gradient(138deg, #1c222c 0%, #0e1219 51%, #080a0e 100%);
  align-items: flex-end;
}

.brand-scene::before,
.brand-scene::after {
  position: absolute;
  content: '';
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 50%;
}

.brand-scene::before {
  top: 6%;
  right: -14%;
  width: min(52vw, 680px);
  aspect-ratio: 1;
}

.brand-scene::after {
  top: 25%;
  right: 8%;
  width: min(25vw, 330px);
  aspect-ratio: 1;
}

.brand-scene__frame {
  position: absolute;
  inset: 28px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.brand-scene__frame::before,
.brand-scene__frame::after {
  position: absolute;
  width: 58px;
  height: 58px;
  content: '';
  border-color: var(--login-accent-on-dark);
  border-style: solid;
}

.brand-scene__frame::before {
  top: -1px;
  left: -1px;
  border-width: 2px 0 0 2px;
}

.brand-scene__frame::after {
  right: -1px;
  bottom: -1px;
  border-width: 0 2px 2px 0;
}

.brand-scene__company-logo {
  position: absolute;
  top: clamp(58px, 6vw, 96px);
  left: clamp(58px, 6vw, 96px);
  z-index: 1;
  display: block;
  width: clamp(230px, 21vw, 340px);
  height: auto;
  opacity: 0.92;
}

.brand-scene__content {
  position: relative;
  z-index: 1;
  max-width: 760px;
}

.brand-scene__eyebrow {
  margin: 0 0 18px;
  color: #f5ad55;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.2em;
}

.brand-scene h1 {
  margin: 0;
  font-size: clamp(42px, 5vw, 70px);
  font-weight: 600;
  letter-spacing: -0.055em;
  line-height: 1.15;
}

.brand-scene__description {
  max-width: 660px;
  margin: 28px 0 38px;
  color: rgba(235, 239, 245, 0.7);
  font-size: 15px;
  line-height: 1.9;
}

.brand-scene__capabilities {
  display: flex;
  gap: 26px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.brand-scene__capabilities li {
  display: flex;
  gap: 9px;
  color: rgba(238, 242, 248, 0.72);
  font-size: 12px;
  letter-spacing: 0.08em;
  align-items: center;
}

.brand-scene__capabilities span {
  color: var(--login-accent-on-dark);
  font-size: 10px;
  font-weight: 700;
}

.brand-scene__caption {
  position: absolute;
  right: clamp(58px, 6vw, 96px);
  bottom: clamp(58px, 6vw, 96px);
  margin: 0;
  color: rgba(235, 239, 245, 0.34);
  font-size: 10px;
  letter-spacing: 0.14em;
  writing-mode: vertical-rl;
}

.login-panel {
  position: relative;
  display: grid;
  min-height: 100vh;
  padding: 48px clamp(36px, 5vw, 76px);
  overflow: hidden;
  background: var(--login-panel);
  border-left: 1px solid var(--login-border);
  grid-template-columns: minmax(0, 1fr);
  place-items: center;
}

.login-panel__glow {
  position: absolute;
  top: -170px;
  right: -120px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(233, 145, 36, 0.14), transparent 68%);
  pointer-events: none;
}

.login-card {
  position: relative;
  z-index: 1;
  width: min(100%, 430px);
  min-width: 0;
  padding: clamp(30px, 4vw, 46px);
  background: var(--login-card);
  border: 1px solid var(--login-border);
  border-radius: 22px;
  box-shadow: 0 24px 70px rgba(31, 41, 55, 0.12);
  backdrop-filter: blur(18px);
}

.mobile-company-logo {
  display: none;
  width: 164px;
  height: 36px;
  color: var(--login-text);
  background: currentColor;
  -webkit-mask: var(--company-logo-image) center / contain no-repeat;
  mask: var(--company-logo-image) center / contain no-repeat;
}

.product-brand {
  display: flex;
  gap: 12px;
  margin-bottom: clamp(40px, 7vh, 64px);
  align-items: center;
}

.product-brand__mark {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  background: #f4aa4b;
  border-radius: 12px;
  box-shadow: 0 10px 24px rgba(191, 101, 0, 0.2);
  place-items: center;
}

.product-brand__mark .el-icon {
  color: #17130e;
  font-size: 24px;
}

.product-brand__copy strong,
.product-brand__copy small {
  display: block;
}

.product-brand__copy strong {
  font-size: 15px;
  letter-spacing: 0.14em;
}

.product-brand__copy small {
  margin-top: 4px;
  color: var(--login-text-secondary);
  font-size: 10px;
}

.login-heading {
  margin-bottom: 30px;
}

.login-heading p {
  margin: 0 0 7px;
  color: var(--login-accent-strong);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.login-heading h2 {
  margin: 0 0 9px;
  color: var(--login-text);
  font-size: 30px;
  font-weight: 650;
  letter-spacing: -0.035em;
}

.login-heading span {
  color: var(--login-text-secondary);
  font-size: 13px;
}

.captcha-field {
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 10px;
  grid-template-columns: minmax(0, 1fr) 126px;
}

.captcha-field .el-input {
  min-width: 0;
}

.captcha-button {
  display: grid;
  height: 40px;
  padding: 0;
  overflow: hidden;
  color: var(--login-text-secondary);
  background: var(--login-fill);
  border-color: var(--login-border);
  place-items: center;
}

.captcha-button img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.login-options {
  display: flex;
  min-height: 32px;
  margin: -2px 0 18px;
  align-items: center;
  justify-content: space-between;
}

.login-options > span {
  color: var(--login-text-secondary);
  font-size: 11px;
}

.login-action {
  margin-bottom: 0;
}

.login-submit {
  width: 100%;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.register-entry {
  display: flex;
  gap: 6px;
  margin-top: 16px;
  color: var(--login-text-secondary);
  font-size: 12px;
  justify-content: center;
}

.register-entry__link {
  color: var(--login-accent-strong);
  font-weight: 600;
}

.login-notice {
  display: flex;
  gap: 7px;
  margin-top: 24px;
  color: var(--login-text-secondary);
  font-size: 11px;
  align-items: center;
  justify-content: center;
}

.login-notice .el-icon {
  color: #4da06b;
}

.login-footer {
  margin-top: 18px;
  color: var(--login-text-secondary);
  font-size: 10px;
  letter-spacing: 0.03em;
  text-align: center;
}

:deep(.el-form-item) {
  margin-bottom: 22px;
}

:deep(.el-form-item__label) {
  color: var(--login-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

:deep(.el-input__wrapper) {
  background: var(--login-fill);
  box-shadow: 0 0 0 1px var(--login-border) inset;
}

:deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--login-accent) 65%, var(--login-border)) inset;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--login-accent) inset;
}

:deep(.el-checkbox__label) {
  color: var(--login-text-secondary);
  font-size: 12px;
  font-weight: 500;
}

:deep(.el-button--primary) {
  --el-button-bg-color: var(--login-button-bg);
  --el-button-border-color: var(--login-button-bg);
  --el-button-hover-bg-color: var(--login-button-hover-bg);
  --el-button-hover-border-color: var(--login-button-hover-bg);
  --el-button-active-bg-color: var(--login-button-active-bg);
  --el-button-active-border-color: var(--login-button-active-bg);
}

:global(html.dark) .admin-login {
  --login-accent: #f0a84e;
  --login-accent-strong: #f6b15a;
  --login-button-bg: #b85d04;
  --login-button-hover-bg: #944900;
  --login-button-active-bg: #753700;
  --login-panel: #0b0e13;
  --login-card: rgba(18, 22, 29, 0.94);
  --login-text: #f0f3f7;
  --login-text-secondary: #8d9aae;
  --login-border: #29313d;
  --login-fill: #171c24;
}

@media (max-width: 1080px) {
  .admin-login {
    grid-template-columns: minmax(0, 0.95fr) minmax(440px, 1.05fr);
  }

  .brand-scene__capabilities { gap: 16px; }
}

@media (max-width: 900px) {
  .admin-login { display: block; }
  .brand-scene { display: none; }

  .login-panel {
    min-height: 100vh;
    padding: 40px 24px;
    border-left: 0;
  }

  .mobile-company-logo {
    display: block;
    margin-bottom: 28px;
  }

  .product-brand { margin-bottom: 42px; }
}

@media (max-width: 520px) {
  .login-panel { padding: 20px 14px; }

  .login-card {
    padding: 28px 22px;
    border-radius: 18px;
  }

  .mobile-company-logo {
    width: 138px;
    height: 30px;
  }

  .captcha-field {
    grid-template-columns: minmax(0, 1fr) 104px;
  }

  .login-options { display: block; }

  .login-options > span {
    display: block;
    margin-top: 2px;
  }
}

@media (max-height: 760px) and (min-width: 901px) {
  .brand-scene {
    padding-top: 42px;
    padding-bottom: 42px;
  }

  .brand-scene__company-logo { top: 54px; }
  .product-brand { margin-bottom: 32px; }

  .login-card {
    padding-top: 30px;
    padding-bottom: 30px;
  }
}
</style>
