import { afterEach } from 'vitest'

afterEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  document.cookie = 'Admin-Token=; Max-Age=0; path=/'
})
