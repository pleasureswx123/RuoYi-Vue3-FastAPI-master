import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScheduleGanttTaskTemplate from '@/views/schedule/components/ScheduleGanttTaskTemplate.vue'

describe('ScheduleGanttTaskTemplate', () => {
  it('普通任务始终把标题包在当前排期条块中', () => {
    const wrapper = mount(ScheduleGanttTaskTemplate, {
      props: {
        data: {
          text: 'EP001-003-0004',
          taskStatus: 'in_progress',
          start: new Date('2026-09-13T00:00:00'),
          end: new Date('2026-09-19T00:00:00'),
          baseline: {
            start: new Date('2026-09-08T00:00:00'),
            end: new Date('2026-09-10T00:00:00')
          },
          conflictTaskIds: [],
          readonly: true
        }
      }
    })

    const currentBar = wrapper.get('[data-testid="schedule-current-bar"]')
    expect(currentBar.classes()).toContain('is-current-schedule')
    expect(currentBar.classes()).toContain('status-in_progress')
    expect(currentBar.get('.schedule-task-content__label').text()).toBe('EP001-003-0004')
    expect(wrapper.get('[data-testid="schedule-baseline-shadow"]').attributes('style')).toContain('left: -83.3333%')
  })

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
    expect(wrapper.get('[data-testid="schedule-current-bar"]').classes()).toContain('is-conflicted')
    expect(wrapper.text()).toContain('S010 动画')
  })

  it('关闭首版基线后仅隐藏灰色基线并保留当前排期条块', () => {
    const wrapper = mount(ScheduleGanttTaskTemplate, {
      props: {
        data: {
          text: 'EP001-003-0004',
          taskStatus: 'in_progress',
          start: new Date('2026-09-13T00:00:00'),
          end: new Date('2026-09-19T00:00:00'),
          baseline: {
            start: new Date('2026-09-08T00:00:00'),
            end: new Date('2026-09-10T00:00:00')
          },
          showBaseline: false,
          conflictTaskIds: [],
          readonly: true
        }
      }
    })

    expect(wrapper.find('[data-testid="schedule-baseline-shadow"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="schedule-current-bar"]').text()).toBe('EP001-003-0004')
  })
})
