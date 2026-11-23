import { createStore, get, update } from 'idb-keyval'
import nacl from 'tweetnacl'

export const rememberedLoginKey = 'shot-grid.remembered-login.v1'
export const rememberPreferenceKey = 'shot-grid.remember-login-choice.v1'

export function shouldRememberLogin() {
  const choice = localStorage.getItem(rememberPreferenceKey)
  if (choice !== null) return choice === 'true'
  // 旧版只在用户选择记住后保存凭据。
  return window.__SHOTGRID_DESKTOP__ === true || localStorage.getItem(rememberedLoginKey) !== null
}

const deviceKeyStore = createStore('shot-grid-login-device', 'keys')
const deviceKeyName = 'secretbox-v1'

export function forgetLogin() {
  localStorage.removeItem(rememberedLoginKey)
}

export async function readRememberedLogin() {
  const saved = localStorage.getItem(rememberedLoginKey)
  if (!saved) return null
  const key = await get(deviceKeyName, deviceKeyStore)
  if (localStorage.getItem(rememberedLoginKey) !== saved) return null
  try {
    const { nonce, box } = JSON.parse(saved)
    const bytes = nacl.secretbox.open(Uint8Array.from(box), Uint8Array.from(nonce), Uint8Array.from(key))
    if (!bytes) throw new Error()
    const { username, password } = JSON.parse(new TextDecoder().decode(bytes))
    if (typeof username !== 'string' || !username || typeof password !== 'string' || !password) throw new Error()
    return { username, password }
  } catch {
    forgetLogin()
    return null
  }
}

export async function rememberLogin(username, password, previousRecord) {
  // 内网 HTTP 也支持 getRandomValues。设备密钥与凭据密文分开保存。
  let key
  await update(deviceKeyName, existing => {
    key = existing ?? Array.from(crypto.getRandomValues(new Uint8Array(nacl.secretbox.keyLength)))
    return key
  }, deviceKeyStore)
  // 其他窗口在登录期间清除了凭据或切换了账号时，以该窗口的新选择为准。
  if (!shouldRememberLogin() || localStorage.getItem(rememberedLoginKey) !== previousRecord) return
  const nonce = crypto.getRandomValues(new Uint8Array(nacl.secretbox.nonceLength))
  const bytes = new TextEncoder().encode(JSON.stringify({ username, password }))
  const box = nacl.secretbox(Uint8Array.from(bytes), nonce, Uint8Array.from(key))
  localStorage.setItem(rememberedLoginKey, JSON.stringify({ nonce: Array.from(nonce), box: Array.from(box) }))
}
