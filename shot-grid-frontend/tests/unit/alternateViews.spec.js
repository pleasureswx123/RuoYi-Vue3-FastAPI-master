import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElCollapse, ElForm, ElInput, ElTable } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getUnscheduledScheduleTasks } from '@/api/shot-grid/schedules'
import { getAssetItems } from '@/api/shot-grid/assets'
import ScheduleToolbar from '@/views/schedule/components/ScheduleToolbar.vue'
import UnscheduledTaskDrawer from '@/views/schedule/components/UnscheduledTaskDrawer.vue'
import AssetCardItems from '@/views/asset/components/AssetCardItems.vue'

vi.mock('@/api/shot-grid/schedules', () => ({ getUnscheduledScheduleTasks: vi.fn() }))
vi.mock('@/api/shot-grid/assets', () => ({ getAssetItems: vi.fn() }))
const click = async (wrapper, label) => {
  const button = wrapper.findAllComponents(ElButton).find(button => button.text() === label)
  expect(button, label).toBeTruthy()
  await button.trigger('click')
  await flushPromises()
}
const task = id => ({ taskId: id, projectId: 8, taskStatus: 'in_progress', assignee: { userId: 7, userName: '制作 A' }, target: { code: `镜头 ${id}` }, allowedActions: ['schedule'] })
const item = id => ({ assetItemId: id, assetId: 2, projectId: 8, productionItem: `场景分项 ${id}`, lifecycleStatus: 'active', assetStatus: 'in_progress', task: { assigneeUserId: 7, assigneeName: '制作 A' } })

