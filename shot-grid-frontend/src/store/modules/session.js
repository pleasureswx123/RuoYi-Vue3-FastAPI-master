import { defineStore } from 'pinia'

import { getCaptcha, getCurrentUser, login, logout } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { getToken, removeToken, setToken } from '@/utils/auth'
import { ApiError } from '@/utils/apiError'
import { normalizeNavigation } from '@/router/routeRegistry'

function projectSafeUser(user) {
  if (!user || typeof user !== 'object') {
    return null
  }
  return {
    userId: user.userId ?? null,
    userName: user.userName || '',
    nickName: user.nickName || '',
    avatar: user.avatar || '',
    dept: user.dept
      ? { deptId: user.dept.deptId ?? null, deptName: user.dept.deptName || '' }
      : null
  }
}

function stringList(value) {
  return Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
}

function projectSafeError(error) {
  return {
    status: error?.status ?? null,
    httpStatus: error?.httpStatus ?? null,
    code: error?.code ?? null,
    errorKey: error?.errorKey ?? null,
    message: error?.message || '会话初始化失败'
  }
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    token: getToken() || '',
    user: null,
    roles: [],
    permissions: [],
    navigation: [],
    initialized: false,
    initializationPromise: null,
    status: getToken() ? 'idle' : 'anonymous',
    bootstrapError: null,
    passwordNotice: null,
    captcha: { enabled: true, image: '', uuid: '', loading: false }
  }),
  getters: {
    displayName: state => state.user?.userName || state.user?.nickName || '当前用户',
    allowedRouteKeys: state => new Set(state.navigation.map(item => item.routeKey))
  },
  actions: {
    clearLocalSession() {
      removeToken()
      this.token = ''
      this.user = null
      this.roles = []
      this.permissions = []
      this.navigation = []
      this.initialized = false
      this.initializationPromise = null
      this.status = 'anonymous'
      this.bootstrapError = null
      this.passwordNotice = null
    },
    async loadCaptcha() {
      this.captcha.loading = true
      try {
        const response = await getCaptcha()
        this.captcha = {
          enabled: response.captchaEnabled !== false,
          image: response.img ? `data:image/gif;base64,${response.img}` : '',
          uuid: response.uuid || '',
          loading: false
        }
        return this.captcha
      } finally {
        this.captcha.loading = false
      }
    },
    async signIn(credentials) {
      const response = await login({
        username: credentials.username.trim(),
        password: credentials.password,
        code: this.captcha.enabled ? credentials.code : undefined,
        uuid: this.captcha.enabled ? this.captcha.uuid : undefined
      })
      if (!response.token) {
        throw new Error('登录未完成，请稍后重试')
      }
      setToken(response.token)
      this.token = response.token
      this.initialized = false
      this.status = 'idle'
      return this.bootstrap()
    },
    bootstrap() {
      if (this.initialized) {
        return Promise.resolve(this)
      }
      if (this.initializationPromise) {
        return this.initializationPromise
      }
      if (!this.token && !getToken()) {
        this.clearLocalSession()
        return Promise.resolve(this)
      }
      this.token = this.token || getToken()
      this.initializationPromise = this.initializeSession().finally(() => {
        this.initializationPromise = null
      })
      return this.initializationPromise
    },
    async initializeSession() {
      this.bootstrapError = null
      try {
        this.status = 'loadingIdentity'
        const identity = await getCurrentUser()
        const safeUser = projectSafeUser(identity.user)
        if (!safeUser?.userId) {
          throw new ApiError('当前登录用户信息无效，请重新登录', {
            status: 401,
            code: 401,
            errorKey: 'SG_CURRENT_USER_INVALID'
          })
        }
        this.user = safeUser
        this.roles = stringList(identity.roles)
        this.permissions = stringList(identity.permissions)
        this.passwordNotice = identity.isPasswordExpired
          ? 'expired'
          : identity.isDefaultModifyPwd
            ? 'default'
            : null
        this.status = 'loadingNavigation'
        const navigationResponse = await getShotGridNavigation()
        this.navigation = normalizeNavigation(navigationResponse.data)
        this.initialized = true
        this.status = this.navigation.length > 0 ? 'ready' : 'forbidden'
        return this
      } catch (error) {
        this.bootstrapError = projectSafeError(error)
        this.status = error.status === 401 ? 'anonymous' : 'bootError'
        if (error.status === 401) {
          this.clearLocalSession()
        }
        throw error
      }
    },
    async signOut() {
      let serverError = null
      try {
        if (this.token || getToken()) {
          await logout()
        }
      } catch (error) {
        serverError = error
      } finally {
        this.clearLocalSession()
      }
      if (serverError) {
        throw serverError
      }
    }
  }
})
