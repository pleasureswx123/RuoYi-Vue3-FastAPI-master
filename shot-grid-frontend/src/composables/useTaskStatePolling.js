import { onBeforeUnmount, ref, watch } from 'vue'

// 列表只在等待开工或目录准备时查询，页面负责暂停编辑和筛选中的上下文。
export function useTaskStatePolling({ getDelay, refresh }) {
  const pollingError = ref('')
  let timer = null
  let controller = null
  let generation = 0
  let attempts = 0
  let failures = 0

  function cancel() {
    generation += 1
    clearTimeout(timer)
    timer = null
    controller?.abort()
    controller = null
  }

  function schedule(delay, currentGeneration) {
    if (!delay || pollingError.value || currentGeneration !== generation) return
    timer = setTimeout(async () => {
      timer = null
      const requestController = new AbortController()
      controller = requestController
      const isCurrent = () => generation === currentGeneration && !requestController.signal.aborted
      attempts += 1
      try {
        await refresh(requestController)
        if (!isCurrent()) return
        failures = 0
      } catch (error) {
        if (!isCurrent()) return
        if (error?.code !== 'ERR_CANCELED') {
          failures += 1
          const status = Number(error?.status ?? error?.httpStatus ?? error?.response?.status)
          if ([401, 403, 404].includes(status) || failures >= 3) {
            pollingError.value = '状态自动刷新已暂停，当前显示上次结果，请点击刷新重试。'
          }
        }
      } finally {
        if (isCurrent()) {
          controller = null
          if (delay === 1500 && attempts >= 80 && !pollingError.value) {
            pollingError.value = '目录准备时间较长，当前显示上次结果，请点击刷新查看最新状态。'
          }
          schedule(delay, currentGeneration)
        }
      }
    }, delay)
  }

  watch(getDelay, delay => {
    cancel()
    attempts = 0
    failures = 0
    pollingError.value = ''
    schedule(delay, generation)
  }, { immediate: true, flush: 'sync' })

  onBeforeUnmount(cancel)
  return { pollingError }
}
