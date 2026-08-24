import { ElOption, ElSelect } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getMemberCandidatePage, getProjectMemberCandidatePage } from '@/api/shot-grid/projects'
import MemberCandidateSelect from '@/views/project/components/MemberCandidateSelect.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  getMemberCandidatePage: vi.fn(),
  getProjectMemberCandidatePage: vi.fn()
}))

describe('成员候选搜索范围', () => {
  beforeEach(() => {
    getMemberCandidatePage.mockResolvedValue({ rows: [] })
    getProjectMemberCandidatePage.mockResolvedValue({ rows: [] })
  })

  it('创建项目时使用 project:add 保护的全局候选接口', async () => {
    const wrapper = mount(MemberCandidateSelect)
    wrapper.findComponent(ElSelect).vm.$emit('visible-change', true)
    await flushPromises()

    expect(getMemberCandidatePage).toHaveBeenCalledWith(
      { pageNum: 1, pageSize: 20, keyword: undefined, deptId: undefined },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(getProjectMemberCandidatePage).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('已有项目添加成员时使用项目范围候选接口', async () => {
    const wrapper = mount(MemberCandidateSelect, {
      props: { projectId: 19 },
      global: {}
    })
    wrapper.findComponent(ElSelect).vm.$emit('visible-change', true)
    await flushPromises()

    expect(getProjectMemberCandidatePage).toHaveBeenCalledWith(
      19,
      { pageNum: 1, pageSize: 20, keyword: undefined, deptId: undefined },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(getMemberCandidatePage).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('创建项目时把当前部门传给候选接口，并返回选择的成员摘要', async () => {
    getMemberCandidatePage.mockResolvedValue({
      rows: [{ userId: 7, userName: 'creator', nickName: '制作人员', deptId: 100, deptName: '策划营销部门' }]
    })
    const wrapper = mount(MemberCandidateSelect, {
      props: { departmentId: 100 },
      attachTo: document.body
    })
    const select = wrapper.findComponent(ElSelect)
    select.vm.$emit('visible-change', true)
    await flushPromises()

    expect(getMemberCandidatePage).toHaveBeenCalledWith(
      { pageNum: 1, pageSize: 20, keyword: undefined, deptId: 100 },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(wrapper.findComponent(ElOption).props('label')).toBe('制作人员')
    select.vm.$emit('change', '7')
    await flushPromises()
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ userId: 7, userName: 'creator' })
    wrapper.unmount()
  })
})
