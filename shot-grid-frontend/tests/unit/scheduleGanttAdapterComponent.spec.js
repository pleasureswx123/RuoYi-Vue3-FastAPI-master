import { defineComponent, h, nextTick, onMounted } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const ganttHarness = vi.hoisted(() => ({
  interceptors: new Map(),
  listeners: new Map(),
  receivedProps: null
}))

vi.mock('@svar-ui/vue-gantt', () => ({
  Gantt: defineComponent({
    name: 'SvarGanttHarness',
    props: {
      tasks: { type: Array, default: () => [] },
      links: { type: Array, default: () => [] },
      scales: { type: Array, default: () => [] },
      cellWidth: { type: Number, default: 0 },
      lengthUnit: { type: String, default: '' },
      taskTemplate: { type: Object, default: null },
      readonly: Boolean,
      init: { type: Function, default: null }
    },
    setup(props) {
      ganttHarness.receivedProps = props
      onMounted(() => {
        props.init?.({
          intercept(action, handler) {
            ganttHarness.interceptors.set(action, handler)
          },
          on(action, handler) {
            ganttHarness.listeners.set(action, handler)
          }
        })
      })
      return () => h('div', { class: 'svar-gantt-harness' })
    }
  })
}))

import ScheduleGanttAdapter from '@/views/schedule/components/ScheduleGanttAdapter.vue'

const scheduleRow = {
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
  allowedActions: ['task.schedule']
}

describe('ScheduleGanttAdapter', () => {
  beforeEach(() => {
    ganttHarness.interceptors.clear()
    ganttHarness.listeners.clear()
    ganttHarness.receivedProps = null
  })

  it('拦截渲染器本地更新并只向上游发排期草稿', async () => {
    const wrapper = mount(ScheduleGanttAdapter, {
      props: { rows: [scheduleRow], scale: 'day', editable: true }
    })
    await nextTick()

    const interceptUpdate = ganttHarness.interceptors.get('update-task')
    expect(interceptUpdate).toEqual(expect.any(Function))
    expect(interceptUpdate({
      id: 'task:31',
      task: {
        start: new Date(2026, 8, 2, 9, 0, 0),
        end: new Date(2026, 8, 6, 18, 0, 0),
        assigneeUserId: 7
      }
    })).toBe(false)
    expect(wrapper.emitted('range-change-request')).toEqual([[
      {
        taskId: 31,
        lockVersion: 8,
        expectedStartTime: '2026-09-02T09:00:00',
        expectedEndTime: '2026-09-06T18:00:00',
        operationSource: 'gantt'
      }
    ]])
    expect(ganttHarness.receivedProps.readonly).toBe(false)
    expect(ganttHarness.receivedProps.lengthUnit).toBe('day')
    expect(ganttHarness.receivedProps.taskTemplate?.name).toBe('ScheduleGanttTaskTemplate')
  })

  it('把渲染器选择动作转换为领域任务点击事件', async () => {
    const wrapper = mount(ScheduleGanttAdapter, {
      props: { rows: [scheduleRow], scale: 'week', editable: false }
    })
    await nextTick()

    const selectTask = ganttHarness.listeners.get('select-task')
    expect(selectTask).toEqual(expect.any(Function))
    selectTask({ id: 'task:31' })
    expect(wrapper.emitted('task-click')).toEqual([[{ taskId: 31 }]])
    expect(ganttHarness.receivedProps.readonly).toBe(true)
    expect(ganttHarness.receivedProps.lengthUnit).toBe('week')
  })
})