describe('简洁视图的操作与隔离', () => {
  beforeEach(() => vi.resetAllMocks())

  it('未设周期任务按人显示，直接打开任务；超过首批可继续加载', async () => {
    getUnscheduledScheduleTasks.mockResolvedValueOnce({ data: { rows: [task(1)], total: 2 } })
      .mockResolvedValueOnce({ data: { rows: [task(2)], total: 2 } })
    const wrapper = mount(UnscheduledTaskDrawer, { props: { visible: true, inline: true, projectId: 8, query: { targetKind: 'shot' }, editableAllowed: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('无需先排期或确认开工')
    expect(wrapper.text()).toContain('制作 A · 1 项')
    await click(wrapper, '镜头 1')
    expect(wrapper.emitted('open-task')[0][0].taskId).toBe(1)
    await click(wrapper, '设置周期')
    expect(wrapper.emitted('edit-task')[0][0].taskId).toBe(1)
    await click(wrapper, '加载更多')
    expect(getUnscheduledScheduleTasks).toHaveBeenLastCalledWith(8, expect.objectContaining({ pageNum: 2, targetKind: 'shot' }), expect.anything())
    expect(wrapper.getComponent(ElTable).props('data').map(row => row.taskId)).toEqual([1, 2])
    expect(wrapper.text()).toContain('制作 A · 2 项')
    wrapper.unmount()
  })

  it('未设周期任务切项目中止旧读取，拒绝旧响应和越范围数据，可重试', async () => {
    let resolveOld
    getUnscheduledScheduleTasks.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce({ data: { rows: [task(1)], total: 1 } })
      .mockResolvedValueOnce({ data: { rows: [{ ...task(2), projectId: 9 }], total: 1 } })
    const wrapper = mount(UnscheduledTaskDrawer, { props: { visible: true, inline: true, projectId: 8, query: {} } })
    const oldSignal = getUnscheduledScheduleTasks.mock.calls[0][2].signal
    await wrapper.setProps({ projectId: 9 })
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    expect(wrapper.text()).toContain('加载失败')
    resolveOld({ data: { rows: [task(99)], total: 1 } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('镜头 99')
    await click(wrapper, '重试')
    expect(wrapper.text()).toContain('镜头 2')
    expect(wrapper.text()).not.toContain('设置周期')
    wrapper.unmount()
  })

  it('收起抽屉后不接受迟到响应', async () => {
    let resolveOld
    getUnscheduledScheduleTasks.mockImplementation(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mount(UnscheduledTaskDrawer, { props: { visible: true, inline: true, projectId: 8, query: {} } })
    await wrapper.setProps({ visible: false })
    resolveOld({ data: { rows: [task(99)], total: 1 } })
    await flushPromises()
    expect(wrapper.findComponent(ElTable).exists()).toBe(false)
    wrapper.unmount()
  })

  it('更多筛选默认收起；校验失败不应用，快捷筛选仍走表单，重置清空', async () => {
    const wrapper = mount(ScheduleToolbar, { props: { filters: {}, currentUserId: 7, targetKind: 'shot', embedded: true, windowStart: '2026-11-02T00:00:00', windowEnd: '2026-11-09T00:00:00' } })
    expect(wrapper.getComponent(ElForm).props('model')).toHaveProperty('keyword')
    expect(wrapper.find('[aria-label="排期视图"]').exists()).toBe(false)
    const more = wrapper.findAllComponents(ElButton).find(button => button.text() === '更多筛选')
    expect(more.attributes('aria-expanded')).toBe('false')
    await click(wrapper, '更多筛选')
    expect(wrapper.text()).toContain('收起筛选')
    await wrapper.getComponent(ElInput).setValue('x'.repeat(201))
    await click(wrapper, '应用筛选')
    expect(wrapper.emitted('filters-change')).toBeUndefined()
    await wrapper.getComponent(ElInput).setValue('镜头')
    await click(wrapper, '只看我的')
    expect(wrapper.emitted('filters-change').at(-1)[0]).toMatchObject({ keyword: '镜头', assigneeUserIds: [7] })
    await click(wrapper, '有反馈')
    expect(wrapper.emitted('filters-change').at(-1)[0].taskStatuses).toEqual(['revision'])
    await click(wrapper, '重置')
    expect(wrapper.emitted('filters-change').at(-1)[0]).toMatchObject({ keyword: '', assigneeUserIds: [], taskStatuses: [] })
    await wrapper.setProps({ loading: true })
    expect(wrapper.findAllComponents(ElButton).find(button => button.text() === '只看我的').props('disabled')).toBe(true)
    wrapper.unmount()
  })

  it('资产卡片按需读取分项，继承制作人和状态筛选并打开准确分项', async () => {
    getAssetItems.mockResolvedValue({ data: [item(1), { ...item(2), assetStatus: 'completed' }, { ...item(3), lifecycleStatus: 'archived' }] })
    const wrapper = mount(AssetCardItems, { props: { projectId: 8, asset: { assetId: 2, itemCount: 3 }, filters: { assetStatus: 'in_progress', assigneeUserId: '7' } } })
    expect(getAssetItems).not.toHaveBeenCalled()
    wrapper.getComponent(ElCollapse).vm.$emit('update:modelValue', ['items'])
    await flushPromises()
    expect(wrapper.text()).toContain('制作 A')
    expect(wrapper.text()).not.toContain('场景分项 2')
    expect(wrapper.text()).not.toContain('场景分项 3')
    await click(wrapper, '场景分项 1')
    expect(wrapper.emitted('open-item')[0][0]).toMatchObject({ assetId: 2, assetItemId: 1 })
    await wrapper.setProps({ filters: { assigneeUserId: '99' } })
    expect(wrapper.text()).toContain('没有匹配分项')
    wrapper.unmount()
  })

  it('资产卡片拒绝跨资产数据，关闭后不接收旧请求', async () => {
    getAssetItems.mockResolvedValueOnce({ data: [{ ...item(1), assetId: 3 }] })
    let resolveOld
    getAssetItems.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mount(AssetCardItems, { props: { projectId: 8, asset: { assetId: 2, itemCount: 1 } } })
    wrapper.getComponent(ElCollapse).vm.$emit('update:modelValue', ['items'])
    await flushPromises()
    expect(wrapper.text()).toContain('分项加载失败')
    await click(wrapper, '重试')
    wrapper.getComponent(ElCollapse).vm.$emit('update:modelValue', [])
    await flushPromises()
    resolveOld({ data: [item(1)] })
    await flushPromises()
    expect(wrapper.findAll('.asset-card-items__row')).toHaveLength(0)
    wrapper.unmount()
  })
})
