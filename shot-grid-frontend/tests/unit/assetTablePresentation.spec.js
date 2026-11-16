import { effectScope, nextTick, ref } from 'vue'
import { expect, it } from 'vitest'
import { useAssetTablePresentation } from '@/views/asset/useAssetTablePresentation'

it('按账号恢复列与宽度，切换账号不串用偏好，恢复默认清空宽度', async () => {
  localStorage.clear()
  const scope = effectScope()
  const user = ref(101)
  const settings = scope.run(() => useAssetTablePresentation(user))
  try {
    settings.setColumns(['status', 'unknown'])
    settings.saveWidth(240, 100, { columnKey: 'status' })
    expect(settings.visibleColumns.value).toEqual(['status'])
    expect(JSON.parse(localStorage.getItem('shot-grid:asset-table:v1:101')).widths.status).toBe(240)
    user.value = 102
    await nextTick()
    expect(settings.visibleColumns.value).toHaveLength(5)
    expect(settings.widths.value).toEqual({})
    user.value = 101
    await nextTick()
    expect(settings.visibleColumns.value).toEqual(['status'])
    expect(settings.widths.value.status).toBe(240)
    settings.resetPresentation()
    expect(settings.visibleColumns.value).toHaveLength(5)
    expect(settings.widths.value).toEqual({})
  } finally { scope.stop(); localStorage.clear() }
})

it('自动模式随容器宽度调整列，手动模式保持不变，恢复自动重新适应', () => {
  localStorage.clear()
  const scope = effectScope()
  const width = ref(1700)
  const settings = scope.run(() => useAssetTablePresentation(ref(103), width))
  try {
    expect(settings.mode.value).toBe('auto')
    expect(settings.visibleColumns.value).toHaveLength(5)
    width.value = 900
    expect(settings.visibleColumns.value).toEqual(['assignee', 'status'])
    width.value = 1050
    expect(settings.visibleColumns.value).toEqual(['plan', 'assignee', 'status'])
    width.value = 1395
    expect(settings.visibleColumns.value).toHaveLength(5)
    settings.mode.value = 'full'
    width.value = 900
    expect(settings.visibleColumns.value).toHaveLength(5)
    settings.setColumns(['thumbnail'])
    width.value = 1900
    expect(settings.visibleColumns.value).toEqual(['thumbnail'])
    settings.resetPresentation()
    expect(settings.mode.value).toBe('auto')
    expect(settings.visibleColumns.value).toHaveLength(5)
  } finally { scope.stop(); localStorage.clear() }
})

it('列顺序按账号记忆，隐藏列恢复位置，非法顺序不破坏布局', async () => {
  localStorage.clear()
  const scope = effectScope()
  const user = ref(201)
  const settings = scope.run(() => useAssetTablePresentation(user))
  try {
    settings.setOrder(['status', 'thumbnail', 'description', 'plan', 'assignee'])
    expect(settings.visibleColumns.value[0]).toBe('status')
    settings.setColumns(['status', 'assignee'])
    settings.setOrder(['assignee', 'status'])
    expect(settings.visibleColumns.value).toEqual(['assignee', 'status'])
    settings.setOrder(['unknown'])
    expect(settings.visibleColumns.value).toEqual(['assignee', 'status'])
    settings.mode.value = 'full'
    expect(settings.visibleColumns.value).toEqual(['assignee', 'thumbnail', 'description', 'plan', 'status'])
    user.value = 202; await nextTick()
    expect(settings.visibleColumns.value[0]).toBe('thumbnail')
    user.value = 201; await nextTick()
    expect(settings.visibleColumns.value[0]).toBe('assignee')
    settings.resetPresentation()
    expect(settings.visibleColumns.value[0]).toBe('thumbnail')
  } finally { scope.stop(); localStorage.clear() }
})
