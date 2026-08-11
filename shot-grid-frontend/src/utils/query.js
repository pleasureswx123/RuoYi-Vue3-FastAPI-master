export function toQueryString(params = {}) {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return
    }
    if (Array.isArray(value)) {
      value.forEach(item => {
        if (item !== null && item !== undefined && item !== '') {
          searchParams.append(key, String(item))
        }
      })
      return
    }
    if (typeof value === 'object') {
      Object.entries(value).forEach(([childKey, childValue]) => {
        if (childValue !== null && childValue !== undefined && childValue !== '') {
          searchParams.append(`${key}[${childKey}]`, String(childValue))
        }
      })
      return
    }
    searchParams.append(key, String(value))
  })

  return searchParams.toString()
}
