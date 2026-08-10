import request from '@/utils/request'

export function login(username, password, code, uuid) {
  const data = typeof username === 'object' ? username : { username, password, code, uuid }
  return request({ url: '/login', method: 'post', data, headers: { isToken: false, repeatSubmit: false, 'Content-Type': 'application/x-www-form-urlencoded' } })
}

export const getInfo = () => request({ url: '/getInfo', method: 'get' })
export const getCaptcha = () => request({ url: '/captchaImage', method: 'get', timeout: 20000, headers: { isToken: false } })
export const getCodeImg = getCaptcha
export const logout = () => request({ url: '/logout', method: 'post', headers: { repeatSubmit: false } })
