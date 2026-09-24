import { onBeforeUnmount, watch } from 'vue'
import { useRealtimeStore } from '@/store/modules/realtime'

// 列表仅订阅当前页版本，复用应用级连接并合并同一批更新。
export function useVersionCollectionRealtime(versionIds, refresh) {
  const realtime = useRealtimeStore()
  const subscriptions = new Map()
  let timer
  let running = false
  let pending = false
  let disposed = false
  function schedule() {
    if (!disposed && !timer) timer = setTimeout(run, 150)
  }
  async function run() {
    timer = null
    if (disposed || !subscriptions.size || document.visibilityState === 'hidden') return
    if (running) { pending = true; return }
    running = true
    try { await refresh() } catch { /* 保留列表，下一次事件或补查时重试。 */ }
    finally {
      running = false
      if (pending) { pending = false; schedule() }
    }
  }
  watch(versionIds, ids => {
    const next = new Set(ids.map(Number).filter(id => Number.isSafeInteger(id) && id > 0))
    for (const [id, stop] of subscriptions) {
      if (!next.has(id)) { stop(); subscriptions.delete(id) }
    }
    for (const id of next) {
      if (!subscriptions.has(id)) subscriptions.set(id, realtime.subscribe('shot-grid.version', id, schedule))
    }
  }, { immediate: true })
  const fallback = setInterval(schedule, 30000)
  function onVisible() { if (document.visibilityState === 'visible') schedule() }
  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    disposed = true
    clearTimeout(timer)
    clearInterval(fallback)
    for (const stop of subscriptions.values()) stop()
    document.removeEventListener('visibilitychange', onVisible)
  })
}
