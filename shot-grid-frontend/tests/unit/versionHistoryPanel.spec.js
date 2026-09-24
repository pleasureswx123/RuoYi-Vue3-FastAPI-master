import { ElAffix, ElButton, ElDialog, ElIcon, ElImage, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadReviewReferenceFile, getReviewActions, getTaskIssues } from '@/api/shot-grid/reviews'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import VersionHistoryPanel from '@/components/version/VersionHistoryPanel.vue'
import { setElSelectValue } from '../helpers/elementPlus'

vi.mock('@/api/shot-grid/versions', () => ({
  downloadProtectedVersionFile: vi.fn(),
  getTaskVersions: vi.fn(),
  getVersionDetail: vi.fn()
}))
vi.mock('@/api/shot-grid/reviews', () => ({
  downloadReviewReferenceFile: vi.fn(),
  getReviewActions: vi.fn(),
  getTaskIssues: vi.fn()
}))

const mountOptions = { global: { components: { ElButton, ElDialog, ElIcon, ElImage, ElTag } } }
const realtimeRefresh = vi.hoisted(() => ({ callback: null }))
vi.mock('@/composables/useVersionRealtime', () => ({
  useVersionRealtime: (_id, callback) => { realtimeRefresh.callback = callback }
}))

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
    submitterName: '曲占锋',
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
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
    getTaskVersions.mockResolvedValue({ rows: [listItem(2), listItem(1)], total: 2 })
    getVersionDetail.mockImplementation(versionId => Promise.resolve(detail(versionId)))
    getReviewActions.mockResolvedValue({ rows: [], total: 0 })
    getTaskIssues.mockResolvedValue({ data: [] })
  })

  it('拆分新增与遗留数量，并从旧版直达后续版本的未修复问题', async () => {
    getVersionDetail.mockImplementation(id => Promise.resolve(detail(id, 31, { candidates: [{ candidateId: id * 100 + 1, candidateNumber: `V00${id}_01`, files: [] }] })))
    getTaskIssues.mockResolvedValue({ data: [
      { issueId: 51, originVersionId: 1, originCandidateId: 101, originVersionNumber: 'V001', pendingVersionId: 2, pendingVersionNumber: 'V002', status: 'open', content: '旧问题仍存在', verifications: [{ checkedVersionId: 2, result: 'still_present', comment: '亮度不足' }] },
      { issueId: 52, originVersionId: 2, originCandidateId: 201, pendingVersionId: 2, status: 'open', content: '新增问题' },
      { issueId: 53, originVersionId: 1, originCandidateId: 101, originVersionNumber: 'V001', status: 'resolved', verifications: [{ checkedVersionId: 2, result: 'resolved' }] }
    ] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    expect(wrapper.get('.feedback-summary').text()).toContain('2 条待处理问题 = 本轮新增 1 条 + 上轮未修复 1 条')
    await wrapper.get('.previous-pending-entry').trigger('click')
    await flushPromises()
    expect(wrapper.get('.opinion-tabs > .el-tabs__header .is-active').text()).toContain('上轮未修复 1')
    expect(wrapper.get('.opinion-tabs > .el-tabs__header').text()).toContain('已修复 1')
    const firstTab = wrapper.findAll('.version-tabs > .el-tabs__header [role="tab"]').find(tab => tab.text().includes('V001'))
    await firstTab.trigger('click')
    await flushPromises()
    expect(wrapper.get('.transferred-hint').text()).toContain('1 条未解决')
    await wrapper.get('.transferred-hint button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.version-tabs > .el-tabs__header .is-active').text()).toContain('V002')
    expect(wrapper.get('.opinion-tabs > .el-tabs__header .is-active').text()).toContain('上轮未修复 1')
    wrapper.unmount()
  })

  it('整体反馈独立展示，不占用候选缩略图或来源文件计数', async () => {
    getVersionDetail.mockImplementation(id => Promise.resolve(detail(id, 31, { candidates: [1, 2, 3].map(n => ({ candidateId: id * 100 + n, candidateNumber: `V00${id}_0${n}`, files: [] })) })))
    getTaskIssues.mockResolvedValue({ data: [
      { issueId: 60, originVersionId: 2, originCandidateId: null, status: 'open', pendingVersionId: 2, content: '全版节奏需要加快', reviewerName: '卢清华', reviewerUserId: 7, createTime: '2026-09-24T16:20:00' },
      { issueId: 61, originVersionId: 2, originCandidateId: 201, status: 'open', pendingVersionId: 2, content: '第一个文件调亮', reviewerName: '审核人乙', reviewerUserId: 8, createTime: '2026-09-24T16:22:00' }
    ] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    expect(wrapper.findAll('.feedback-file')).toHaveLength(3)
    expect(wrapper.get('.feedback-file-nav').text()).not.toContain('整体反馈')
    expect(wrapper.get('.feedback-category-tabs').classes()).toContain('el-tabs--left')
    await wrapper.get('#tab-overall-feedback').trigger('click')
    await flushPromises()
    expect(wrapper.get('.overall-feedback').isVisible()).toBe(true)
    expect(wrapper.get('#tab-files').attributes('aria-selected')).toBe('false')
    expect(wrapper.get('.overall-feedback').text()).toContain('全版节奏需要加快')
    expect(wrapper.get('.overall-feedback').text()).toContain('待处理 1 条')
    expect(wrapper.get('.overall-feedback .feedback-author').text()).toBe('卢清华 · 2026/09/24 16:20 提出')
    expect(wrapper.get('.feedback-summary').text()).toContain('涉及 1 个来源文件')
    await wrapper.get('#tab-files').trigger('click')
    await flushPromises()
    expect(wrapper.get('#tab-overall-feedback').attributes('aria-selected')).toBe('false')
    expect(wrapper.get('.feedback-file-nav').isVisible()).toBe(true)
    expect(wrapper.get('.feedback-list').text()).toContain('第一个文件调亮')
    expect(wrapper.get('.feedback-list .feedback-author').text()).toBe('审核人乙 · 2026/09/24 16:22 提出')
    expect(wrapper.get('.opinion-tabs > .el-tabs__header #tab-current').text()).toBe('本轮问题 1')
    expect(wrapper.get('.feedback-summary').text()).toContain('2 条待处理问题')
    wrapper.unmount()
  })

  it('退回修改使用业务状态卡而不是错误警报', async () => {
    getReviewActions.mockResolvedValueOnce({
      rows: [{
        actionId: 91,
        actionType: 'reject',
        reason: '',
        reviewerUserId: 9,
        reviewerName: '刘远辉',
        createTime: '2026-08-26T17:48:00'
      }],
      total: 1
    })
    getTaskIssues.mockResolvedValueOnce({
      data: [
        { issueId: 51, originVersionId: 2, originCandidateId: 201, pendingVersionId: 2, status: 'open', content: '主体亮度偏低', responses: [], verifications: [] },
        { issueId: 52, originVersionId: 2, originCandidateId: 202, pendingVersionId: 2, status: 'open', content: '运动节奏过快', responses: [], verifications: [] }
      ]
    })
    getVersionDetail.mockResolvedValueOnce(detail(2, 31, { candidates: [{ candidateId: 201, candidateNumber: 'V002_01', files: [{ fileId: 'first' }] }, { candidateId: 202, candidateNumber: 'V002_02', files: [{ fileId: 'second' }] }] }))
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: true, canQuery: true, canListNotes: true }
    })
    await flushPromises()

    const decision = wrapper.get('.feedback-decision')
    expect(decision.classes()).toContain('is-reject')
    expect(decision.text()).toContain('已退回修改')
    expect(decision.text()).toContain('2 条待处理问题 = 本轮新增 2 条 + 上轮未修复 0 条')
    expect(decision.text()).toContain('审核人 刘远辉')
    expect(decision.attributes('role')).not.toBe('alert')
    expect(wrapper.find('.feedback-decision.el-alert').exists()).toBe(false)
    const media = wrapper.findComponent({ name: 'ReviewMediaWorkspace' })
    expect(media.props('version')).toMatchObject({ candidateId: 201, files: [{ fileId: 'first' }] })
    await wrapper.findAll('.feedback-file')[1].trigger('click')
    await flushPromises()
    expect(media.props('version')).toMatchObject({ candidateId: 202, files: [{ fileId: 'second' }] })
    expect(wrapper.text()).toContain('来源文件 V002_02')
    getTaskIssues.mockResolvedValueOnce({ data: [
      { issueId: 53, originVersionId: 2, originCandidateId: 202, pendingVersionId: 2, status: 'open', content: '实时追加的修改意见', responses: [], verifications: [] }
    ] })
    await realtimeRefresh.callback(2)
    await flushPromises()
    expect(wrapper.text()).toContain('实时追加的修改意见')
    expect(media.props('version')).toMatchObject({ candidateId: 202, files: [{ fileId: 'second' }] })
    wrapper.unmount()
  })

  it('在对应问题卡片展示参考附件，下载与图片预览不触发问题选择', async () => {
    const files = [
      { fileId: '11111111-1111-4111-8111-111111111111', originalName: '灯光参考.png', contentType: 'image/png', fileSize: 2048, downloadUrl: '/shot-grid/issues/51/reference-files/11111111-1111-4111-8111-111111111111/download' },
      { fileId: '22222222-2222-4222-8222-222222222222', originalName: '修改要求.pdf', contentType: 'application/pdf', fileSize: 4096, downloadUrl: '/shot-grid/issues/51/reference-files/22222222-2222-4222-8222-222222222222/download' }
    ]
    getTaskIssues.mockResolvedValueOnce({
      data: [
        { issueId: 50, originVersionId: 2, originCandidateId: 201, originVersionNumber: 'V002', pendingVersionId: 2, status: 'open', content: '另一条待处理问题', referenceFiles: [], responses: [], verifications: [] },
        { issueId: 51, originVersionId: 2, originCandidateId: 201, originVersionNumber: 'V002', pendingVersionId: 2, status: 'open', content: '请参考附件调整灯光', referenceFiles: files, responses: [], verifications: [] }
      ]
    })
    downloadReviewReferenceFile.mockImplementation(file => Promise.resolve(new Blob(['参考文件'], { type: file.contentType })))
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = vi.fn(() => 'blob:reference-preview')
      static revokeObjectURL = vi.fn()
    })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: true, canQuery: true, canListNotes: true }
    })
    try {
      await flushPromises()
      const cards = wrapper.findAll('.feedback-list .feedback-item')
      expect(cards[0].find('.review-reference-files').exists()).toBe(false)
      const card = cards[1]
      expect(card.text()).toContain('灯光参考.png')
      expect(card.text()).toContain('修改要求.pdf')
      expect(card.get('.review-reference-files').element.closest('button')).toBeNull()
      const preview = card.findComponent(ElImage)
      expect(preview.props('previewSrcList')).toEqual(['blob:reference-preview'])
      await preview.get('img').trigger('click')
      expect(card.classes()).not.toContain('active')
      await card.get('[aria-label="下载参考文件 修改要求.pdf"]').trigger('click')
      await flushPromises()
      expect(downloadReviewReferenceFile).toHaveBeenLastCalledWith(files[1])
      expect(anchorClick).toHaveBeenCalledOnce()
      expect(card.classes()).not.toContain('active')
      await card.get('.feedback-item__select').trigger('click')
      expect(card.classes()).toContain('active')
    } finally {
      wrapper.unmount()
      anchorClick.mockRestore()
      vi.unstubAllGlobals()
    }
  })

  it('默认选择有待处理意见的文件，并隔离文件与历史记录', async () => {
    getVersionDetail.mockResolvedValueOnce(detail(2, 31, { candidates: [
      { candidateId: 201, candidateNumber: 'V002_01', files: [] },
      { candidateId: 202, candidateNumber: 'V002_02', files: [] }
    ] }))
    getTaskIssues.mockResolvedValueOnce({ data: [
      { issueId: 51, originVersionId: 2, originCandidateId: 202, pendingVersionId: 2, status: 'open', content: '需要调整灯光' },
      { issueId: 52, originVersionId: 2, originCandidateId: 202, status: 'resolved', content: '已修复构图' }
    ] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    expect(wrapper.get('.feedback-file.active').text()).toContain('V002_02')
    expect(wrapper.find('#tab-overall-feedback').exists()).toBe(false)
    expect(wrapper.get('.feedback-category-tabs').classes()).toContain('is-file-only')
    expect(wrapper.get('.version-feedback-panel__heading').text()).toContain('1 条待处理问题 = 本轮新增 1 条 + 上轮未修复 0 条')
    expect(wrapper.get('.feedback-list').text()).toContain('需要调整灯光')
    expect(wrapper.get('.feedback-list').text()).not.toContain('已修复构图')
    await wrapper.get('#tab-history').trigger('click')
    expect(wrapper.get('.feedback-list').text()).toContain('已修复构图')
    await wrapper.findAll('.feedback-file')[0].trigger('click')
    expect(wrapper.get('.feedback-list').text()).toContain('该文件暂无历史记录')
    expect(wrapper.get('.feedback-file.active').text()).toContain('无待修改问题')
    wrapper.unmount()
  })

  it('当前导航只含本轮文件，上一轮意见通过抽屉查看原始文件', async () => {
    getVersionDetail.mockImplementation(id => Promise.resolve(detail(id, 31, { candidates: [
      { candidateId: id * 100 + 1, candidateNumber: `V00${id}_01`, files: [{ fileId: `file-${id}` }] }
    ] })))
    getTaskIssues.mockResolvedValueOnce({ data: [{ issueId: 51, originVersionId: 1, originCandidateId: 101, originVersionNumber: 'V001', pendingVersionId: 2, status: 'open', content: '遗留问题' }] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    expect(wrapper.get('.version-tabs > .el-tabs__header .is-active').text()).toContain('V002')
    expect(wrapper.findAll('.feedback-file')).toHaveLength(1)
    expect(wrapper.get('.opinion-tabs > .el-tabs__header .is-active').text()).toContain('上轮未修复')
    expect(wrapper.get('.previous-issues__list > .el-tabs__header .is-active').text()).toContain('V001_01（1）')
    expect(wrapper.get('.feedback-file.active').text()).toContain('V002_01')
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version').versionId).toBe(2)
    await wrapper.get('.previous-issues .feedback-item__select').trigger('click')
    await flushPromises()
    const drawer = wrapper.findComponent({ name: 'ElDrawer' })
    expect(drawer.props('modelValue')).toBe(true)
    expect(drawer.findComponent({ name: 'ReviewMediaWorkspace' }).props('version')).toMatchObject({ versionId: 1, candidateId: 101, files: [{ fileId: 'file-1' }] })
    drawer.vm.$emit('close')
    await flushPromises()
    expect(wrapper.get('.feedback-file.active').text()).toContain('V002_01')
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version').versionId).toBe(2)
    wrapper.unmount()
  })

  it('关闭抽屉后忽略迟到的历史来源响应', async () => {
    let resolveSource
    getVersionDetail.mockImplementation(id => id === 1
      ? new Promise(resolve => { resolveSource = resolve })
      : Promise.resolve(detail(2, 31, { candidates: [{ candidateId: 201, candidateNumber: 'V002_01', files: [] }] })))
    getTaskIssues.mockResolvedValueOnce({ data: [{ issueId: 51, originVersionId: 1, originCandidateId: 101, originVersionNumber: 'V001', pendingVersionId: 2, status: 'open', content: '遗留问题' }] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    await wrapper.get('.previous-issues .feedback-item__select').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'ElDrawer' }).vm.$emit('close')
    await flushPromises()
    resolveSource(detail(1, 31, { candidates: [{ candidateId: 101, candidateNumber: 'V001_01', files: [] }] }))
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version')).toMatchObject({ versionId: 2, candidateId: 201 })
    expect(wrapper.get('.feedback-file.active').text()).toContain('V002_01')
    expect(wrapper.get('.feedback-list').text()).toContain('暂无待处理意见')
    wrapper.unmount()
  })

  it.each([
    [[], '待审核'],
    [[{ checkedVersionId: 2, result: 'still_present' }], '仍需修改'],
    [[{ checkedVersionId: 2, result: 'resolved' }], '已修复']
  ])('返修响应按本轮实际审核记录显示状态 %j', async (verifications, expected) => {
    getTaskIssues.mockResolvedValueOnce({ data: [{ issueId: 51, originVersionId: 1, originCandidateId: 101, originVersionNumber: 'V001', pendingVersionId: 1, pendingVersionNumber: 'V001', status: 'open', content: '调整亮度', responses: [{ versionId: 2, versionNumber: 'V002', responseText: '已处理' }], verifications }] })
    const wrapper = mount(VersionHistoryPanel, { ...mountOptions, props: { taskId: 31, canList: true, canQuery: true, canListNotes: true } })
    await flushPromises()
    expect(wrapper.get('.feedback-item__heading').text()).toContain(expected)
    expect(wrapper.get('.feedback-list').text()).not.toContain('已处理但未通过')
    if (!verifications.length) expect(wrapper.get('.previous-issues h4').text()).toContain('1 条待审核')
    wrapper.unmount()
  })

  it('窄屏回到普通文档流，避免吸附内容遮挡详情', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 800 })
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      attachTo: document.body,
      props: { taskId: 31, canList: true, canQuery: true }
    })
    await flushPromises()

    expect(wrapper.findAllComponents(ElAffix)).toHaveLength(0)
    expect(wrapper.find('.version-tabs').exists()).toBe(true)
    wrapper.unmount()
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
    expect(wrapper.find('.version-tabs').text()).toContain('曲占锋')
    expect(wrapper.find('.version-tabs').text()).not.toContain('QZF')
    expect(wrapper.text()).toContain('自动审核 V2')
    const statusTags = wrapper.findAllComponents(ElTag).filter(tag => tag.text() === '待审核')
    expect(statusTags.length).toBeGreaterThanOrEqual(2)
    statusTags.forEach(tag => expect(tag.props('type')).toBe('warning'))
    expect(wrapper.find('.version-tabs em').exists()).toBe(false)

    await wrapper.get('.version-tabs > .el-tabs__header #tab-1').trigger('click')
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
