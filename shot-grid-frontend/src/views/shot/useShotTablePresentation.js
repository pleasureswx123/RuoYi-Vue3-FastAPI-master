import { computed, ref, watch } from 'vue'

export const shotDetailColumns = [
  { key: 'parameters', label: '镜头参数', width: 160 },
  { key: 'dialogue', label: '台词 / 对白', width: 180 },
  { key: 'soundEffect', label: '音效', width: 180 },
  { key: 'colorReference', label: '色调参考', width: 200 },
  { key: 'remark', label: '备注', width: 200 },
  { key: 'references', label: '参考内容', width: 240 }
]

// 只记忆当前账号的展示偏好，不保存业务数据，也不改变查询与权限。
export function useShotTablePresentation(userId, availableWidth) {
  const mode = ref('auto')
  const customColumns = ref([])
  const widths = ref({})
  const storageKey = computed(() => `shot-grid:shot-table:v1:${userId.value ?? 'guest'}`)
  const columnKeys = new Set(['identity', 'description', 'plan', 'assignee', 'status', 'actions', ...shotDetailColumns.map(item => item.key)])

  watch(storageKey, key => {
    let saved = {}
    try { saved = JSON.parse(localStorage.getItem(key) || '{}') || {} } catch { /* 存储不可用时沿用默认展示。 */ }
    mode.value = ['auto', 'compact', 'full', 'custom'].includes(saved.mode) ? saved.mode : 'auto'
    customColumns.value = Array.isArray(saved.columns) ? saved.columns.filter(key => shotDetailColumns.some(item => item.key === key)) : []
    widths.value = Object.fromEntries(Object.entries(saved.widths || {}).filter(([key, value]) => columnKeys.has(key) && Number.isFinite(value) && value >= 80 && value <= 800))
  }, { immediate: true })

  watch([mode, customColumns, widths], () => {
    try {
      localStorage.setItem(storageKey.value, JSON.stringify({ mode: mode.value, columns: customColumns.value, widths: widths.value }))
    } catch { /* 不让浏览器存储限制影响表格操作。 */ }
  }, { deep: true })

  const visibleColumns = computed(() => {
    if (mode.value === 'full') return shotDetailColumns.map(item => item.key)
    if (mode.value === 'custom') return customColumns.value
    if (mode.value === 'compact') return []
    return availableWidth.value >= 1700 ? ['parameters'] : []
  })

  function setColumns(columns) {
    customColumns.value = columns.filter(key => shotDetailColumns.some(item => item.key === key))
    mode.value = 'custom'
  }
  function saveWidth(width, _oldWidth, column) {
    if (columnKeys.has(column.columnKey)) widths.value = { ...widths.value, [column.columnKey]: Math.min(800, Math.max(80, width)) }
  }
  function resetPresentation() {
    mode.value = 'auto'
    customColumns.value = []
    widths.value = {}
  }
  return { mode, widths, visibleColumns, setColumns, saveWidth, resetPresentation }
}
