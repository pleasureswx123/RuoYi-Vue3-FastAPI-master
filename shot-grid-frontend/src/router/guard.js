import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

import { useSessionStore } from '@/store/modules/session'
import { getToken } from '@/utils/auth'
import { setSessionExpiredHandler } from '@/utils/request'
import { getFirstAuthorizedPath, sanitizeInternalRedirect } from '@/router/routeRegistry'

NProgress.configure({ showSpinner: false })

function loginLocation(to) {
  const redirect = sanitizeInternalRedirect(to.fullPath, '/')
  return { name: 'login', query: redirect === '/login' ? {} : { redirect } }
}

export function installRouterGuard(router, pinia) {
  const session = useSessionStore(pinia)
  const landingPath = () => session.isCreatorWorkspace && session.allowedRouteKeys.has('workbench')
    ? '/workbench' : getFirstAuthorizedPath(session.navigation)

  setSessionExpiredHandler(() => {
    const current = router.currentRoute.value
    const target = loginLocation(current)
    session.clearLocalSession()
    if (current.name !== 'login') {
      queueMicrotask(() => {
        router.replace(target).catch(() => undefined)
      })
    }
  })

  router.beforeEach(async to => {
    NProgress.start()
    const token = getToken()

    if (!token) {
      if (to.meta.public) {
        return true
      }
      session.clearLocalSession()
      return loginLocation(to)
    }

    if (to.name === 'login') {
      try {
        await session.bootstrap()
        return sanitizeInternalRedirect(to.query.redirect, landingPath())
      } catch (error) {
        if (error.status === 401) {
          return true
        }
        if (error.status === 403) {
          return { name: 'forbidden' }
        }
        return { name: 'service-unavailable', query: { retry: '/' } }
      }
    }

    if (!to.meta.public) {
      try {
        await session.bootstrap()
      } catch (error) {
        if (error.status === 401) {
          return loginLocation(to)
        }
        if (error.status === 403) {
          return { name: 'forbidden' }
        }
        return { name: 'service-unavailable', query: { retry: sanitizeInternalRedirect(to.fullPath, '/') } }
      }
    }

    if (to.name === 'root') {
      return landingPath()
    }
    if (to.meta.routeKey && !session.allowedRouteKeys.has(to.meta.routeKey)) {
      return { name: 'forbidden' }
    }
    if (to.meta.routeKey) {
      const projectId = to.params.projectId || to.query.projectId
      if (['shots', 'assets', 'workbench', 'reviews', 'files'].includes(to.name) && !projectId && !session.activeProjectId && !(to.name === 'workbench' && session.isCreatorWorkspace)) {
        return session.allowedRouteKeys.has('projects') ? { name: 'projects' } : { name: 'forbidden' }
      }
    }
    return true
  })

  // 导航真正成功后才切项目，取消离开时保留旧项目及草稿上下文。
  router.afterEach((to, _from, failure) => {
    if (!failure && to.meta.routeKey) {
      const projectId = to.params.projectId || to.query.projectId
      if (projectId) session.selectProject(projectId)
      if (to.name === 'projects') session.selectProject('')
    }
    const applicationTitle = import.meta.env.VITE_APP_TITLE || 'Shot Grid'
    document.title = to.meta.title ? `${to.meta.title} · ${applicationTitle}` : applicationTitle
    NProgress.done()
  })

  router.onError(() => NProgress.done())
}
