import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElAlert, ElButton, ElDialog, ElMessageBox, ElTabPane, ElTabs } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NasOpenButton from '@/components/NasOpenButton.vue'
import ShotResultsPanel from '@/views/shot/components/ShotResultsPanel.vue'
import { useSessionStore } from '@/store/modules/session'
import { getShotDetail } from '@/api/shot-grid/shots'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import { getVersionReviewContext } from '@/api/shot-grid/reviews'

vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/assets', () => ({ getAssetDetail: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
vi.mock('@/api/shot-grid/versions', () => ({ getTaskVersions: vi.fn(), getVersionDetail: vi.fn() }))
vi.mock('@/api/shot-grid/reviews', () => ({ getTaskIssues: vi.fn(), getVersionReviewContext: vi.fn() }))
const realtime = vi.hoisted(() => ({ refresh: null }))
vi.mock('@/composables/useVersionRealtime', () => ({ useVersionRealtime: (_id, callback) => { realtime.refresh = callback } }))
const stubs = {
  ProtectedVersionPreview: { name: 'ProtectedVersionPreview', props: ['version', 'canPreview'], template: '<div data-testid="protected-preview" />' },
  ReviewCandidateThumbnail: true, ReviewReferenceFiles: { name: 'ReviewReferenceFiles', props: ['files'], template: '<div />' },
  ShotFeedbackPanel: { name: 'ShotFeedbackPanel', props: ['projectId', 'taskId', 'versionId', 'canRead', 'canComment'], data: () => ({ dirty: false, sending: false }), template: '<div />' }
}
const shot = { projectId: 8, shotId: 41, taskId: 71, shotCode: '0001', episodeCode: 'EP001', sceneCode: '001', status: 'in_progress', description: 'AI 生成的雨夜街道', referenceFiles: [] }
const task = { taskId: 71, taskKind: 'shot_video', taskStatus: 'in_progress', project: { projectId: 8 }, target: { targetType: 'shot', shotId: 41 }, allowedActions: ['version.add'], latestVersion: { versionNo: 2 }, versionCount: 2, assignee: { userId: 7, userName: '制作人甲' } }
const versionRow = id => ({ versionId: id, taskId: 71, projectId: 8, versionNo: id, versionNumber: `V00${id}`, versionStatus: 'pending_review', submittedTime: '2026-10-29T10:00:00', submitterName: '制作人甲', changelog: `第 ${id} 轮成果` })
const versionDetail = id => ({ ...versionRow(id), selectedCandidateId: id * 10 + 2, candidates: [1, 2].map(n => ({ candidateId: id * 10 + n, candidateNumber: `V00${id}_0${n}`, isSelected: n === 2, files: [{ fileId: `file-${id}-${n}`, role: 'review_media', contentType: 'video/mp4' }] })) })
async function mountPanel(permissions = ['*:*:*'], props = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().permissions = permissions
  const wrapper = mount(ShotResultsPanel, { props: { projectId: 8, shotId: 41, ...props }, global: { plugins: [pinia], stubs } })
  await flushPromises()
  return wrapper
}

