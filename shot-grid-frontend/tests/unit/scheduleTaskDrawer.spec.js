import { flushPromises, mount } from '@vue/test-utils'
import { ElAlert, ElTag } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getTaskScheduleChanges } from '@/api/shot-grid/schedules'
import ScheduleTaskDrawer from '@/views/schedule/components/ScheduleTaskDrawer.vue'

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

  it('把人员重叠显示为业务警告，并只保留排期决策信息', async () => {
    getTaskScheduleChanges.mockResolvedValue({ rows: [], total: 0, hasNext: false })
    wrapper = mount(ScheduleTaskDrawer, {
      attachTo: document.body,
      props: { visible: true, task, canEdit: true },
      global: { stubs: { teleport: true } }
    })
    await flushPromises()

    const conflictAlert = wrapper.findAllComponents(ElAlert).find(alert => alert.text().includes('人员排期重叠'))
    const conflictTag = wrapper.findAllComponents(ElTag).find(tag => tag.text().includes('项重叠'))

    expect(conflictAlert?.props('type')).toBe('warning')
    expect(conflictTag?.props('type')).toBe('warning')
    expect(conflictAlert?.text()).not.toContain('排期已正常加载，这不是系统故障')
    expect(conflictAlert?.text()).toContain('EP001-001-0020')
    expect(conflictAlert?.text()).toContain('重叠时段')
    expect(conflictAlert?.find('time[datetime="2026-09-03T09:00:00"]').exists()).toBe(true)
    expect(conflictAlert?.find('time[datetime="2026-09-05T18:00:00"]').exists()).toBe(true)
    expect(conflictAlert?.text()).toContain('可调整当前排期，或在保存时确认保留重叠')
  })
})
