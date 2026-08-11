import Cookies from 'js-cookie'

const TOKEN_KEY = 'Admin-Token'

export function getToken() {
  return Cookies.get(TOKEN_KEY)
}

export function setToken(token) {
  return Cookies.set(TOKEN_KEY, token, {
    path: '/',
    sameSite: 'Lax',
    secure: window.location.protocol === 'https:'
  })
}

export function removeToken() {
  return Cookies.remove(TOKEN_KEY, { path: '/' })
}
