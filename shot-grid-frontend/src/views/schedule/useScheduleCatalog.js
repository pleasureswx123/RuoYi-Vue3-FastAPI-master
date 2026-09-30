import { onBeforeUnmount, ref, watch } from 'vue'
import { getProjectSchedule } from '@/api/shot-grid/schedules'

// 使用同一鉴权接口独立加载窗口选项，不随任务筛选缩减。
export function useScheduleCatalog(scope) {
  const rows = ref([])
  const loading = ref(false)
  const error = ref('')
  let controller
  let generation = 0
  async function refresh() {
    controller?.abort()
    const current = ++generation
    const query = scope()
    rows.value = []
    error.value = ''
    loading.value = false
    if (!query.projectId) return
    controller = new AbortController()
    const signal = controller.signal
    loading.value = true
    try {
      const resultRows = []
      let pageNum = 1
      let result
      do {
        const { projectId, ...params } = query
        const response = await getProjectSchedule(projectId, { ...params, pageNum, pageSize: 500 }, { signal })
        if (current !== generation) return
        result = response?.data ?? response ?? {}
        resultRows.push(...(result.rows || []))
        pageNum += 1
      } while (result.hasNext)
      rows.value = resultRows
    } catch {
      if (current === generation && !signal.aborted) error.value = '窗口统计和筛选选项加载失败'
    } finally {
      if (current === generation) loading.value = false
    }
  }
  watch(scope, refresh, { immediate: true, deep: true })
  onBeforeUnmount(() => { generation += 1; controller?.abort() })
  return { rows, loading, error, refresh }
}
