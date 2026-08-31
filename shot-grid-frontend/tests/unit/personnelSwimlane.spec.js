import { mount } from '@vue/test-utils'
import { ElTooltip } from 'element-plus'
import { describe, expect, it } from 'vitest'

import PersonnelSwimlane from '@/views/schedule/components/PersonnelSwimlane.vue'

const task = {
  taskId: 31,
  projectId: 11,
  taskKind: 'shot_video',
  taskStatus: 'in_progress',
  priority: 'high',
  lockVersion: 8,
  target: { targetKind: 'shot', targetId: 101, code: 'EP001-002-0002', name: 'EP001-002-0002' },
  assignee: { userId: 7, userName: '庞晓亮' },
  currentStart: '2026-08-30T09:00:00',
  currentEnd: '2026-09-01T09:00:00',
  baselineStart: '2026-08-30T09:00:00',
  baselineEnd: '2026-09-01T09:00:00',
  conflicts: [],
  allowedActions: ['schedule']
}

describe('人员泳道任务条', () => {
  it('日视图为时间窗口中的每个自然日生成独立日期格', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [task],
        windowStart: '2026-08-23T00:00:00',
        windowEnd: '2026-08-27T00:00:00',
        scale: 'day'
      }
    })

    expect(wrapper.findAll('.personnel-swimlane__tick').map(item => item.text())).toEqual([
      '08-23',
      '08-24',
      '08-25',
      '08-26'
    ])
  })

  it('长时间窗口按甘特图日刻度宽度横向展开', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [task],
        windowStart: '2026-08-30T00:00:00',
        windowEnd: '2027-01-30T00:00:00',
        scale: 'day'
      }
    })

    const swimlane = wrapper.get('[data-testid="personnel-swimlane"]')
    expect(wrapper.findAll('.personnel-swimlane__tick')).toHaveLength(153)
    expect(swimlane.attributes('style')).toContain(
      '--personnel-timeline-width: 11016px'
    )
    expect(swimlane.element.style.minWidth).toBe('11186px')
  })

  it('短时间窗口铺满父容器并保留时间轴最小宽度', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [task],
        windowStart: '2026-08-01T00:00:00',
        windowEnd: '2026-09-01T00:00:00',
        scale: 'month'
      }
    })

    const swimlane = wrapper.get('[data-testid="personnel-swimlane"]')
    expect(swimlane.element.style.width).toBe('100%')
    expect(swimlane.element.style.minWidth).toBe('890px')
  })

  it.each([
    {
      scale: 'week',
      windowStart: '2026-08-23T00:00:00',
      windowEnd: '2026-09-15T00:00:00',
      labels: ['08-17', '08-24', '08-31', '09-07', '09-14']
    },
    {
      scale: 'month',
      windowStart: '2026-08-23T00:00:00',
      windowEnd: '2026-11-10T00:00:00',
      labels: ['2026-08', '2026-09', '2026-10', '2026-11']
    }
  ])('$scale 视图按自然时间边界生成日期格', ({ scale, windowStart, windowEnd, labels }) => {
    const wrapper = mount(PersonnelSwimlane, {
      props: { rows: [task], windowStart, windowEnd, scale }
    })

    expect(wrapper.findAll('.personnel-swimlane__tick').map(item => item.text())).toEqual(labels)
  })

  it('只渲染与当前时间窗口相交的任务', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [
          {
            ...task,
            taskId: 30,
            currentStart: '2026-07-30T09:00:00',
            currentEnd: '2026-08-01T00:00:00'
          },
          {
            ...task,
            taskId: 31,
            currentStart: '2026-08-30T09:00:00',
            currentEnd: '2026-09-01T00:00:00'
          },
          {
            ...task,
            taskId: 32,
            currentStart: '2026-09-01T00:00:00',
            currentEnd: '2026-09-03T09:00:00'
          }
        ],
        windowStart: '2026-08-01T00:00:00',
        windowEnd: '2026-09-01T00:00:00',
        scale: 'day'
      }
    })

    expect(wrapper.findAll('.personnel-task').map(item => item.attributes('data-task-id'))).toEqual(['31'])
    expect(wrapper.get('[data-testid="personnel-lane"]').text()).toContain('1 项任务')
  })

  it('不绘制完全位于窗口外的首版基线', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [{
          ...task,
          currentStart: '2026-08-15T09:00:00',
          currentEnd: '2026-08-16T09:00:00',
          baselineStart: '2026-09-02T09:00:00',
          baselineEnd: '2026-09-03T09:00:00'
        }],
        windowStart: '2026-08-01T00:00:00',
        windowEnd: '2026-09-01T00:00:00',
        scale: 'day'
      }
    })

    expect(wrapper.get('.personnel-task__baseline').attributes('style')).toContain('display: none')
  })

  it('把首版基线放在当前任务色块下方', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [task],
        windowStart: '2026-08-23T00:00:00',
        windowEnd: '2026-10-10T00:00:00',
        scale: 'day'
      }
    })

    expect(wrapper.get('[data-task-id="31"]').element.style.top).toBe('8px')
    expect(wrapper.get('.personnel-task__baseline').element.style.top).toBe('39px')
  })

  it('切换首版基线可见性时保持相邻任务的横向位置', async () => {
    const adjacentButtonStyle = document.createElement('style')
    adjacentButtonStyle.textContent = '.el-button + .el-button { margin-left: 12px; }'
    document.head.append(adjacentButtonStyle)

    try {
      const wrapper = mount(PersonnelSwimlane, {
        props: {
          rows: [
            task,
            {
              ...task,
              taskId: 32,
              target: { ...task.target, targetId: 102, code: 'EP001-002-0003', name: 'EP001-002-0003' },
              currentStart: '2026-09-02T09:00:00',
              currentEnd: '2026-09-03T09:00:00',
              baselineStart: '2026-09-02T09:00:00',
              baselineEnd: '2026-09-03T09:00:00'
            }
          ],
          windowStart: '2026-08-23T00:00:00',
          windowEnd: '2026-10-10T00:00:00',
          scale: 'day',
          showBaseline: true
        }
      })

      await wrapper.setProps({ showBaseline: false })

      const taskButtons = wrapper.findAll('.personnel-task')
      const baselines = wrapper.findAll('.personnel-task__baseline')
      expect(Number.parseFloat(getComputedStyle(taskButtons[1].element).marginLeft || '0')).toBe(0)
      expect(baselines).toHaveLength(2)
      expect(baselines.every(item => item.element.style.visibility === 'hidden')).toBe(true)
    } finally {
      adjacentButtonStyle.remove()
    }
  })

  it('保持真实时长宽度，并通过悬浮提示提供完整任务信息', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [task],
        windowStart: '2026-08-23T00:00:00',
        windowEnd: '2026-10-10T00:00:00',
        scale: 'day'
      }
    })

    const taskButton = wrapper.get('[data-task-id="31"]')
    const width = Number.parseFloat(taskButton.attributes('style').match(/width:\s*([\d.]+)%/)?.[1])
    const tooltip = wrapper.getComponent(ElTooltip)

    expect(width).toBeCloseTo(4.1667, 3)
    expect(tooltip.props('content')).toBe(
      'EP001-002-0002 · 负责人：庞晓亮 · 排期：2026/08/30 09:00 至 2026/09/01 09:00'
    )
  })

  it('按场次分组时显示场次泳道而不是负责人泳道', () => {
    const wrapper = mount(PersonnelSwimlane, {
      props: {
        rows: [{ ...task, groupKey: 'scene:5', groupName: '动力舱' }],
        groupBy: 'scene',
        windowStart: '2026-08-23T00:00:00',
        windowEnd: '2026-10-10T00:00:00',
        scale: 'day'
      }
    })

    expect(wrapper.get('.personnel-swimlane__header>strong').text()).toBe('场次')
    expect(wrapper.get('[data-testid="personnel-lane"] header strong').text()).toBe('动力舱')
  })
})
