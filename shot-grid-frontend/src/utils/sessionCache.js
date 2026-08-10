function getSessionStorage() {
  return typeof globalThis.sessionStorage === 'undefined' ? null : globalThis.sessionStorage
}

const session = {
  getJSON(key) {
    const value = getSessionStorage()?.getItem(key)
    if (!value) return null
    try {
      return JSON.parse(value)
    } catch {
      return null
    }
  },
  setJSON(key, value) {
    getSessionStorage()?.setItem(key, JSON.stringify(value))
  },
  remove(key) {
    getSessionStorage()?.removeItem(key)
  }
}

export default { session }
