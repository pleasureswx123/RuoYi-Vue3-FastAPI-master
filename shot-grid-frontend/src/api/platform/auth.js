import request from '@/utils/request'

export function login(credentials) {
  return request({
    url: '/login',
    method: 'post',
    silentError: true,
    headers: {
      isToken: false,
      repeatSubmit: false,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    data: {
      username: credentials.username,
      password: credentials.password,
      code: credentials.code,
      uuid: credentials.uuid
    }
  })
}

export function getCurrentUser() {
  return request({ url: '/getInfo', method: 'get', silentError: true })
}

export function logout() {
  return request({ url: '/logout', method: 'post', headers: { repeatSubmit: false } })
}

export function getCaptcha() {
  return request({
    url: '/captchaImage',
    method: 'get',
    timeout: 20000,
    silentError: true,
    headers: { isToken: false }
  })
}
