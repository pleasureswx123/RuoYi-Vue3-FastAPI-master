const objectUrls = new Set()
const mediaControllers = new Set()

export function trackObjectUrl(url) {
  if (typeof url === 'string' && url.startsWith('blob:')) objectUrls.add(url)
  return url
}

export function trackMediaRequest(controller) {
  if (controller?.abort) mediaControllers.add(controller)
  return () => mediaControllers.delete(controller)
}

export function clearProjectResources() {
  for (const controller of mediaControllers) controller.abort()
  mediaControllers.clear()
  if (typeof URL !== 'undefined') for (const url of objectUrls) URL.revokeObjectURL(url)
  objectUrls.clear()
  if (typeof sessionStorage !== 'undefined') {
    for (const key of ['shot-grid:project-list', 'shot-grid:project-filters', 'shot-grid:review-draft', 'shot-grid:media-temporary']) sessionStorage.removeItem(key)
  }
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('shot-grid:project-cleared'))
}
