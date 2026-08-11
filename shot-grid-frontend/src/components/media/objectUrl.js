export function createObjectUrlOwner(urlApi = URL) {
  let current = ''
  return {
    replace(blob) {
      if (current) urlApi.revokeObjectURL(current)
      current = urlApi.createObjectURL(blob)
      return current
    },
    release() {
      if (current) urlApi.revokeObjectURL(current)
      current = ''
    }
  }
}
