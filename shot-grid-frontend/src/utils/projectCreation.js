export function uniqueUserIds(values) {
  return [...new Set((values || []).map(Number).filter(Number.isInteger).filter((id) => id > 0))]
}

export function hasDirector(values) {
  return uniqueUserIds(values).length > 0
}

export function createLatestPreview(onValue, onError) {
  let sequence = 0
  let controller
  return {
    async run(loader) {
      const current = ++sequence
      controller?.abort()
      controller = new AbortController()
      try {
        const value = await loader(controller.signal)
        if (current === sequence) onValue(value)
      } catch (error) {
        if (current === sequence && error?.code !== 'ERR_CANCELED' && error?.name !== 'AbortError') onError(error)
      }
    },
    cancel() { sequence += 1; controller?.abort() }
  }
}
