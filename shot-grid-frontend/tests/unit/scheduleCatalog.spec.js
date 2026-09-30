import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { getProjectSchedule } from '@/api/shot-grid/schedules'
import { useScheduleCatalog } from '@/views/schedule/useScheduleCatalog'

vi.mock('@/api/shot-grid/schedules', () => ({ getProjectSchedule: vi.fn() }))

describe('排期窗口选项', () => {
  it('加载所有分页，并隔离切换项目后的旧响应', async () => {
    let resolveOld
    getProjectSchedule.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    let catalog
    const wrapper = mount({
      props: ['projectId'],
      setup(props) { catalog = useScheduleCatalog(() => ({ projectId: props.projectId })); return {} },
      template: '<div />'
    }, { props: { projectId: 11 } })
    getProjectSchedule.mockResolvedValueOnce({ data: { rows: [{ taskId: 21 }], hasNext: true } })
      .mockResolvedValueOnce({ data: { rows: [{ taskId: 22 }], hasNext: false } })
    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    resolveOld({ data: { rows: [{ taskId: 11 }] } })
    await flushPromises()
    expect(catalog.rows.value.map(row => row.taskId)).toEqual([21, 22])
    expect(getProjectSchedule.mock.calls[0][2].signal.aborted).toBe(true)
    wrapper.unmount()
  })
})
