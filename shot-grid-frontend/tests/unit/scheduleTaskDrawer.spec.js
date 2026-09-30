import { flushPromises, mount } from '@vue/test-utils'
import { ElAlert, ElTag } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'

import { getTaskScheduleChanges } from '@/api/shot-grid/schedules'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'

vi.mock('@/api/shot-grid/productionHistory', () => ({ getProductionHistory: vi.fn().mockResolvedValue({ data: { lanes: [], events: [] } }) }))

vi.mock('@/api/shot-grid/schedules', () => ({
  getTaskScheduleChanges: vi.fn()
}))

const task = {
  taskId: 31,
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
  conflicts: [
    {
      taskId: 32,
      targetName: 'EP001-001-0020',
      startTime: '2026-09-03T09:00:00',
      endTime: '2026-09-06T18:00:00'
    }
  ],
  allowedActions: ['schedule']
}

describe('排期详情抽屉', () => {
  let wrapper

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('允许排期重叠，详情不展示重叠警告和计数并保留排期信息', async () => {
    getTaskScheduleChanges.mockResolvedValue({ rows: [], total: 0, hasNext: false })
    wrapper = mount(ScheduleTaskDrawer, {
      attachTo: document.body,
      props: { visible: true, task, canEdit: true },
      global: { plugins: [createPinia()], stubs: { teleport: true } }
    })
    await flushPromises()

    const conflictAlert = wrapper.findAllComponents(ElAlert).find(alert => alert.text().includes('人员排期重叠'))
    const conflictTag = wrapper.findAllComponents(ElTag).find(tag => tag.text().includes('项重叠'))

    expect(conflictAlert).toBeUndefined()
    expect(conflictTag).toBeUndefined()
    expect(wrapper.text()).not.toContain('EP001-001-0020')
    expect(wrapper.text()).toContain('当前开始')
    expect(wrapper.text()).toContain('首版基线')
    expect(wrapper.text()).toContain('最近排期变更')
    expect(wrapper.text()).toContain('调整排期')
  })
  it('权限读取完成后显示底部操作，打开业务入口时保留排期详情', async () => {
    getTaskScheduleChanges.mockResolvedValue({ rows: [] })
    const run = vi.fn()
    const actionLoader = vi.fn().mockResolvedValue({ allowedActions: ['task.review'] })
    const actionFactory = target => target?.allowedActions?.includes('task.review')
      ? [{ key: 'review', button: { label: '审核任务', type: 'primary', plain: false }, run }]
      : []
    wrapper = mount(ScheduleTaskDrawer, {
      props: { visible: true, task, actionLoader, actionFactory },
      global: { plugins: [createPinia()], stubs: { teleport: true } }
    })
    expect(wrapper.text()).toContain('正在加载可用操作')
    await flushPromises()
    expect(actionLoader).toHaveBeenCalledWith(task, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    await wrapper.get('.el-drawer__footer button').trigger('click')
    expect(wrapper.emitted('update:visible')).toBeUndefined()
    expect(wrapper.props('visible')).toBe(true)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('切换任务取消旧权限读取并忽略迟到结果，失败时可重试', async () => {
    getTaskScheduleChanges.mockResolvedValue({ rows: [] })
    let resolveOld
    const actionLoader = vi.fn()
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockRejectedValueOnce(new Error('权限读取失败'))
      .mockResolvedValueOnce(null)
    const actionFactory = vi.fn(() => [])
    wrapper = mount(ScheduleTaskDrawer, {
      props: { visible: true, task, actionLoader, actionFactory },
      global: { plugins: [createPinia()], stubs: { teleport: true } }
    })
    const signal = actionLoader.mock.calls[0][1].signal
    await wrapper.setProps({ task: { ...task, taskId: 32 } })
    await flushPromises()
    expect(signal.aborted).toBe(true)
    resolveOld({ taskId: 31, allowedActions: ['task.review'] })
    await flushPromises()
    expect(actionFactory).not.toHaveBeenCalledWith(expect.objectContaining({ taskId: 31 }))
    expect(wrapper.text()).toContain('权限读取失败')
    await wrapper.get('.el-drawer__footer button').trigger('click')
    await flushPromises()
    expect(actionLoader).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).not.toContain('权限读取失败')
  })
})
