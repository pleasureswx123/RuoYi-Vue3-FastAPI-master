import { computed, onBeforeUnmount, watch } from 'vue'
import { useRealtimeStore } from '@/store/modules/realtime'

export function useVersionRealtime(versionId, refresh) {
  const realtime = useRealtimeStore()
  let unsubscribe = null
  let timer = null
  let fallback = null
  let disposed = false
  let refreshing = false
  let pending = false
  async function run() {
    timer = null
    if (disposed || !versionId.value || document.visibilityState === 'hidden') return
    if (refreshing) { pending = true; return }
    refreshing = true
    try { await refresh(versionId.value) } catch { /* 网络恢复后再次校验，保留现有页面和草稿。 */ }
    finally {
      refreshing = false
      if (pending) { pending = false; schedule() }
    }
  }
  function schedule() {
    if (!disposed && !timer) timer = setTimeout(run, 150)
  }
  watch(versionId, id => {
    unsubscribe?.()
    clearTimeout(timer)
    timer = null
    if (id) unsubscribe = realtime.subscribe('shot-grid.version', Number(id), schedule)
  }, { immediate: true })
  function visible() { if (document.visibilityState === 'visible') schedule() }
  document.addEventListener('visibilitychange', visible)
  // Pub/Sub 是失效提示而非业务账本；定期和重新可见时回源，补偿漏发。
  fallback = setInterval(schedule, 30000)
  onBeforeUnmount(() => {
    disposed = true
    unsubscribe?.()
    clearTimeout(timer)
    clearInterval(fallback)
    document.removeEventListener('visibilitychange', visible)
  })
  return { connectionStatus: computed(() => realtime.status) }
}
