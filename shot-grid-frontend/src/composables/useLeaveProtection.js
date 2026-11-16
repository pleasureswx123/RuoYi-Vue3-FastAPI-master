import { onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'

// 路由切换使用业务确认；刷新/关页只能使用浏览器提供的离开提示。
export function useLeaveProtection(canLeave, hasDraft = () => false) {
  let pending
  const guard = () => {
    if (!pending) pending = Promise.resolve().then(canLeave).finally(() => { pending = null })
    return pending
  }
  onBeforeRouteLeave(guard)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || guard())
  const beforeUnload = event => {
    if (hasDraft()) { event.preventDefault(); event.returnValue = '' }
  }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  return guard
}