describe('镜头三页签侧栏', () => {
  afterEach(() => vi.unstubAllEnvs())
  beforeEach(() => {
    vi.stubEnv('DEV', false)
    getShotDetail.mockResolvedValue({ data: { ...shot } })
    getTaskDetail.mockResolvedValue({ data: { ...task } })
    getTaskVersions.mockResolvedValue({ rows: [versionRow(2), versionRow(1)], total: 2, hasNext: false })
    getVersionDetail.mockImplementation(id => Promise.resolve({ data: versionDetail(id) }))
  })
  it.each(['pending', 'publishing', 'published', 'failed'])('定稿默认聚焦选中候选并按真实归档状态启用入口：%s', async state => {
    const approvedVersion = { versionId: 1, versionNo: 1, versionStatus: 'final', deliveryStatus: state, approvedTime: '2026-10-30T09:00:00' }
    getShotDetail.mockResolvedValue({ data: { ...shot, status: 'completed', approvedVersion } })
    getVersionDetail.mockImplementation(id => Promise.resolve({ data: { ...versionDetail(id), versionStatus: 'final', finalDelivery: { versionId: id, candidateId: id * 10 + 2, deliveryStatus: state, businessFileName: 'result.mp4', approvedTime: approvedVersion.approvedTime } } }))
    const wrapper = await mountPanel()
    try {
      expect(wrapper.text()).toContain('通过日期：2026/10/30')
      expect(wrapper.find('[aria-label="查看成果 V001"]').exists()).toBe(true)
      expect(wrapper.find('[aria-label="查看成果 V002"]').exists()).toBe(false)
      expect(wrapper.find('[aria-label="预览候选 V001_01"]').exists()).toBe(false)
      expect(wrapper.find('[aria-label="预览候选 V001_02"]').exists()).toBe(true)
      const folder = wrapper.findAllComponents(ElButton).find(button => button.text().startsWith('打开定稿文件夹'))
      expect(folder.props('disabled')).toBe(state !== 'published')
      await wrapper.findAllComponents(ElButton).find(button => button.text() === '历史版本').trigger('click')
      expect(wrapper.find('[aria-label="查看成果 V002"]').exists()).toBe(true)
    } finally { wrapper.unmount() }
  })
  it('上次定稿不在首批版本时仍鉴权加载，反馈状态及当前最新版本保持独立', async () => {
    getShotDetail.mockResolvedValue({ data: { ...shot, status: 'revision', approvedVersion: { versionId: 1, versionNo: 1, versionStatus: 'rejected', deliveryStatus: 'published' } } })
    getTaskVersions.mockResolvedValue({ rows: [versionRow(2)], hasNext: true })
    const wrapper = await mountPanel()
    try {
      expect(wrapper.text()).toContain('修改中 · 上次定稿 V001')
      expect(wrapper.find('[aria-label="查看成果 V001"]').exists()).toBe(true)
      expect(wrapper.find('[aria-label="查看成果 V002"]').exists()).toBe(false)
    } finally { wrapper.unmount() }
  })
  it('首批之外的定稿详情失败显示重试，不当成空成果', async () => {
    getShotDetail.mockResolvedValue({ data: { ...shot, approvedVersion: { versionId: 1, versionNo: 1, versionStatus: 'final' } } })
    getTaskVersions.mockResolvedValue({ rows: [versionRow(2)], hasNext: true })
    getVersionDetail.mockRejectedValue(new Error('定稿读取失败'))
    const wrapper = await mountPanel()
    try { expect(wrapper.text()).toContain('定稿读取失败'); expect(wrapper.text()).toContain('重试') }
    finally { wrapper.unmount() }
  })
  function assetFixture() {
    const item = { assetItemId: 51, assetId: 31, projectId: 8, productionItem: '主视角', description: '分项参考', referenceFiles: [{ fileId: 'ref', originalName: '参考.png' }], task: { taskId: 71 }, allowedActions: ['task.review'] }
    getAssetDetail.mockResolvedValue({ data: { assetId: 31, projectId: 8, assetName: '客厅', description: '整体参考', items: [item] } })
    getTaskDetail.mockResolvedValue({ data: { ...task, taskKind: 'asset_image', target: { targetType: 'asset_item', assetId: 31, assetItemId: 51 }, latestVersion: { versionId: 2 } } })
    return { assetId: 31, assetItemId: 51, shotId: 0 }
  }
  it('资产分项复用三页签，提交与反馈只关联当前分项', async () => {
    const wrapper = await mountPanel(['*:*:*'], assetFixture())
    try {
      expect(getShotDetail).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('客厅')
      expect(wrapper.text()).toContain('主视角')
      expect(wrapper.text()).toContain('第 2 轮成果')
      expect(wrapper.text()).toContain('2026/10/29')
      expect(wrapper.findAllComponents(ElTabPane).map(pane => pane.props('label'))).toEqual(['成果展示', '反馈说明', '制作参考', '关联资产'])
      await wrapper.findAllComponents(ElButton).find(button => button.text() === '提交成果').trigger('click')
      expect(wrapper.emitted('work')).toEqual([[71]])
      wrapper.getComponent(ElTabs).vm.$emit('update:modelValue', 'feedback'); await flushPromises()
      expect(wrapper.findComponent({ name: 'ShotFeedbackPanel' }).props()).toMatchObject({ taskId: 71, versionId: 2 })
      await wrapper.findAllComponents(ElButton).find(button => button.text() === '添加反馈').trigger('click'); await flushPromises()
      expect(wrapper.emitted('feedback')[0][0]).toMatchObject({ asset: { assetId: 31 }, item: { assetItemId: 51 }, action: 'review' })
      wrapper.getComponent(ElTabs).vm.$emit('update:modelValue', 'references'); await flushPromises()
      expect(wrapper.text()).toContain('整体参考')
      expect(wrapper.text()).toContain('分项参考')
      expect(wrapper.findComponent({ name: 'ReviewReferenceFiles' }).props('files')[0].fileId).toBe('ref')
    } finally { wrapper.unmount() }
  })
  it.each(['项目', '分项', '任务'])('资产侧栏拒绝不匹配的%s', async kind => {
    const props = assetFixture()
    if (kind === '项目') getAssetDetail.mockResolvedValueOnce({ data: { projectId: 99, assetId: 31, items: [] } })
    if (kind === '分项') props.assetItemId = 99
    if (kind === '任务') getTaskDetail.mockResolvedValueOnce({ data: { ...task, target: { targetType: 'asset_item', assetId: 99, assetItemId: 51 } } })
    const wrapper = await mountPanel(['*:*:*'], props)
    try {
      expect(wrapper.findAllComponents(ElAlert).some(alert => /归属已变化|不匹配/.test(alert.props('title')))).toBe(true)
      expect(wrapper.findAllComponents(ElButton).some(button => button.text() === '提交成果')).toBe(false)
    } finally { wrapper.unmount() }
  })
  it('切换资产分项隔离迟到版本，资产不使用镜头本地目录身份', async () => {
    vi.stubEnv('DEV', true)
    const props = assetFixture()
    let finish
    getVersionDetail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await mountPanel(['*:*:*'], props)
    try {
      const signal = getVersionDetail.mock.calls[0][1].signal
      getAssetDetail.mockResolvedValueOnce({ data: { assetId: 31, projectId: 8, items: [{ assetId: 31, assetItemId: 52, projectId: 8, productionItem: '第二分项' }] } })
      await wrapper.setProps({ assetItemId: 52 }); await flushPromises()
      finish({ data: versionDetail(2) }); await flushPromises()
      expect(signal.aborted).toBe(true)
      expect(wrapper.text()).toContain('第二分项')
      expect(wrapper.text()).not.toContain('第 2 轮成果')
      expect(wrapper.text()).not.toContain('本地模拟')
    } finally { wrapper.unmount() }
  })
  it('侧栏直接反馈只允许最新版本，旧版本保留只读查看', async () => {
    getTaskDetail.mockResolvedValue({ data: { ...task, taskStatus: 'pending_review', allowedActions: ['task.feedback'], latestVersion: { versionId: 2, versionNo: 2 } } })
    getVersionReviewContext.mockResolvedValue({ data: { currentVersion: { versionId: 2, versionStatus: 'pending_review', lockVersion: 4 } } })
    const wrapper = await mountPanel()
    try {
      wrapper.getComponent(ElTabs).vm.$emit('update:modelValue', 'feedback'); await flushPromises()
      const button = () => wrapper.findAllComponents(ElButton).find(item => item.text() === '添加反馈')
      await wrapper.find('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      expect(button().props('disabled')).toBe(true)
      await wrapper.find('[aria-label="查看成果 V002"]').trigger('click'); await flushPromises()
      await button().trigger('click'); await flushPromises()
      expect(getVersionReviewContext).toHaveBeenCalledWith(2, expect.objectContaining({ signal: expect.any(AbortSignal) }))
      expect(document.body.textContent).toContain('共同反馈（适用于全部所选镜头）')
    } finally { wrapper.unmount() }
  })
  it('只展示三个页签，成果日期和内容可见，按需预览且不出现旧操作', async () => {
    const wrapper = await mountPanel()
    try {
      expect(wrapper.findAllComponents(ElTabPane).map(item => item.props('label'))).toEqual(['成果展示', '反馈说明', '制作参考'])
      expect(wrapper.text()).toContain('第 2 轮成果')
      expect(wrapper.text()).toContain('2026/10/29')
      expect(wrapper.text()).toContain('打开所在文件夹（演示）')
      expect(wrapper.text()).not.toMatch(/文件夹帮助|提交成果|提示词/)
      expect(wrapper.findComponent({ name: 'ProtectedVersionPreview' }).exists()).toBe(false)
      await wrapper.find('[aria-label="预览候选 V002_01"]').trigger('click')
      await flushPromises()
      expect(wrapper.findComponent(ElDialog).props('modelValue')).toBe(true)
      expect(wrapper.findComponent({ name: 'ProtectedVersionPreview' }).props('version').files[0].fileId).toBe('file-2-1')
    } finally { wrapper.unmount() }
  })
  it('反馈随版本切换，未发送和正在发送的评论均有离开门禁', async () => {
    const wrapper = await mountPanel()
    try {
      wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'feedback')
      await flushPromises()
      const panel = wrapper.findComponent({ name: 'ShotFeedbackPanel' })
      expect(panel.props()).toMatchObject({ taskId: 71, versionId: 2, canComment: true })
      panel.vm.dirty = true
      const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel')
      await wrapper.find('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      expect(wrapper.findComponent({ name: 'ShotFeedbackPanel' }).props('versionId')).toBe(2)
      confirm.mockResolvedValueOnce('confirm')
      await wrapper.find('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      expect(wrapper.findComponent({ name: 'ShotFeedbackPanel' }).props('versionId')).toBe(1)
      wrapper.findComponent({ name: 'ShotFeedbackPanel' }).vm.sending = true
      expect(await wrapper.vm.$.exposed.canLeave()).toBe(false)
    } finally { wrapper.unmount() }
  })
  it('桌面端按所点候选打开目录，缺少文件编号时禁用入口', async () => {
    vi.stubGlobal('__SHOTGRID_DESKTOP__', true)
    const detail = versionDetail(2)
    detail.candidates[0].files = []
    getVersionDetail.mockResolvedValueOnce({ data: detail })
    const wrapper = await mountPanel()
    try {
      const buttons = wrapper.findAllComponents(NasOpenButton)
      expect(buttons[0].props('disabled')).toBe(true)
      expect(buttons[1].text()).toContain('在文件资源管理器中打开')
      expect(buttons[1].props()).toMatchObject({ projectId: 8, taskId: 71, versionId: 2, fileId: 'file-2-2', disabled: false })
      await wrapper.get('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      expect(wrapper.findComponent(NasOpenButton).props()).toMatchObject({ versionId: 1, fileId: 'file-1-1' })
    } finally { wrapper.unmount(); vi.unstubAllGlobals() }
  })
  it('文件夹入口只演示当前原文件位置，不触发协议；换版和无路径均不借用其他文件', async () => {
    const folder = String.raw`\\192.168.10.64\制作\项目 A\V002`
    getVersionDetail.mockImplementation(id => {
      const detail = versionDetail(id)
      if (id === 2) detail.candidates[0].files[0].nasPath = folder + '\\clip.mp4'
      return Promise.resolve({ data: detail })
    })
    const wrapper = await mountPanel()
    const clickLink = vi.spyOn(HTMLAnchorElement.prototype, 'click')
    try {
      await wrapper.get('[aria-label="打开 V002_01 所在文件夹（演示）"]').trigger('click'); await flushPromises()
      expect(document.body.textContent).toContain(folder)
      expect(document.body.textContent).toContain('不会打开文件夹或连接 NAS')
      expect(clickLink).not.toHaveBeenCalled()
      wrapper.findAllComponents(ElDialog)[1].vm.$emit('update:modelValue', false); await flushPromises()
      await wrapper.get('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      await wrapper.get('[aria-label="打开 V001_01 所在文件夹（演示）"]').trigger('click'); await flushPromises()
      expect(document.body.textContent).toContain('尚未提供原文件 NAS 路径')
      expect(document.body.textContent).not.toContain(folder)
    } finally { clickLink.mockRestore(); wrapper.unmount() }
  })
  it('预览弹窗内切换上一版本，播放器绑定新版本文件', async () => {
    const wrapper = await mountPanel()
    try {
      await wrapper.get('[aria-label="预览候选 V002_01"]').trigger('click'); await flushPromises()
      const previous = wrapper.findAllComponents(ElButton).find(button => button.text() === '上一版本')
      await previous.trigger('click'); await flushPromises()
      expect(wrapper.findComponent({ name: 'ProtectedVersionPreview' }).props('version').versionId).toBe(1)
      expect(wrapper.findComponent({ name: 'ProtectedVersionPreview' }).props('version').files[0].fileId).toBe('file-1-2')
      expect(previous.props('disabled')).toBe(true)
    } finally { wrapper.unmount() }
  })
  it('本地模拟点击使用当前镜头版本候选编号，换版本不打开上个版本的目录', async () => {
    vi.stubEnv('DEV', true)
    const links = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { links.push(this.href) })
    const wrapper = await mountPanel()
    try {
      await wrapper.get('[aria-label="打开 V002_01 所在文件夹（本地模拟）"]').trigger('click')
      expect(links).toEqual(['shotgrid-folder://demo/8/41/2/21'])
      await wrapper.get('[aria-label="查看成果 V001"]').trigger('click'); await flushPromises()
      await wrapper.get('[aria-label="打开 V001_02 所在文件夹（本地模拟）"]').trigger('click')
      expect(links[1]).toBe('shotgrid-folder://demo/8/41/1/12')
      expect(document.querySelector('a[href^="shotgrid-folder:"]')).toBeNull()
    } finally { click.mockRestore(); wrapper.unmount() }
  })
  it('制作参考仅保留文字和图片，保留原鉴权预览', async () => {
    getShotDetail.mockResolvedValueOnce({ data: { ...shot, referenceDescription: '参考光线', referenceFiles: [{ fileId: 'image', originalName: '参考.png' }, { fileId: 'other', originalName: '文件.pdf' }] } })
    const wrapper = await mountPanel()
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'references'); await flushPromises()
    expect(wrapper.text()).toContain('参考光线')
    expect(wrapper.findComponent({ name: 'ReviewReferenceFiles' }).props('files')).toEqual([{ fileId: 'image', originalName: '参考.png' }])
    wrapper.unmount()
  })
  it('没有文件权限不能预览，没有评论权限仅阅读', async () => {
    const wrapper = await mountPanel(['shotgrid:shot:query', 'shotgrid:version:list', 'shotgrid:version:query', 'shotgrid:note:list'])
    expect(wrapper.find('[aria-label="预览候选 V002_01"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[aria-label="打开 V002_01 所在文件夹（演示）"]').attributes('disabled')).toBeDefined()
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'feedback'); await flushPromises()
    expect(wrapper.findComponent({ name: 'ShotFeedbackPanel' }).props('canComment')).toBe(false)
    wrapper.unmount()
  })
  it.each(['镜头', '版本', '版本项目', '列表'])('拒绝%s跨项目或跨任务数据', async kind => {
    if (kind === '镜头') getShotDetail.mockResolvedValueOnce({ data: { ...shot, projectId: 99 } })
    if (kind === '版本') getVersionDetail.mockResolvedValueOnce({ data: { ...versionDetail(2), taskId: 99 } })
    if (kind === '版本项目') getVersionDetail.mockResolvedValueOnce({ data: { ...versionDetail(2), projectId: 99 } })
    if (kind === '列表') getTaskVersions.mockResolvedValueOnce({ rows: [{ ...versionRow(2), projectId: 99 }] })
    const wrapper = await mountPanel()
    expect(wrapper.findAllComponents(ElAlert).some(item => /不匹配|归属已变化/.test(item.props('title')))).toBe(true)
    wrapper.unmount()
  })
  it('快速切换镜头，旧请求取消且迟到版本不会进入新镜头', async () => {
    let finish
    getVersionDetail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await mountPanel()
    const signal = getVersionDetail.mock.calls[0][1].signal
    getShotDetail.mockResolvedValueOnce({ data: { ...shot, shotId: 42, taskId: null } })
    await wrapper.setProps({ shotId: 42 }); await flushPromises()
    expect(signal.aborted).toBe(true)
    finish({ data: versionDetail(2) }); await flushPromises()
    expect(wrapper.text()).toContain('还没有提交成果')
    expect(wrapper.find('[aria-label="预览候选 V002_01"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
