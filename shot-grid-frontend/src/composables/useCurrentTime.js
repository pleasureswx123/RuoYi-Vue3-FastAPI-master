import { onBeforeUnmount, onMounted, ref } from 'vue'

// 时间提醒在页面停留期间也会更新，不请求后端或修改任务状态。
export function useCurrentTime() {
  const currentTime = ref(new Date())
  let timer
  const refresh = () => { currentTime.value = new Date() }
  onMounted(() => {
    timer = window.setInterval(refresh, 30000)
    document.addEventListener('visibilitychange', refresh)
  })
  onBeforeUnmount(() => {
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', refresh)
  })
  return currentTime
}
