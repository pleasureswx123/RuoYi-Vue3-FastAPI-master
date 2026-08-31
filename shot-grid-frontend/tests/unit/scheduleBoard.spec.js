import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectSchedule, getTaskScheduleChanges } from '@/api/shot-grid/schedules'
import ScheduleBoard from '@/views/schedule/ScheduleBoard.vue'
import PersonnelSwimlane from '@/views/schedule/components/PersonnelSwimlane.vue'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'
import ScheduleToolbar from '@/views/schedule/components/ScheduleToolbar.vue'
import TaskGantt from '@/views/schedule/components/TaskGantt.vue'

vi.mock('@/views/schedule/components/ScheduleGanttAdapter.vue', () => ({
  default: {
    name: 'ScheduleGanttAdapter',
    props: ['rows', 'scale', 'editable'],
    emits: ['task-click', 'range-change-request', 'change-rejected'],
    template: '<div data-testid="schedule-gantt-stub" />'
  }
}))

vi.mock('@/api/shot-grid/schedules', () => ({
  getProjectSchedule: vi.fn(),
  getTaskScheduleChanges: vi.fn(),
  getUnscheduledScheduleTasks: vi.fn()
}))

const rows = [
  {
    taskId: 31,
    projectId: 11,
    taskKind: 'shot_video',
    taskStatus: 'in_progress',
    priority: 'high',
    lockVersion: 8,
    target: { targetKind: 'shot', targetId: 101, code: 'EP001-001-0010', name: 'EP001-001-0010' },
    assignee: { userId: 7, userName: '杨景锋' },
    currentStart: '2026-09-01T09:00:00',
    currentEnd: '2026-09-05T18:00:00',
    baselineStart: '2026-08-31T09:00:00',
    baselineEnd: '2026-09-04T18:00:00',
    conflicts: [{ taskId: 32, targetName: 'EP001-001-0020', startTime: '2026-09-03T09:00:00', endTime: '2026-09-06T18:00:00' }],
    allowedActions: ['schedule']
  },
  {
    taskId: 32,
    projectId: 11,
    taskKind: 'shot_video',
    taskStatus: 'not_started',
    priority: 'normal',
    lockVersion: 2,
    target: { targetKind: 'shot', targetId: 102, code: 'EP001-001-0020', name: 'EP001-001-0020' },
    assignee: { userId: 7, userName: '杨景锋' },
    currentStart: '2026-09-03T09:00:00',
    currentEnd: '2026-09-06T18:00:00',
    baselineStart: '2026-09-03T09:00:00',
    baselineEnd: '2026-09-06T18:00:00',
    conflicts: [{ taskId: 31, targetName: 'EP001-001-0010', startTime: '2026-09-01T09:00:00', endTime: '2026-09-05T18:00:00' }],
    allowedActions: ['schedule']
  }
]

describe('共享任务排期面板', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getProjectSchedule.mockResolvedValue({
      data: { rows, groups: [{ groupKey: 'assignee:7', groupName: '杨景锋', sortOrder: 0, taskCount: 2 }], total: 2, unscheduledCount: 1, serverTime: '2026-09-02T09:00:00' }
    })
    getTaskScheduleChanges.mockResolvedValue({ rows: [], total: 0, hasNext: false })
  })

  it('默认只读并让人员泳道稳定堆叠同人重叠任务', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00',
        editableAllowed: true
      }
    })
    await flushPromises()

    const swimlane = wrapper.getComponent(PersonnelSwimlane)
    expect(swimlane.props('editable')).toBe(false)
    expect(wrapper.findAll('[data-testid="personnel-lane"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="personnel-lane"]').attributes('data-track-count')).toBe('2')
    expect(wrapper.text()).toContain('默认只读')
  })

  it('切换甘特模式更新查询状态，点击任务打开同一详情抽屉', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()

    await wrapper.get('[data-task-id="31"]').trigger('click')
    expect(wrapper.getComponent(ScheduleTaskDrawer).props()).toMatchObject({ visible: true, task: rows[0] })

    wrapper.getComponent(ScheduleToolbar).vm.$emit('update:mode', 'gantt')
    await flushPromises()
    expect(wrapper.findComponent(TaskGantt).exists()).toBe(true)
    expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({ mode: 'gantt', scale: 'week' })
  })

  it('无编辑授权时拒绝进入编辑模式', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00',
        editableAllowed: false
      }
    })
    await flushPromises()

    wrapper.getComponent(ScheduleToolbar).vm.$emit('edit-toggle', true)
    await flushPromises()

    expect(wrapper.getComponent(PersonnelSwimlane).props('editable')).toBe(false)
    expect(wrapper.text()).toContain('没有调整排期权限')
  })
})
