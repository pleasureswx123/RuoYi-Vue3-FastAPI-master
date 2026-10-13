import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TargetPurgeStatus from '@/components/TargetPurgeStatus.vue'
import { listTargetPurges } from '@/api/shot-grid/targetPurges'
vi.mock('@/store/modules/session', () => ({ useSessionStore: () => ({ permissions: ['shotgrid:shot:forceDelete'] }) }))
vi.mock('@/api/shot-grid/targetPurges', () => ({ listTargetPurges: vi.fn(), retryTargetPurge: vi.fn() }))
let wrapper
const row = { purgeId: 1, targetLabel: '0010', purgeStatus: 'pending', canRetry: false }
afterEach(() => { wrapper?.unmount(); vi.clearAllMocks(); vi.useRealTimers() })
describe('永久清理页面状态', () => {
  it('刷新页面恢复未完成记录，清理完成后停止轮询', async () => {
    vi.useFakeTimers()
    listTargetPurges.mockResolvedValueOnce({ rows: [row], total: 1 }).mockResolvedValue({ rows: [], total: 0 })
    wrapper = mount(TargetPurgeStatus, { props: { projectId: 1, entityType: 'shot' } })
    await flushPromises()
    expect(wrapper.text()).toContain('文件仍在清理')
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(wrapper.text()).not.toContain('文件仍在清理')
    await vi.advanceTimersByTimeAsync(10000)
    expect(listTargetPurges).toHaveBeenCalledTimes(2)
  })
  it('切换项目后不接受旧项目迟到的响应', async () => {
    let resolveOld
    listTargetPurges.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve })).mockResolvedValue({ rows: [], total: 0 })
    wrapper = mount(TargetPurgeStatus, { props: { projectId: 1, entityType: 'shot' } })
    await wrapper.setProps({ projectId: 2 })
    await flushPromises()
    resolveOld({ rows: [row], total: 1 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('0010')
  })
  it('没有对应实体权限时不查询', async () => {
    wrapper = mount(TargetPurgeStatus, { props: { projectId: 1, entityType: 'asset' } })
    await flushPromises()
    expect(listTargetPurges).not.toHaveBeenCalled()
  })
})
