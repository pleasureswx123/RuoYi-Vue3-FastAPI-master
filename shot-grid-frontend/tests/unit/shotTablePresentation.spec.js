import { effectScope, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { useShotTablePresentation } from '@/views/shot/useShotTablePresentation'

describe('镜头表格展示偏好', () => {
  beforeEach(() => localStorage.clear())

  it('自动布局跟随容器宽度，自定义选择不被窗口变化覆盖，重置恢复自动', async () => {
    const scope = effectScope()
    const width = ref(1200)
    const settings = scope.run(() => useShotTablePresentation(ref(1), width))
    expect(settings.visibleColumns.value).toEqual([])
    width.value = 1900
    expect(settings.visibleColumns.value).toEqual(['parameters'])
    settings.setColumns(['dialogue', 'assets'])
    width.value = 1000
    expect(settings.visibleColumns.value).toEqual(['dialogue'])
    settings.saveWidth(340, 260, { columnKey: 'description' })
    await nextTick()
    expect(JSON.parse(localStorage.getItem('shot-grid:shot-table:v1:1'))).toMatchObject({ mode: 'custom', columns: ['dialogue'], widths: { description: 340 } })
    settings.resetPresentation()
    expect(settings.visibleColumns.value).toEqual([])
    expect(settings.widths.value).toEqual({})
    scope.stop()
  })

  it('重新进入恢复列宽和完整模式，切换账号不串用偏好', async () => {
    localStorage.setItem('shot-grid:shot-table:v1:1', JSON.stringify({ mode: 'full', widths: { description: 360, unknown: 99, plan: -1, assets: 150 } }))
    const scope = effectScope()
    const user = ref(1)
    const settings = scope.run(() => useShotTablePresentation(user, ref(1200)))
    expect(settings.visibleColumns.value).toHaveLength(6)
    expect(settings.widths.value).toEqual({ description: 360 })
    user.value = 2
    await nextTick()
    expect(settings.mode.value).toBe('auto')
    expect(settings.widths.value).toEqual({})
    user.value = 1
    await nextTick()
    expect(settings.mode.value).toBe('full')
    expect(settings.widths.value.description).toBe(360)
    scope.stop()
  })

  it('损坏的偏好不阻止页面初始化', () => {
    localStorage.setItem('shot-grid:shot-table:v1:1', '{invalid')
    const scope = effectScope()
    const settings = scope.run(() => useShotTablePresentation(ref(1), ref(1200)))
    expect(settings.mode.value).toBe('auto')
    scope.stop()
  })

  it('历史自定义偏好不能重新显示暂时隐藏的场景角色列', () => {
    localStorage.setItem('shot-grid:shot-table:v1:1', JSON.stringify({ mode: 'custom', columns: ['assets', 'dialogue'] }))
    const scope = effectScope()
    const settings = scope.run(() => useShotTablePresentation(ref(1), ref(1900)))
    expect(settings.visibleColumns.value).toEqual(['dialogue'])
    settings.mode.value = 'full'
    expect(settings.visibleColumns.value).not.toContain('assets')
    scope.stop()
  })
})
