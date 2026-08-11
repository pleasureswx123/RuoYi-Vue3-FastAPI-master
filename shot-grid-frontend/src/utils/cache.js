function createStorageCache(storage) {
  return {
    set(key, value) {
      if (key != null && value != null) {
        storage.setItem(key, String(value))
      }
    },
    get(key) {
      return key == null ? null : storage.getItem(key)
    },
    setJSON(key, value) {
      if (value != null) {
        storage.setItem(key, JSON.stringify(value))
      }
    },
    getJSON(key) {
      const value = key == null ? null : storage.getItem(key)
      if (value == null) {
        return null
      }
      try {
        return JSON.parse(value)
      } catch {
        storage.removeItem(key)
        return null
      }
    },
    remove(key) {
      if (key != null) {
        storage.removeItem(key)
      }
    },
    clear() {
      storage.clear()
    }
  }
}

export const sessionCache = createStorageCache(sessionStorage)
export const localCache = createStorageCache(localStorage)

export default {
  session: sessionCache,
  local: localCache
}
