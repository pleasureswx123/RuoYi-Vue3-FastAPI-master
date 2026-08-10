export const NAVIGATION_ROUTE_WHITELIST = Object.freeze({
  workbench: Object.freeze({ name: 'Workbench', path: '/workbench' }),
  projects: Object.freeze({ name: 'Projects', path: '/projects' }),
  shots: Object.freeze({ name: 'Shots', path: '/shots' }),
  assets: Object.freeze({ name: 'Assets', path: '/assets' }),
  reviews: Object.freeze({ name: 'Reviews', path: '/reviews' }),
  files: Object.freeze({ name: 'Files', path: '/files' })
})

const SAFE_ROUTE_KEY = /^[a-z][a-z0-9-]{0,49}$/

function warnUnknownRoute(routeKey) {
  // 只记录经净化的稳定键和固定事件名，不记录响应对象、用户身份或请求信息。
  const safeKey = typeof routeKey === 'string' && SAFE_ROUTE_KEY.test(routeKey) ? routeKey : '[invalid]'
  console.warn('[shot-grid:navigation] 已拒绝未知路由键', { routeKey: safeKey })
}

export function resolveNavigation(items, onUnknown = warnUnknownRoute) {
  if (!Array.isArray(items)) return { entries: [], rejected: [] }
  const entries = []
  const rejected = []
  const seen = new Set()
  for (const item of items) {
    const routeKey = item?.routeKey
    const target = NAVIGATION_ROUTE_WHITELIST[routeKey]
    if (!target) {
      rejected.push(routeKey)
      onUnknown(routeKey)
      continue
    }
    if (seen.has(routeKey)) continue
    seen.add(routeKey)
    entries.push({
      routeKey,
      title: typeof item.title === 'string' ? item.title : routeKey,
      icon: typeof item.icon === 'string' ? item.icon : null,
      orderNum: Number.isFinite(item.orderNum) ? item.orderNum : 0,
      ...target
    })
  }
  entries.sort((left, right) => left.orderNum - right.orderNum)
  return { entries, rejected }
}
