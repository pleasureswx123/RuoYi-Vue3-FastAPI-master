import request from '@/utils/request'

export const login = (data) => request({ url: '/login', method: 'post', data })
export const getInfo = () => request({ url: '/getInfo', method: 'get' })
export const logout = () => request({ url: '/logout', method: 'post' })
