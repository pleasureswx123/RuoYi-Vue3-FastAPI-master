import { computed, ref, watch } from 'vue'

// 表格渲染与自动适应使用同一组默认宽度。
export const assetColumnWidths = { identity: 210, actions: 320, status: 170, assignee: 100, plan: 175, thumbnail: 96, description: 220 }

export const assetOptionalColumns = [
  { key: 'thumbnail', label: '缩略图' },
  { key: 'description', label: '说明' },
  { key: 'plan', label: '计划时间' },
  { key: 'assignee', label: '制作人' },
  { key: 'status', label: '状态' }
]

// 与镜头表一致，展示偏好按账号保存在浏览器，不保存业务数据。
export function useAssetTablePresentation(userId, availableWidth = ref(0)) {
  const mode = ref('auto')
  const columns = ref([])
  const widths = ref({})
  const keys = assetOptionalColumns.map(column => column.key)
  const widthKeys = [...keys, 'identity', 'actions']
  const storageKey = computed(() => `shot-grid:asset-table:v1:${userId.value ?? 'guest'}`)
  watch(storageKey, key => {
    let saved = {}
    try { saved = JSON.parse(localStorage.getItem(key) || '{}') || {} } catch { /* 存储不可用时恢复默认。 */ }
    mode.value = ['auto', 'full', 'compact', 'custom'].includes(saved.mode) ? saved.mode : 'auto'
    columns.value = Array.isArray(saved.columns) ? saved.columns.filter(key => keys.includes(key)) : []
    widths.value = Object.fromEntries(Object.entries(saved.widths || {}).filter(([key, value]) => widthKeys.includes(key) && Number.isFinite(value) && value >= 80 && value <= 800))
  }, { immediate: true })
  watch([mode, columns, widths], () => {
    try { localStorage.setItem(storageKey.value, JSON.stringify({ mode: mode.value, columns: columns.value, widths: widths.value })) } catch { /* 不阻断列表使用。 */ }
  }, { deep: true, flush: 'sync' })
  const visibleColumns = computed(() => {
    if (mode.value === 'full') return keys
    if (mode.value === 'custom') return columns.value
    if (mode.value === 'compact') return ['assignee', 'status']
    // 尚未测量时保持完整布局；根据容器宽度优先保留负责人和状态。
    if (availableWidth.value <= 0) return keys
    const widthOf = key => widths.value[key] || assetColumnWidths[key]
    let remaining = availableWidth.value - 48 - widthOf('identity') - widthOf('actions') - widthOf('assignee') - widthOf('status')
    const visible = new Set(['assignee', 'status'])
    for (const key of ['plan', 'thumbnail', 'description']) {
      if (remaining >= widthOf(key)) {
        visible.add(key)
        remaining -= widthOf(key)
      }
    }
    return keys.filter(key => visible.has(key))
  })
  function setColumns(value) {
    columns.value = value.filter(key => keys.includes(key))
    mode.value = 'custom'
  }
  function saveWidth(width, _oldWidth, column) {
    if (widthKeys.includes(column.columnKey)) widths.value = { ...widths.value, [column.columnKey]: Math.min(800, Math.max(80, width)) }
  }
  function resetPresentation() {
    mode.value = 'auto'
    columns.value = []
    widths.value = {}
  }
  return { mode, visibleColumns, widths, setColumns, saveWidth, resetPresentation }
}
