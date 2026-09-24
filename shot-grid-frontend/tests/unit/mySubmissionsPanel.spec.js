import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElTable, ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElDatePicker, ElPagination, ElTag } from 'element-plus'
import MySubmissionsPanel from '@/views/workbench/MySubmissionsPanel.vue'
import { getRecentMineVersions } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'

const push = vi.hoisted(() => vi.fn())
const openDetail = vi.hoisted(() => vi.fn(() => true))
vi.mock('@/components/RelatedDetailDrawer.vue', () => ({ default: {
  name: 'RelatedDetailDrawer', template: '<div />', setup: (_props, { expose }) => { expose({ open: openDetail }) }
} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/shot-grid/reviews', () => ({ getRecentMineVersions: vi.fn() }))
const row = { versionId: 29, taskId: 69, projectId: 13, projectName: '罗刹夫人', taskName: '镜头制作', versionNumber: 'V001', candidateCount: 4, versionStatus: 'rejected', autoReviewListId: 87 }
async function render() {
  const wrapper = mount(MySubmissionsPanel, { global: { components: { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElDatePicker, ElPagination, ElTag }, directives: { loading: {} } } })
  await flushPromises()
  return wrapper
}
const button = (wrapper, label) => wrapper.findAllComponents(ElButton).find(item => item.text() === label)
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  useSessionStore().permissions = ['*:*:*']
  getRecentMineVersions.mockResolvedValue({ rows: [row], total: 21 })
})
describe('我的提交', () => {
  it('同任务各版本归为子级，按版本倒序且跨项目保持独立', async () => {
    getRecentMineVersions.mockResolvedValue({ rows: [
      { ...row, versionNo: 1 },
      { ...row, versionId: 30, versionNo: 2, versionNumber: 'V002' },
      { ...row, projectId: 14, taskId: 70, versionId: 31, versionNo: 1 }
    ], total: 2 })
    const wrapper = await render()
    const data = wrapper.findComponent(ElTable).props('data')
    expect(data).toHaveLength(2)
    expect(data[0].children.map(item => item.versionId)).toEqual([30, 29])
    expect(data[0].versionId).toBe(30)
    expect(data[0].rowKey).not.toBe(data[1].rowKey)
    await wrapper.find('.el-table__expand-icon').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('V001')
    expect(wrapper.text()).toContain('V002')
    wrapper.unmount()
  })

  it('服务端分页浏览全部提交，使用真实审核单 ID', async () => {
    const wrapper = await render()
    expect(wrapper.text()).toContain('镜头制作')
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 1, pageSize: 10, groupByTask: true, orderByColumn: 'shotNo', isAsc: 'ascending' }), expect.anything())
    await wrapper.find('.el-pagination .btn-next').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 2 }), expect.anything())
    await button(wrapper, '查看审核').trigger('click')
    expect(openDetail).toHaveBeenCalledWith('/reviews/87')
    await button(wrapper, '查看最新版本').trigger('click')
    expect(openDetail).toHaveBeenCalledWith('/versions/29')
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ElPagination).props('currentPage')).toBe(2)
    wrapper.unmount()
  })
  it('查询提交筛选，日期倒置阻止请求，重置清空筛选', async () => {
    const wrapper = await render()
    const inputs = wrapper.findAllComponents(ElInput)
    await inputs[0].find('input').setValue('罗刹')
    await inputs[1].find('input').setValue('0010')
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 'rejected')
    const dates = wrapper.findComponent(ElDatePicker)
    dates.vm.$emit('update:modelValue', ['2026-09-24', '2026-09-01'])
    await button(wrapper, '查询').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).toHaveBeenCalledTimes(1)
    dates.vm.$emit('update:modelValue', ['2026-09-01', '2026-09-24'])
    await button(wrapper, '查询').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 1, projectKeyword: '罗刹', taskKeyword: '0010', versionStatus: 'rejected', submittedFrom: '2026-09-01', submittedTo: '2026-09-24' }), expect.anything())
    await button(wrapper, '重置').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions.mock.lastCall[0]).not.toHaveProperty('projectKeyword')
    expect(inputs[0].find('input').element.value).toBe('')
    wrapper.unmount()
  })
  it('失败明确提示，重试中卸载会取消请求', async () => {
    getRecentMineVersions.mockRejectedValueOnce(new Error('失败'))
    const wrapper = await render()
    expect(wrapper.text()).toContain('提交记录加载失败')
    getRecentMineVersions.mockReturnValue(new Promise(() => {}))
    await button(wrapper, '重新加载').trigger('click')
    const signal = getRecentMineVersions.mock.lastCall[1].signal
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
  })
})
