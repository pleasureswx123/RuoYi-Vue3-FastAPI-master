import { inject } from 'vue'
import { useRouter } from 'vue-router'

export const detailNavigationKey = Symbol('detailNavigation')

export function detailResource(target) {
  const named = {
    'version-detail': ['version', 'versionId'],
    'review-detail': ['review', 'reviewListId'],
    'task-detail': ['task', 'taskId']
  }
  const match = typeof target === 'string' ? target.match(/^\/(versions|reviews|tasks)\/(\d+)(?:#.*)?$/) : null
  const entry = named[target?.name]
  const type = match ? { versions: 'version', reviews: 'review', tasks: 'task' }[match[1]] : entry?.[0]
  const id = Number(match ? match[2] : target?.params?.[entry?.[1]])
  return type && Number.isSafeInteger(id) && id > 0 ? { type, id } : null
}

export function useDetailNavigation() {
  const router = useRouter()
  const openDetail = inject(detailNavigationKey, null)
  return target => openDetail?.(target) || router.push(target)
}
