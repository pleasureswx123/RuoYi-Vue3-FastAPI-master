import { createRouter, createWebHistory } from 'vue-router'
import { pinia } from '@/store'
import { useUserStore } from '@/store/modules/user'
import { getToken } from '@/utils/auth'
import { stableRoutes } from './routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: stableRoutes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (!getToken()) return { name: 'Login', query: { redirect: to.fullPath } }
  try {
    const restored = await useUserStore(pinia).restore()
    return restored ? true : { name: 'Login' }
  } catch {
    return { name: 'SessionExpired' }
  }
})

export default router
