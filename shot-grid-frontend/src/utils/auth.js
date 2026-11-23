import Cookies from 'js-cookie'

const TOKEN_KEY = 'Admin-Token'

export function getToken() {
  return Cookies.get(TOKEN_KEY)
}

// 到期时间只控制本机 Cookie 的保存期限，身份和会话有效性仍由服务端校验。
function tokenExpiration(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const { exp } = JSON.parse(atob(payload))
    if (Number.isSafeInteger(exp) && exp > 0) {
      const expires = new Date(exp * 1000)
      if (Number.isFinite(expires.getTime())) return expires
    }
  } catch {
    // 缺少可用期限时沿用会话 Cookie。
  }
}

export function setToken(token, remember = false) {
  return Cookies.set(TOKEN_KEY, token, {
    expires: remember && window.__SHOTGRID_DESKTOP__ === true ? tokenExpiration(token) : undefined,
    path: '/',
    sameSite: 'Lax',
    secure: window.location.protocol === 'https:'
  })
}

export function removeToken() {
  return Cookies.remove(TOKEN_KEY, { path: '/' })
}
