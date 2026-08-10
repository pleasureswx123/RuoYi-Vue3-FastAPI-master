const ID_PATTERN = /^[1-9]\d{0,18}$/
const DETAIL_PARAM_BY_ROUTE = Object.freeze({
  ProjectOverview: 'projectId', ProjectScenes: 'projectId', ProjectShots: 'projectId',
  ProjectAssets: 'projectId', ProjectReviews: 'projectId', ProjectMembers: 'projectId',
  ShotDetail: 'shotId', AssetDetail: 'assetId', TaskDetail: 'taskId', VersionReview: 'versionId'
})

export const isValidRouteId = (value) => typeof value === 'string' && ID_PATTERN.test(value)

export function createNavigationGuard({ getToken, userStore, navigationStore, clearProjectResources }) {
  let activeProjectId = null
  return async (to) => {
    if (to.meta.public) return true
    if (!getToken()) return { name: 'Login', query: { redirect: to.fullPath } }
    try {
      if (!userStore.restored && !(await userStore.restore())) return { name: 'Login' }
      if (!navigationStore.loaded) await navigationStore.load()
      if (navigationStore.entries?.length === 0 && navigationStore.rejectedRouteKeys?.length > 0) return { name: 'FeatureUnavailable' }
    } catch (error) {
      return error?.status === 401 ? { name: 'SessionExpired' } : { name: 'ServiceError' }
    }

    const paramName = DETAIL_PARAM_BY_ROUTE[to.name]
    if (paramName && !isValidRouteId(to.params[paramName])) return { name: 'NotFound' }
    if (to.meta.navigationKey && !navigationStore.hasRoute(to.meta.navigationKey)) return { name: 'Forbidden' }

    const nextProjectId = typeof to.params.projectId === 'string' ? to.params.projectId : null
    if (activeProjectId && nextProjectId !== activeProjectId) clearProjectResources()
    activeProjectId = nextProjectId
    return true
  }
}
