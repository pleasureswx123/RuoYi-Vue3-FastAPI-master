import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ScheduleGanttAdapter from '@/views/schedule/components/ScheduleGanttAdapter.vue'

describe('SVAR OSS 真实运行门禁', () => {
  let contextSpy
  let dataUrlSpy

  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    contextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      translate: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      strokeStyle: ''
    })
    dataUrlSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,grid')
  })

  afterEach(() => {
    contextSpy.mockRestore()
    dataUrlSpy.mockRestore()
    vi.unstubAllGlobals()
  })

  it('使用固定排期夹具挂载真实甘特组件', async () => {
    expect(HTMLCanvasElement.prototype.getContext).toBe(contextSpy)
    const wrapper = mount(ScheduleGanttAdapter, {
      attachTo: document.body,
      props: {
        scale: 'day',
        editable: false,
        rows: [{
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
      }
    })

    await nextTick()
    expect(wrapper.find('.wx-gantt').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-gantt-adapter"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
