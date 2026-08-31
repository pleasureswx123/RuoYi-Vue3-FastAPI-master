import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useThemeStore } from '@/store/modules/theme'
import ScheduleGanttAdapter from '@/views/schedule/components/ScheduleGanttAdapter.vue'

const runtimeRows = [{
  taskId: 31,
  taskName: 'S010 动画',
  taskKind: 'shot_video',
  taskStatus: 'in_progress',
  priority: 'high',
  lockVersion: 8,
  target: { targetKind: 'shot', targetId: 101, name: 'EP01-S010' },
  assignee: { userId: 7, userName: '杨景锋' },
  currentStart: '2026-09-01T09:00:00',
  currentEnd: '2026-09-05T18:00:00',
  baselineStart: '2026-08-31T09:00:00',
  baselineEnd: '2026-09-04T18:00:00',
  conflicts: [],
  allowedActions: []
}]

const runtimeProps = {
  scale: 'day',
  windowStart: '2026-09-01T00:00:00',
  windowEnd: '2026-10-01T00:00:00',
  editable: false,
  rows: runtimeRows
}

describe('SVAR OSS 真实运行门禁', () => {
  let contextSpy
  let dataUrlSpy
  let canvasContext
  let computedStyleSpy
  let initialColorScheme
  let initialThemeColor

  beforeEach(() => {
    initialColorScheme = document.documentElement.style.colorScheme
    initialThemeColor = document.querySelector('meta[name="theme-color"]')?.getAttribute('content') ?? null
    setActivePinia(createPinia())
    window.localStorage.removeItem('shot-grid.theme-mode')
    document.documentElement.classList.remove('dark')
    document.documentElement.dataset.theme = 'light'
    vi.stubGlobal('ResizeObserver', class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    canvasContext = {
      translate: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      strokeStyle: ''
    }
    contextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext)
    dataUrlSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,grid')

    // JSDOM 不计算自定义属性继承；仅补齐浏览器会提供给 SVAR Canvas 的这一项结果。
    const originalGetComputedStyle = window.getComputedStyle.bind(window)
    computedStyleSpy = vi.spyOn(window, 'getComputedStyle').mockImplementation((element, pseudoElement) => {
      const computed = originalGetComputedStyle(element, pseudoElement)
      const gantt = element.closest?.('.wx-gantt')
      if (!gantt) return computed
      return new Proxy(computed, {
        get(target, property) {
          if (property !== 'getPropertyValue') {
            return Reflect.get(target, property, target)
          }
          return name => {
            if (name === '--wx-gantt-border') {
              return gantt.style.getPropertyValue(name) || target.getPropertyValue(name)
            }
            return target.getPropertyValue(name)
          }
        }
      })
    })
  })

  afterEach(() => {
    computedStyleSpy.mockRestore()
    contextSpy.mockRestore()
    dataUrlSpy.mockRestore()
    window.localStorage.removeItem('shot-grid.theme-mode')
    document.documentElement.classList.remove('dark')
    document.documentElement.dataset.theme = 'light'
    document.documentElement.style.colorScheme = initialColorScheme
    const themeColor = document.querySelector('meta[name="theme-color"]')
    if (themeColor && initialThemeColor === null) {
      themeColor.removeAttribute('content')
    } else if (themeColor) {
      themeColor.setAttribute('content', initialThemeColor)
    }
    vi.unstubAllGlobals()
  })

  it('使用固定排期夹具挂载真实甘特组件', async () => {
    expect(HTMLCanvasElement.prototype.getContext).toBe(contextSpy)
    const wrapper = mount(ScheduleGanttAdapter, {
      attachTo: document.body,
      props: runtimeProps
    })

    await nextTick()
    expect(wrapper.find('.wx-gantt').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-gantt-adapter"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('把项目主题变量桥接到真实甘特组件的背景和边框契约', async () => {
    const wrapper = mount(ScheduleGanttAdapter, {
      attachTo: document.body,
      props: runtimeProps
    })
    await nextTick()

    const adapter = wrapper.get('[data-testid="schedule-gantt-adapter"]').element
    const gantt = wrapper.get('.wx-gantt').element
    const headerCell = wrapper.get('[role="columnheader"]').element
    const timeScale = wrapper.get('.wx-scale').element
    const headerTexts = wrapper.findAll('[role="columnheader"]').map(column => column.text())

    expect(adapter.style.background).toBe('var(--sg-surface)')
    expect(adapter.style.border).toBe('1px solid var(--sg-border)')
    expect(adapter.style.borderRadius).toBe('var(--sg-radius-md, 14px)')
    expect(gantt.style.getPropertyValue('--wx-background')).toBe('var(--sg-surface)')
    expect(gantt.style.getPropertyValue('--wx-gantt-border-color')).toBe('#d7dbde')
    expect(gantt.style.getPropertyValue('--wx-gantt-border')).toBe('1px solid #d7dbde')
    expect(gantt.style.getPropertyValue('--wx-grid-body-cell-border')).toBe('var(--wx-gantt-border)')
    expect(gantt.style.getPropertyValue('--wx-grid-body-row-border')).toBe('var(--wx-gantt-border)')
    expect(canvasContext.strokeStyle).toBe('#d7dbde')
    expect(headerTexts).toEqual(['任务名称', '开始日期'])
    expect(wrapper.text()).not.toContain('Duration')
    expect(gantt).toBeInstanceOf(HTMLElement)
    expect(headerCell).toBeInstanceOf(HTMLElement)
    expect(timeScale).toBeInstanceOf(HTMLElement)

    const initialGridRenderCount = dataUrlSpy.mock.calls.length
    useThemeStore().setDark(true)
    await nextTick()
    const darkGantt = wrapper.get('.wx-gantt').element
    expect(darkGantt.style.getPropertyValue('--wx-gantt-border')).toBe('1px solid #30353d')
    expect(canvasContext.strokeStyle).toBe('#30353d')
    expect(dataUrlSpy.mock.calls.length).toBeGreaterThan(initialGridRenderCount)
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    wrapper.unmount()
  })
})
