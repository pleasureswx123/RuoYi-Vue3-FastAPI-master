import Cookies from 'js-cookie'

const TOKEN_KEY = 'Admin-Token'

export const getToken = () => Cookies.get(TOKEN_KEY)
export const setToken = (token) => Cookies.set(TOKEN_KEY, token, { path: '/', sameSite: 'Lax' })
export const removeToken = () => Cookies.remove(TOKEN_KEY, { path: '/' })
