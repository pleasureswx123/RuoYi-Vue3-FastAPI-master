/** 创建只接受最新响应的请求门。新请求会主动取消上一请求。 */
export function createLatestRequest() {
  let sequence = 0
  let controller
  return {
    async run(executor) {
      controller?.abort()
      controller = new AbortController()
      const current = ++sequence
      try {
        const value = await executor(controller.signal)
        return current === sequence ? { accepted: true, value } : { accepted: false }
      } catch (error) {
        if (controller.signal.aborted || current !== sequence || error?.code === 'ERR_CANCELED') return { accepted: false }
        throw error
      }
    },
    cancel() { sequence += 1; controller?.abort() }
  }
}

export function debounce(fn, delay = 300) {
  let timer
  const wrapped = (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay) }
  wrapped.cancel = () => clearTimeout(timer)
  return wrapped
}
