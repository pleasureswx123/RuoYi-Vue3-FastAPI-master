function stableSerialize(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(',')}]`
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map(key => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
      .join(',')}}`
  }
  return JSON.stringify(value)
}

function randomPart() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID()
  }
  const values = new Uint32Array(4)
  globalThis.crypto?.getRandomValues?.(values)
  return Array.from(values, item => item.toString(16).padStart(8, '0')).join('') || `${Date.now()}`
}

export function createIdempotencyState(scope) {
  const normalizedScope = String(scope || 'request').replace(/[^a-z0-9:_-]/gi, '-').slice(0, 32)
  let signature = null
  let key = null

  return {
    forPayload(payload) {
      const nextSignature = stableSerialize(payload)
      if (signature !== nextSignature || !key) {
        signature = nextSignature
        key = `${normalizedScope}:${randomPart()}`.slice(0, 100)
      }
      return key
    },
    reset() {
      signature = null
      key = null
    }
  }
}
