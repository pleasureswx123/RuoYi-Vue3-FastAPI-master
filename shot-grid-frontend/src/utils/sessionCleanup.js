import { clearProjectResources } from '@/utils/projectResources'

const PROJECT_SESSION_KEYS = ['shot-grid:current-project', 'shot-grid:project-context']
const MEDIA_SESSION_KEYS = ['shot-grid:media-temporary', 'shot-grid:review-draft']

export function clearClientSession() {
  clearProjectResources()
  if (typeof sessionStorage !== 'undefined') [...PROJECT_SESSION_KEYS, ...MEDIA_SESSION_KEYS].forEach((key) => sessionStorage.removeItem(key))
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('shot-grid:session-cleared'))
}
