const ROUTE_REGISTRY = Object.freeze({
  workbench: Object.freeze({ routeKey: 'workbench', path: '/workbench', routeName: 'workbench', title: '工作台', icon: 'dashboard' }),
  projects: Object.freeze({ routeKey: 'projects', path: '/projects', routeName: 'projects', title: '项目', icon: 'project' }),
  shots: Object.freeze({ routeKey: 'shots', path: '/shots', routeName: 'shots', title: '镜头管理', icon: 'video-camera' }),
  assets: Object.freeze({ routeKey: 'assets', path: '/assets', routeName: 'assets', title: '资产库管理', icon: 'picture' }),
  reviews: Object.freeze({ routeKey: 'reviews', path: '/reviews', routeName: 'reviews', title: '版本审核', icon: 'eye-open' }),
  files: Object.freeze({ routeKey: 'files', path: '/files', routeName: 'files', title: '文件与 NAS', icon: 'folder-opened' })
})

export const SHOT_GRID_ROUTE_KEYS = Object.freeze(Object.keys(ROUTE_REGISTRY))

function sanitizeLabel(value, fallback) {
  const label = typeof value === 'string' ? value.trim() : ''
  return label && label.length <= 40 ? label : fallback
}

function sanitizeIcon(value, fallback) {
  return typeof value === 'string' && /^[a-z0-9-]{1,40}$/i.test(value) ? value : fallback
}

export function normalizeNavigation(items) {
  if (!Array.isArray(items)) {
    return []
  }
  const seen = new Set()
  return items
    .flatMap(item => {
      const routeKey = typeof item?.routeKey === 'string' ? item.routeKey.trim() : ''
      if (!Object.hasOwn(ROUTE_REGISTRY, routeKey)) {
        return []
      }
      const localRoute = ROUTE_REGISTRY[routeKey]
      if (!localRoute || seen.has(routeKey) || item.path !== localRoute.path) {
        return []
      }
      seen.add(routeKey)
      const orderNum = Number(item.orderNum)
      return [
        {
          routeKey,
          routeName: localRoute.routeName,
          path: localRoute.path,
          title: sanitizeLabel(item.title, localRoute.title),
          icon: sanitizeIcon(item.icon, localRoute.icon),
          orderNum: Number.isInteger(orderNum) && orderNum >= 0 ? orderNum : SHOT_GRID_ROUTE_KEYS.indexOf(routeKey) + 1
        }
      ]
    })
    .sort((left, right) => left.orderNum - right.orderNum || left.routeKey.localeCompare(right.routeKey))
}

export function getRouteDefinition(routeKey) {
  return Object.hasOwn(ROUTE_REGISTRY, routeKey) ? ROUTE_REGISTRY[routeKey] : null
}

export function getRouteKeyByPath(path) {
  return SHOT_GRID_ROUTE_KEYS.find(routeKey => ROUTE_REGISTRY[routeKey].path === path) || null
}

export function getFirstAuthorizedPath(navigation) {
  return Array.isArray(navigation) && navigation.length > 0 ? navigation[0].path : '/forbidden'
}

export function sanitizeInternalRedirect(value, fallback = '/') {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return fallback
  }
  try {
    const parsed = new URL(value, window.location.origin)
    return parsed.origin === window.location.origin ? `${parsed.pathname}${parsed.search}${parsed.hash}` : fallback
  } catch {
    return fallback
  }
}
