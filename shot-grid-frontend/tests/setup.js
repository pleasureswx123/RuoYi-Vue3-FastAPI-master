import { afterEach } from 'vitest'
import { config } from '@vue/test-utils'
import { ElCheckbox, ElOption, ElSelect } from 'element-plus'

config.global.components = { ElCheckbox, ElOption, ElSelect }

afterEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  document.cookie = 'Admin-Token=; Max-Age=0; path=/'
})
