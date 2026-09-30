import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton, ElCheckbox, ElDatePicker, ElSelect } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectSchedule, getTaskScheduleChanges, updateTaskSchedule } from '@/api/shot-grid/schedules'
import ScheduleBoard from '@/views/schedule/ScheduleBoard.vue'
import PersonnelSwimlane from '@/views/schedule/components/PersonnelSwimlane.vue'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'
import ScheduleToolbar from '@/views/schedule/components/ScheduleToolbar.vue'
import TaskGantt from '@/views/schedule/components/TaskGantt.vue'

vi.mock('@/views/schedule/components/ScheduleGanttAdapter.vue', () => ({
  default: {
    name: 'ScheduleGanttAdapter',
    props: ['rows', 'scale', 'editable'],
    emits: ['task-click', 'range-change-request', 'change-rejected'],
    template: '<div data-testid="schedule-gantt-stub"><div class="wx-chart"><div class="wx-area"><div class="wx-bars"><div class="wx-bar">任务</div></div></div></div></div>'
  }
}))

vi.mock('@/api/shot-grid/productionHistory', () => ({ getProductionHistory: vi.fn().mockResolvedValue({ data: { lanes: [], events: [] } }) }))
vi.mock('@/api/shot-grid/schedules', () => ({
  getProjectSchedule: vi.fn(),
  getTaskScheduleChanges: vi.fn(),
  getUnscheduledScheduleTasks: vi.fn(),
  updateTaskSchedule: vi.fn()
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

async function changeDatePicker(datePicker, value) {
  datePicker.vm.$emit('update:modelValue', value)
  await datePicker.vm.$nextTick()
  datePicker.findComponent({ name: 'Picker' }).vm.$emit('change', value)
  await datePicker.vm.$nextTick()
}

describe('共享任务排期面板', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getProjectSchedule.mockResolvedValue({
      data: { rows, groups: [{ groupKey: 'assignee:7', groupName: '杨景锋', sortOrder: 0, taskCount: 2 }], total: 2, unscheduledCount: 1, serverTime: '2026-09-02T09:00:00' }
    })
    getTaskScheduleChanges.mockResolvedValue({ rows: [], total: 0, hasNext: false })
  })

  it('点击图例立即筛选并同步下拉框，再次点击恢复全部状态', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00',
        initialFilters: { keyword: 'EP001', assigneeUserIds: [7] }
      }
    })
    await flushPromises()
    getProjectSchedule.mockResolvedValueOnce({ data: { rows: [rows[0]], groups: [], total: 1 } })
    const legend = wrapper.get('.schedule-board__legend [data-status="in_progress"]')
    await legend.trigger('click')
    await flushPromises()
    expect(getProjectSchedule).toHaveBeenLastCalledWith(11, expect.objectContaining({
      taskStatuses: ['in_progress'], keyword: 'EP001', assigneeUserIds: [7]
    }), expect.anything())
    expect(wrapper.getComponent(PersonnelSwimlane).props('rows')).toHaveLength(1)
    expect(wrapper.getComponent(ScheduleToolbar).findAllComponents(ElSelect).some(select =>
      JSON.stringify(select.props('modelValue')) === '["in_progress"]'
    )).toBe(true)
    expect(legend.attributes('aria-pressed')).toBe('true')
    await legend.trigger('click')
    await flushPromises()
    expect(getProjectSchedule).toHaveBeenLastCalledWith(11, expect.objectContaining({ taskStatuses: [] }), expect.anything())
    expect(wrapper.getComponent(PersonnelSwimlane).props('rows')).toHaveLength(2)
    expect(legend.attributes('aria-pressed')).toBe('false')
    wrapper.unmount()
  })

  it('空白处拖动和 Shift 滚轮横移画布，任务条仍可点击且不触发筛选请求', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()
    const viewport = wrapper.get('.schedule-board__viewport')
    Object.defineProperties(viewport.element, {
      scrollWidth: { value: 1600 }, clientWidth: { value: 800 }
    })
    viewport.element.scrollLeft = 100
    const pointer = (type, x) => {
      const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, button: 0 })
      Object.defineProperty(event, 'pointerId', { value: 1 })
      return event
    }
    viewport.element.dispatchEvent(pointer('pointerdown', 300))
    window.dispatchEvent(pointer('pointermove', 220))
    await wrapper.vm.$nextTick()
    expect(viewport.element.scrollLeft).toBe(180)
    expect(viewport.classes()).toContain('is-panning')
    window.dispatchEvent(pointer('pointerup', 220))
    window.dispatchEvent(pointer('pointermove', 100))
    expect(viewport.element.scrollLeft).toBe(180)
    viewport.element.dispatchEvent(new WheelEvent('wheel', { shiftKey: true, deltaY: 60, cancelable: true }))
    expect(viewport.element.scrollLeft).toBe(240)
    viewport.element.dispatchEvent(new WheelEvent('wheel', { deltaY: 60, cancelable: true }))
    expect(viewport.element.scrollLeft).toBe(240)
    const bar = wrapper.get('.personnel-task')
    bar.element.dispatchEvent(pointer('pointerdown', 300))
    window.dispatchEvent(pointer('pointermove', 200))
    expect(viewport.element.scrollLeft).toBe(240)
    await bar.trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(ScheduleTaskDrawer).props('visible')).toBe(true)
    expect(getProjectSchedule).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('甘特图拖动内部画布而非外层容器，保留任务条操作并在失焦后结束拖动', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11, initialMode: 'gantt',
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()
    const chart = wrapper.get('.wx-chart').element
    Object.defineProperties(chart, { scrollWidth: { value: 1600 }, clientWidth: { value: 800 } })
    chart.scrollLeft = 100
    const pointer = (type, x) => {
      const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, button: 0 })
      Object.defineProperty(event, 'pointerId', { value: 1 })
      return event
    }
    wrapper.get('.wx-bars').element.dispatchEvent(pointer('pointerdown', 300))
    window.dispatchEvent(pointer('pointermove', 220))
    expect(chart.scrollLeft).toBe(180)
    expect(wrapper.get('.schedule-board__viewport').element.scrollLeft).toBe(0)
    window.dispatchEvent(new Event('blur'))
    window.dispatchEvent(pointer('pointermove', 100))
    expect(chart.scrollLeft).toBe(180)
    wrapper.get('.wx-area').element.dispatchEvent(new WheelEvent('wheel', { bubbles: true, shiftKey: true, deltaY: 60, cancelable: true }))
    expect(chart.scrollLeft).toBe(240)
    wrapper.get('.wx-bar').element.dispatchEvent(pointer('pointerdown', 300))
    window.dispatchEvent(pointer('pointermove', 200))
    expect(chart.scrollLeft).toBe(240)
    expect(getProjectSchedule).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('筛选后保留窗口选项与状态总数，详情可在当前结果中切换', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: { projectId: 11, initialWindowStart: '2026-09-01T00:00:00', initialWindowEnd: '2026-09-08T00:00:00' }
    })
    await flushPromises()
    wrapper.getComponent(PersonnelSwimlane).vm.$emit('task-click', { taskId: 31 })
    await flushPromises()
    const drawer = wrapper.getComponent(ScheduleTaskDrawer)
    expect(drawer.props('position')).toBe(1)
    expect(drawer.props('total')).toBe(2)
    drawer.vm.$emit('navigate', 1)
    await flushPromises()
    expect(drawer.props('task').taskId).toBe(32)
    expect(drawer.props('position')).toBe(2)
    getProjectSchedule.mockResolvedValueOnce({ data: { rows: [], total: 0 } })
    await wrapper.get('.schedule-board__legend [data-status="completed"]').trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(ScheduleToolbar).props('filterOptions').assignees).toEqual([{ value: 7, label: '杨景锋' }])
    expect(wrapper.get('.schedule-board__legend [data-status="in_progress"]').text()).toContain('1')
    expect(wrapper.text()).toContain('当前窗口显示 0 项任务')
    wrapper.unmount()
  })

  it('继承镜头号区间并在清空后移除查询范围', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11, targetKind: 'shot',
        initialWindowStart: '2026-09-01T00:00:00', initialWindowEnd: '2026-09-08T00:00:00',
        initialFilters: { shotNoStart: 10, shotNoEnd: 50 }
      }
    })
    await flushPromises()
    expect(getProjectSchedule).toHaveBeenLastCalledWith(11, expect.objectContaining({ shotNoStart: 10, shotNoEnd: 50 }), expect.anything())
    await wrapper.setProps({ initialFilters: {} })
    await flushPromises()
    expect(getProjectSchedule).toHaveBeenLastCalledWith(11, expect.objectContaining({ shotNoStart: null, shotNoEnd: null }), expect.anything())
    wrapper.unmount()
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
    expect(wrapper.text()).toContain('拖动编辑未开启')
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
    expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({ mode: 'gantt', scale: 'day' })
  })

  it('甘特模式关闭共享容器的横向滚动', async () => {
    const wrapper = mount(ScheduleBoard, {
      attachTo: document.body,
      props: {
        projectId: 11,
        initialMode: 'gantt',
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()

    expect(wrapper.get('.schedule-board__viewport').element.style.overflowX).toBe('hidden')
    wrapper.unmount()
  })

  it('工具栏按自然日期展示，并把包含结束日的选择转换为查询边界', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialScale: 'day',
        initialWindowStart: '2026-08-24T00:00:00',
        initialWindowEnd: '2026-09-24T00:00:00'
      }
    })
    await flushPromises()

    const datePicker = wrapper.getComponent(ElDatePicker)
    expect(datePicker.props()).toMatchObject({
      type: 'daterange',
      modelValue: ['2026-08-24', '2026-09-23'],
      valueFormat: 'YYYY-MM-DD',
      format: 'YYYY-MM-DD'
    })

    await changeDatePicker(datePicker, ['2026-09-01', '2026-09-30'])
    await flushPromises()
    expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({
      windowStart: '2026-09-01T00:00:00',
      windowEnd: '2026-10-01T00:00:00'
    })
  })

  it('“回到今天”按当前缩放恢复未来偏重的默认窗口', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 31, 16, 20, 30))
    try {
      const wrapper = mount(ScheduleBoard, {
        props: {
          projectId: 11,
          initialScale: 'day',
          initialWindowStart: '2026-06-01T00:00:00',
          initialWindowEnd: '2026-07-01T00:00:00'
        }
      })
      await flushPromises()

      expect(wrapper.text()).toContain('回到今天')
      wrapper.getComponent(ScheduleToolbar).vm.$emit('window-shift', 0)
      await flushPromises()

      expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({
        scale: 'day',
        windowStart: '2026-08-24T00:00:00',
        windowEnd: '2026-09-24T00:00:00'
      })
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('切换时间缩放时以当前可见的今天为锚点应用对应窗口', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 31, 16, 20, 30))
    try {
      const wrapper = mount(ScheduleBoard, {
        props: {
          projectId: 11,
          initialScale: 'day',
          initialWindowStart: '2026-08-24T00:00:00',
          initialWindowEnd: '2026-09-24T00:00:00'
        }
      })
      await flushPromises()

      wrapper.getComponent(ScheduleToolbar).vm.$emit('update:scale', 'month')
      await flushPromises()

      expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({
        scale: 'month',
        windowStart: '2026-05-01T00:00:00',
        windowEnd: '2027-06-01T00:00:00'
      })
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('月视图的前后导航按完整自然月平移，不因闰年偏离月初', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialScale: 'month',
        initialWindowStart: '2026-01-01T00:00:00',
        initialWindowEnd: '2027-02-01T00:00:00'
      }
    })
    await flushPromises()

    wrapper.getComponent(ScheduleToolbar).vm.$emit('window-shift', 1)
    await flushPromises()

    expect(wrapper.emitted('query-change').at(-1)[0]).toMatchObject({
      windowStart: '2027-02-01T00:00:00',
      windowEnd: '2028-03-01T00:00:00'
    })
  })

  it('响应镜头与资产列表外层视图切换，并按目标类型重新查询', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        targetKind: 'shot',
        initialMode: 'swimlane',
        initialScale: 'week',
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()

    await wrapper.setProps({ targetKind: 'asset_item', initialMode: 'gantt', initialScale: 'month' })
    await flushPromises()

    expect(wrapper.findComponent(TaskGantt).exists()).toBe(true)
    expect(wrapper.findComponent(TaskGantt).props('scale')).toBe('month')
    expect(getProjectSchedule.mock.calls.at(-1)[1]).toMatchObject({ targetKind: 'asset_item' })
  })

  it('直接安排时间无需开启拖动编辑，保存后切换窗口并选中任务', async () => {
    const wrapper = mount(ScheduleBoard, { props: { projectId: 11, editableAllowed: true, initialWindowStart: '2026-09-01T00:00:00', initialWindowEnd: '2026-09-08T00:00:00' } })
    await flushPromises()
    wrapper.getComponent(ScheduleTaskDrawer).vm.$emit('edit', rows[0])
    await flushPromises()
    expect(wrapper.getComponent(ScheduleEditDialog).props('visible')).toBe(true)
    expect(wrapper.getComponent(PersonnelSwimlane).props('editable')).toBe(false)
    const saved = { ...rows[0], currentStart: '2026-11-01T09:00:00', currentEnd: '2026-11-03T18:00:00', lockVersion: 9 }
    getProjectSchedule.mockResolvedValue({ data: { rows: [saved], groups: [], total: 1, hasNext: false } })
    updateTaskSchedule.mockResolvedValueOnce({ data: saved })
    wrapper.getComponent(ScheduleEditDialog).vm.$emit('save-request', { expectedStartTime: saved.currentStart, expectedEndTime: saved.currentEnd, changeReason: '调整计划' })
    await flushPromises()
    expect(wrapper.getComponent(PersonnelSwimlane).props('selectedTaskId')).toBe(saved.taskId)
    expect(wrapper.getComponent(PersonnelSwimlane).props('editable')).toBe(false)
    expect(wrapper.emitted('query-change').at(-1)[0].windowStart).toBe('2026-10-25T00:00:00')
    wrapper.unmount()
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

  it('显式进入编辑后拖动只打开草稿弹窗，不立即改写任务时间', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00',
        editableAllowed: true
      }
    })
    await flushPromises()
    wrapper.getComponent(ScheduleToolbar).vm.$emit('edit-toggle', true)
    await flushPromises()
    wrapper.getComponent(PersonnelSwimlane).vm.$emit('range-change-request', {
      taskId: 31,
      lockVersion: 8,
      expectedStartTime: '2026-09-02T09:00:00',
      expectedEndTime: '2026-09-06T18:00:00',
      operationSource: 'swimlane'
    })
    await flushPromises()

    expect(wrapper.getComponent(ScheduleEditDialog).props('visible')).toBe(true)
    expect(wrapper.getComponent(ScheduleEditDialog).props('draft')).toMatchObject({
      expectedStartTime: '2026-09-02T09:00:00',
      expectedEndTime: '2026-09-06T18:00:00'
    })
    expect(wrapper.getComponent(PersonnelSwimlane).props('rows')[0].currentStart).toBe('2026-09-01T09:00:00')
  })

  it('多选筛选按复数查询参数提交，并可独立隐藏首版基线', async () => {
    const wrapper = mount(ScheduleBoard, {
      props: {
        projectId: 11,
        initialWindowStart: '2026-09-01T00:00:00',
        initialWindowEnd: '2026-09-08T00:00:00'
      }
    })
    await flushPromises()

    const toolbar = wrapper.getComponent(ScheduleToolbar)
    const selectByPlaceholder = placeholder => toolbar.findAllComponents(ElSelect).find(item => item.props('placeholder') === placeholder)
    selectByPlaceholder('全部负责人').vm.$emit('update:modelValue', [7])
    selectByPlaceholder('全部状态').vm.$emit('update:modelValue', ['in_progress'])
    const conflictToggle = toolbar.findAllComponents(ElCheckbox).find(item => item.text() === '仅排期重叠')
    conflictToggle.vm.$emit('update:modelValue', true)
    await toolbar.findAllComponents(ElButton).find(item => item.text() === '应用筛选').trigger('click')
    await flushPromises()

    expect(getProjectSchedule.mock.calls.at(-1)[1]).toMatchObject({
      assigneeUserIds: [7], taskStatuses: ['in_progress'], onlyConflicts: true
    })

    const baselineToggle = toolbar.findAllComponents(ElCheckbox).find(item => item.text() === '对比最初排期')
    expect(wrapper.getComponent(PersonnelSwimlane).props('showBaseline')).toBe(false)
    baselineToggle.vm.$emit('change', true)
    await flushPromises()
    expect(wrapper.getComponent(PersonnelSwimlane).props('showBaseline')).toBe(true)
  })
})
