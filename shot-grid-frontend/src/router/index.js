import { createRouter, createWebHistory } from 'vue-router'
import { pinia } from '@/store'
import { useUserStore } from '@/store/modules/user'
import { getToken } from '@/utils/auth'
import { stableRoutes } from './routes'
import { createNavigationGuard } from './guards'
import { useNavigationStore } from '@/store/modules/navigation'
import { clearProjectResources } from '@/utils/projectResources'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: stableRoutes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach(createNavigationGuard({
  getToken,
  userStore: useUserStore(pinia),
  navigationStore: useNavigationStore(pinia),
  clearProjectResources
}))

export default router
