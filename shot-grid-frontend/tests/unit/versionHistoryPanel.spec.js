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
        { issueId: 51, originVersionId: 2, pendingVersionId: 2, status: 'open', content: '主体亮度偏低', responses: [], verifications: [] },
        { issueId: 52, originVersionId: 2, pendingVersionId: 2, status: 'open', content: '运动节奏过快', responses: [], verifications: [] }
      ]
    })
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      props: { taskId: 31, canList: true, canQuery: true, canListNotes: true }
    })
    await flushPromises()

    const decision = wrapper.get('.feedback-decision')
    expect(decision.classes()).toContain('is-reject')
    expect(decision.text()).toContain('已退回修改')
    expect(decision.text()).toContain('需要继续修改')
    expect(decision.text()).toContain('请根据下方 2 条待处理问题逐项修改')
    expect(decision.text()).toContain('审核人 刘远辉')
    expect(decision.attributes('role')).not.toBe('alert')
    expect(wrapper.find('.feedback-decision.el-alert').exists()).toBe(false)
    wrapper.unmount()
  })

  it('在对应问题卡片展示参考附件，下载与图片预览不触发问题选择', async () => {
    const files = [
      { fileId: '11111111-1111-4111-8111-111111111111', originalName: '灯光参考.png', contentType: 'image/png', fileSize: 2048, downloadUrl: '/shot-grid/issues/51/reference-files/11111111-1111-4111-8111-111111111111/download' },
      { fileId: '22222222-2222-4222-8222-222222222222', originalName: '修改要求.pdf', contentType: 'application/pdf', fileSize: 4096, downloadUrl: '/shot-grid/issues/51/reference-files/22222222-2222-4222-8222-222222222222/download' }
    ]
    getTaskIssues.mockResolvedValueOnce({
      data: [
        { issueId: 50, originVersionId: 2, originVersionNumber: 'V002', pendingVersionId: 2, status: 'open', content: '另一条待处理问题', referenceFiles: [], responses: [], verifications: [] },
        { issueId: 51, originVersionId: 2, originVersionNumber: 'V002', pendingVersionId: 2, status: 'open', content: '请参考附件调整灯光', referenceFiles: files, responses: [], verifications: [] }
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

  it('桌面端使用 Element Plus Affix 固定版本轨道与反馈列表', async () => {
    getTaskIssues.mockResolvedValueOnce({
      data: [{
        issueId: 51,
        originVersionId: 2,
        originVersionNumber: 'V002',
        pendingVersionId: 2,
        pendingVersionNumber: 'V002',
        status: 'open',
        content: '主体亮度偏低',
        mediaTimeMs: 1200,
        annotations: null,
        responses: [],
        verifications: [],
        createTime: '2026-08-11T12:30:00'
      }]
    })
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      attachTo: document.body,
      props: { taskId: 31, canList: true, canQuery: true, canListNotes: true }
    })
    await flushPromises()

    const affixes = wrapper.findAllComponents(ElAffix)
    expect(affixes).toHaveLength(2)
    expect(affixes[0].props()).toMatchObject({ appendTo: 'body', offset: 92, target: '#version-history-panel-31', teleported: true })
    expect(affixes[1].props()).toMatchObject({ appendTo: 'body', offset: 92, target: '#version-feedback-panel-31', teleported: true })
    expect(wrapper.find('.version-rail-affix .version-rail').exists()).toBe(true)
    expect(wrapper.find('.feedback-list-affix .feedback-list').exists()).toBe(true)
    wrapper.unmount()
  })

  it('页面滚动越过轨道后进入 Element Plus fixed 状态', async () => {
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      attachTo: document.body,
      props: { taskId: 31, canList: true, canQuery: true }
    })
    await flushPromises()

    const affix = wrapper.findComponent(ElAffix)
    const target = wrapper.find('#version-history-panel-31').element
    affix.element.getBoundingClientRect = () => ({
      top: 40,
      bottom: 440,
      left: 120,
      right: 360,
      width: 240,
      height: 400,
      x: 120,
      y: 40,
      toJSON: () => ({})
    })
    target.getBoundingClientRect = () => ({
      top: -600,
      bottom: 1600,
      left: 100,
      right: 1180,
      width: 1080,
      height: 2200,
      x: 100,
      y: -600,
      toJSON: () => ({})
    })
    window.dispatchEvent(new Event('scroll'))
    await flushPromises()

    expect(document.querySelector('.el-affix--fixed .version-rail')).not.toBeNull()
    wrapper.unmount()
  })

  it('侧栏改变面板宽度后重新测量两块已吸顶卡片的位置和宽度', async () => {
    const observers = []
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback) {
        this.callback = callback
        this.targets = new Set()
        observers.push(this)
      }
      observe(target) { this.targets.add(target) }
      unobserve(target) { this.targets.delete(target) }
      disconnect() { this.targets.clear() }
    })
    getTaskIssues.mockResolvedValueOnce({
      data: [{ issueId: 51, originVersionId: 2, pendingVersionId: 2, status: 'open', content: '检查画面', responses: [], verifications: [] }]
    })
    const wrapper = mount(VersionHistoryPanel, {
      ...mountOptions,
      attachTo: document.body,
      props: { taskId: 31, canList: true, canQuery: true, canListNotes: true }
    })
    try {
      await flushPromises()
      let collapsed = false
      const rect = (left, top, width, height) => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) })
      const history = wrapper.get('.version-history-affix-target').element
      history.getBoundingClientRect = () => rect(collapsed ? 76 : 244, -600, collapsed ? 1200 : 1032, 2200)
      wrapper.get('.version-feedback-affix-target').element.getBoundingClientRect = () => rect(650, -100, 800, 1400)
      const affixes = wrapper.findAllComponents(ElAffix)
      affixes[0].element.getBoundingClientRect = () => rect(collapsed ? 100 : 268, 40, collapsed ? 320 : 280, 200)
      affixes[1].element.getBoundingClientRect = () => rect(collapsed ? 1000 : 900, 40, 300, 240)
      window.dispatchEvent(new Event('scroll'))
      await flushPromises()
      const rail = document.querySelector('.version-rail').closest('.el-affix--fixed')
      const feedback = document.querySelector('.feedback-list').closest('.el-affix--fixed')
      expect(rail.style.left).toBe('268px')
      expect(feedback.style.left).toBe('900px')

      collapsed = true
      // 侧栏收起只改变容器宽度，不会触发 window.resize 或 scroll。
      observers.filter(observer => observer.targets.has(history)).forEach(observer => {
        observer.callback([{ target: history, contentRect: history.getBoundingClientRect() }])
      })
      await flushPromises()
      expect(rail.style.left).toBe('100px')
      expect(rail.style.width).toBe('320px')
      expect(feedback.style.left).toBe('1000px')
      expect(feedback.style.width).toBe('300px')
    } finally {
      wrapper.unmount()
      vi.unstubAllGlobals()
    }
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
    expect(wrapper.find('.version-rail').exists()).toBe(true)
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
    expect(wrapper.find('.version-rail').text()).toContain('曲占锋')
    expect(wrapper.find('.version-rail').text()).not.toContain('QZF')
    expect(wrapper.text()).toContain('自动审核 V2')
    const statusTags = wrapper.findAllComponents(ElTag).filter(tag => tag.text() === '待审核')
    expect(statusTags.length).toBeGreaterThanOrEqual(2)
    statusTags.forEach(tag => expect(tag.props('type')).toBe('warning'))
    expect(wrapper.find('.version-rail em').exists()).toBe(false)

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
