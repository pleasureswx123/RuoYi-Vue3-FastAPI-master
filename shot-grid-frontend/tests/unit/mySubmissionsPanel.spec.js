import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElTable, ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElDatePicker, ElPagination, ElTag } from 'element-plus'
import MySubmissionsPanel from '@/views/workbench/MySubmissionsPanel.vue'
import { getRecentMineVersions, getMineSubmissionProjects } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'

const push = vi.hoisted(() => vi.fn())
const openDetail = vi.hoisted(() => vi.fn(() => true))
vi.mock('@/components/RelatedDetailDrawer.vue', () => ({ default: {
  name: 'RelatedDetailDrawer', template: '<div />', setup: (_props, { expose }) => { expose({ open: openDetail }) }
} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/shot-grid/reviews', () => ({ getRecentMineVersions: vi.fn(), getMineSubmissionProjects: vi.fn() }))
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
  getMineSubmissionProjects.mockResolvedValue({ data: [{ projectId: 13, projectName: '罗刹夫人', projectCode: 'LCFR', projectStatus: 'archived' }] })
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
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 1, pageSize: 10, groupByTask: true, orderByColumn: 'submittedTime', isAsc: 'descending' }), expect.anything())
    await wrapper.find('.el-pagination .btn-next').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 2 }), expect.anything())
    await button(wrapper, '查看修改意见').trigger('click')
    expect(openDetail).toHaveBeenCalledWith('/reviews/87')
    await button(wrapper, '查看作品').trigger('click')
    expect(openDetail).toHaveBeenCalledWith('/versions/29')
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ElPagination).props('currentPage')).toBe(2)
    wrapper.unmount()
  })
  it('展开后隐藏父行重复操作，各历史版本使用自身状态与真实 ID', async () => {
    getRecentMineVersions.mockResolvedValue({ rows: [
      { ...row, versionNo: 1 },
      { ...row, versionId: 30, versionNo: 2, versionNumber: 'V002', versionStatus: 'pending_review', autoReviewListId: 88 },
      { ...row, versionId: 31, versionNo: 3, versionNumber: 'V003', versionStatus: 'final', autoReviewListId: 89 }
    ], total: 1 })
    const wrapper = await render()
    expect(button(wrapper, '查看审核结果').props()).toMatchObject({ type: 'success' })
    await wrapper.find('.el-table__expand-icon').trigger('click')
    await flushPromises()
    expect(wrapper.find('.el-table__row--level-0 .submission-actions').text()).toBe('')
    const childRows = wrapper.findAll('.el-table__row--level-1')
    expect(childRows).toHaveLength(3)
    for (const [index, type] of ['success', 'warning', 'danger'].entries()) {
      const actions = childRows[index].find('.submission-actions').findAllComponents(ElButton)
      expect(actions[0].props()).toMatchObject({ type, size: 'small' })
      expect(actions[0].props('plain')).toBeFalsy()
      expect(actions[1].props('link')).toBeFalsy()
      expect(actions[1].props()).toMatchObject({ type, plain: true, size: 'small' })
    }
    expect(childRows[0].text()).toContain('查看审核结果')
    expect(childRows[1].text()).toContain('查看审核进度')
    expect(childRows[2].text()).toContain('查看修改意见')
    expect(button(wrapper, '查看修改意见').props('plain')).toBeFalsy()
    await button(wrapper, '查看修改意见').trigger('click')
    expect(openDetail).toHaveBeenLastCalledWith('/reviews/87')
    await button(wrapper, '查看审核进度').trigger('click')
    expect(openDetail).toHaveBeenLastCalledWith('/reviews/88')
    await childRows[2].findAllComponents(ElButton).find(item => item.text() === 'V001').trigger('click')
    expect(openDetail).toHaveBeenLastCalledWith('/versions/29')
    await wrapper.find('.el-table__expand-icon').trigger('click')
    await flushPromises()
    expect(wrapper.find('.el-table__row--level-0 .submission-actions').text()).toContain('查看审核结果')
    wrapper.unmount()
  })

  it('缺少查看权限或审核单时不提供无效入口', async () => {
    useSessionStore().permissions = ['shotgrid:version:list']
    const wrapper = await render()
    expect(button(wrapper, '查看作品')).toBeUndefined()
    expect(button(wrapper, '查看修改意见')).toBeUndefined()
    expect(button(wrapper, 'V001')).toBeUndefined()
    wrapper.unmount()
    useSessionStore().permissions = ['*:*:*']
    getRecentMineVersions.mockResolvedValue({ rows: [{ ...row, autoReviewListId: null }], total: 1 })
    const noReview = await render()
    expect(button(noReview, '查看修改意见')).toBeUndefined()
    expect(button(noReview, '查看作品')).toBeDefined()
    noReview.unmount()
  })

  it('查询提交筛选，日期倒置阻止请求，重置清空筛选', async () => {
    const wrapper = await render()
    const input = wrapper.find('input[placeholder=搜索任务名称]')
    await input.setValue('0010')
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 13)
    await wrapper.find('input[type=radio][value=rejected]').setValue()
    await flushPromises()
    getRecentMineVersions.mockClear()
    const dates = wrapper.findComponent(ElDatePicker)
    dates.vm.$emit('update:modelValue', ['2026-09-24', '2026-09-01'])
    await button(wrapper, '搜索').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).not.toHaveBeenCalled()
    dates.vm.$emit('update:modelValue', ['2026-09-01', '2026-09-24'])
    await button(wrapper, '搜索').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions).toHaveBeenLastCalledWith(expect.objectContaining({ pageNum: 1, projectId: 13, taskKeyword: '0010', versionStatus: 'rejected', submittedFrom: '2026-09-01', submittedTo: '2026-09-24' }), expect.anything())
    await button(wrapper, '重置').trigger('click')
    await flushPromises()
    expect(getRecentMineVersions.mock.lastCall[0]).not.toHaveProperty('projectId')
    expect(input.element.value).toBe('')
    wrapper.unmount()
  })
  it('项目选择与日期快捷项即时筛选，快速切换丢弃迟到响应', async () => {
    const wrapper = await render()
    expect(wrapper.findComponent(ElSelect).props('filterable')).toBe(true)
    expect(wrapper.text()).not.toContain('仅显示已退回')
    const shortcuts = wrapper.findComponent(ElDatePicker).props('shortcuts')
    expect(shortcuts.map(item => item.text)).toEqual(['今天', '近7天', '近30天'])
    const [start, end] = shortcuts[1].value()
    expect(start.getHours()).toBe(0)
    expect(Math.round((new Date(end.getFullYear(), end.getMonth(), end.getDate()) - start) / 86400000)).toBe(6)
    let resolveOld
    getRecentMineVersions.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const project = wrapper.findComponent(ElSelect)
    project.vm.$emit('update:modelValue', 13)
    project.vm.$emit('change', 13)
    await flushPromises()
    const oldSignal = getRecentMineVersions.mock.lastCall[1].signal
    expect(getRecentMineVersions.mock.lastCall[0].projectId).toBe(13)
    expect(wrapper.text()).toContain('镜头制作')
    await wrapper.find('input[type=radio][value=rejected]').setValue()
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    expect(wrapper.text()).toContain('仅显示已退回的提交版本')
    resolveOld({ rows: [{ ...row, taskName: '迟到记录' }], total: 1 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('迟到记录')
    const dates = wrapper.findComponent(ElDatePicker)
    dates.vm.$emit('update:modelValue', ['2026-09-01', '2026-09-29'])
    await dates.vm.$nextTick()
    dates.findComponent({ name: 'Picker' }).vm.$emit('change', ['2026-09-01', '2026-09-29'])
    await flushPromises()
    expect(getRecentMineVersions.mock.lastCall[0]).toMatchObject({ submittedFrom: '2026-09-01', submittedTo: '2026-09-29', pageNum: 1 })
    wrapper.unmount()
  })

  it('项目选项失败可重试，空结果提供清空筛选', async () => {
    getMineSubmissionProjects.mockRejectedValueOnce(new Error('失败'))
    getRecentMineVersions.mockResolvedValue({ rows: [], total: 0 })
    const wrapper = await render()
    expect(wrapper.text()).toContain('项目选项加载失败')
    expect(wrapper.text()).toContain('没有符合条件的提交记录')
    await button(wrapper, '重试项目选项').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('项目选项加载失败')
    expect(wrapper.findComponent(ElSelect).findAllComponents(ElOption)[0].props('label')).toContain('已归档')
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
