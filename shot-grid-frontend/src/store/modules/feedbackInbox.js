import { ref } from 'vue'
import { defineStore } from 'pinia'
import request from '@/utils/request'
import { useRealtimeStore } from './realtime'

export const useFeedbackInbox = defineStore('feedbackInbox', () => {
  const count = ref(0)
  const latestId = ref(null)
  const revision = ref(0)
  let sequence = 0

  async function refresh() {
    const token = ++sequence
    const { data } = await request.get('/shot-grid/my-messages/unread', { silentError: true })
    if (token !== sequence) return
    if (count.value !== data.count || latestId.value !== data.latestId) revision.value++
    count.value = data.count
    latestId.value = data.latestId
  }

  function listen(userId) {
    const sync = () => refresh().catch(() => {})
    const stop = useRealtimeStore().subscribe('shot-grid.inbox', userId, () => {
      revision.value++
      sync()
    })
    sync()
    const timer = setInterval(sync, 30000)
    window.addEventListener('online', sync)
    return () => {
      stop()
      clearInterval(timer)
      window.removeEventListener('online', sync)
      sequence++
      count.value = 0
      latestId.value = null
    }
  }

  async function markRead(id) {
    await request.put(`/shot-grid/my-messages/${id}/read`)
    await refresh()
  }
  return { count, latestId, revision, refresh, listen, markRead }
})
