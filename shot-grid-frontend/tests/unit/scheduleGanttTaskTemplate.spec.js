import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScheduleGanttTaskTemplate from '@/views/schedule/components/ScheduleGanttTaskTemplate.vue'

describe('ScheduleGanttTaskTemplate', () => {
  it('使用自有覆盖层同时展示首次基线、冲突和任务名称', () => {
    const wrapper = mount(ScheduleGanttTaskTemplate, {
      props: {
        data: {
          text: 'S010 动画',
          start: new Date('2026-09-02T00:00:00'),
          end: new Date('2026-09-06T00:00:00'),
          baseline: {
            start: new Date('2026-09-01T00:00:00'),
            end: new Date('2026-09-04T00:00:00')
          },
          conflictTaskIds: [32],
          readonly: false
        }
      }
    })

    expect(wrapper.get('[data-testid="schedule-baseline-shadow"]').attributes('style')).toContain('left: -25%')
    expect(wrapper.get('[data-testid="schedule-baseline-shadow"]').attributes('style')).toContain('width: 75%')
    expect(wrapper.get('[data-testid="schedule-task-content"]').classes()).toContain('is-conflicted')
    expect(wrapper.text()).toContain('S010 动画')
  })
})
