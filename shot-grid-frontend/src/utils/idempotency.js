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
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  if (typeof globalThis.crypto?.getRandomValues !== 'function') {
    throw new Error('当前浏览器无法生成安全的请求标识，请更换浏览器后重试')
  }
  const values = new Uint32Array(4)
  globalThis.crypto.getRandomValues(values)
  return Array.from(values, item => item.toString(16).padStart(8, '0')).join('')
}

export function createIdempotencyState(scope) {
  const normalizedScope = String(scope || 'request').replace(/[^a-z0-9:_-]/gi, '-').slice(0, 32)
  let signature = null
  let key = null

  return {
    forPayload(payload) {
      const nextSignature = stableSerialize(payload)
      if (signature !== nextSignature || !key) {
        const nextKey = `${normalizedScope}:${randomPart()}`.slice(0, 100)
        signature = nextSignature
        key = nextKey
      }
      return key
    },
    reset() {
      signature = null
      key = null
    }
  }
}
