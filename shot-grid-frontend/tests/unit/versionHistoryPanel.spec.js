import { ElButton, ElIcon, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import VersionHistoryPanel from '@/components/version/VersionHistoryPanel.vue'
import { setElSelectValue } from '../helpers/elementPlus'

vi.mock('@/api/shot-grid/versions', () => ({
  downloadProtectedVersionFile: vi.fn(),
  getTaskVersions: vi.fn(),
  getVersionDetail: vi.fn()
}))

const mountOptions = { global: { components: { ElButton, ElIcon, ElTag } } }

function listItem(versionId, taskId = 31, overrides = {}) {
  return {
    versionId,
    projectId: 8,
    taskId,
    versionNo: versionId,
    versionNumber: `V${String(versionId).padStart(3, '0')}`,
    versionStatus: 'pending_review',
    changelog: `版本 ${versionId} 修改说明`,
    submittedBy: 7,
    submitterName: '制作人甲',
    submittedTime: '2026-08-11T12:00:00',
    generatedAtMs: 1,
    lockVersion: 0,
    ...overrides
  }
}

function detail(versionId, taskId = 31, overrides = {}) {
  return {
    data: {
      ...listItem(versionId, taskId),
      aiParams: null,
      files: [],
      autoReviewList: { reviewListId: 100 + versionId, reviewListName: `自动审核 V${versionId}`, reviewStatus: 'pending', lockVersion: 0 },
      ...overrides
    }
  }
}

describe('版本历史面板', () => {
  beforeEach(() => {
    getTaskVersions.mockResolvedValue({ rows: [listItem(2), listItem(1)], total: 2 })
    getVersionDetail.mockImplementation(versionId => Promise.resolve(detail(versionId)))
  })

  it('使用服务端分页版本历史并加载所选版本真实详情', async () => {
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, operationGeneration: 5, pageSize: 10, canList: true, canQuery: true, canDownload: true }
    })
    await flushPromises()

    expect(getTaskVersions).toHaveBeenCalledWith(31, {
      pageNum: 1,
      pageSize: 10,
      orderByColumn: 'versionNo',
      isAsc: 'descending'
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(getVersionDetail).toHaveBeenCalledWith(2, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('V002')
    expect(wrapper.text()).toContain('自动审核 V2')

    await wrapper.findAll('.version-rail > button').find(button => button.text().includes('V001')).trigger('click')
    await flushPromises()
    expect(getVersionDetail).toHaveBeenLastCalledWith(1, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.emitted('version-selected').at(-1)[1]).toEqual({ taskId: 31, versionId: 1, operationGeneration: 5 })
    wrapper.unmount()
  })

  it('状态筛选回到第一页并提交稳定英文状态', async () => {
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: true, canQuery: true }
    })
    await flushPromises()
    await setElSelectValue(wrapper.findComponent({ name: 'ElSelect' }), 'rejected')
    await flushPromises()
    expect(getTaskVersions).toHaveBeenLastCalledWith(31, expect.objectContaining({
      pageNum: 1,
      versionStatus: 'rejected'
    }), expect.any(Object))
    wrapper.unmount()
  })

  it('任务切换会取消旧列表并拒绝迟到响应覆盖当前任务', async () => {
    let resolveOld
    getTaskVersions.mockImplementationOnce((_taskId, _params, options) => new Promise(resolve => {
      resolveOld = resolve
      expect(options.signal.aborted).toBe(false)
    })).mockResolvedValueOnce({ rows: [listItem(8, 32, { changelog: '任务 B 版本' })], total: 1 })
    getVersionDetail.mockResolvedValueOnce(detail(8, 32))

    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, operationGeneration: 1, canList: true, canQuery: true }
    })
    await flushPromises()
    const oldSignal = getTaskVersions.mock.calls[0][2].signal
    await wrapper.setProps({ taskId: 32, operationGeneration: 2 })
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    expect(wrapper.text()).toContain('任务 B 版本')

    resolveOld({ rows: [listItem(9, 31, { changelog: '迟到任务 A 版本' })], total: 1 })
    await flushPromises()
    expect(wrapper.text()).toContain('任务 B 版本')
    expect(wrapper.text()).not.toContain('迟到任务 A 版本')
    wrapper.unmount()
  })

  it('详情响应若不属于当前任务则失败关闭且不渲染文件', async () => {
    getVersionDetail.mockResolvedValueOnce(detail(2, 999))
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: true, canQuery: true }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('版本详情与当前任务不匹配')
    expect(wrapper.find('.version-detail-card').exists()).toBe(false)
    wrapper.unmount()
  })

  it('无列表权限时不发起版本请求', async () => {
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: false, canQuery: false }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('当前账号没有版本列表权限')
    expect(getTaskVersions).not.toHaveBeenCalled()
    expect(getVersionDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('慢详情请求期间切到空版本任务会清理 loading', async () => {
    let resolveOldDetail
    getVersionDetail.mockImplementationOnce(() => new Promise(resolve => { resolveOldDetail = resolve }))
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, operationGeneration: 1, canList: true, canQuery: true }
    })
    await flushPromises()
    getTaskVersions.mockResolvedValueOnce({ rows: [], total: 0 })
    await wrapper.setProps({ taskId: 32, operationGeneration: 2 })
    await flushPromises()

    expect(wrapper.text()).toContain('该任务还没有正式版本')
    expect(wrapper.text()).not.toContain('正在加载版本详情')
    resolveOldDetail(detail(2, 31))
    await flushPromises()
    expect(wrapper.text()).not.toContain('版本 2 修改说明')
    wrapper.unmount()
  })
})
