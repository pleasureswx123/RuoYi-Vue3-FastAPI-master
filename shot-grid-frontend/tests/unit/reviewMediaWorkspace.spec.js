import { ElAlert, ElButton, ElIcon, ElMessage, ElMessageBox, ElOption, ElSelect, ElSkeleton, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createVersionPlaybackTicket,
  downloadProtectedVersionFile,
  getTaskVersions,
  getVersionDetail,
  resolvePlaybackUrl
} from '@/api/shot-grid/versions'
import ReviewMediaWorkspace from '@/views/review/components/ReviewMediaWorkspace.vue'

vi.mock('@/api/shot-grid/versions', () => ({
  createVersionPlaybackTicket: vi.fn(),
  downloadProtectedVersionFile: vi.fn(),
  getTaskVersions: vi.fn(),
  getVersionDetail: vi.fn(),
  resolvePlaybackUrl: vi.fn(url => `/dev-api${url}`)
}))

const file = {
  fileId: '5ed39e04-2f29-45ab-a58c-4f8168f5131a',
  originalName: 'review.png',
  businessFileName: 'LCFR_asset_V003.png',
  role: 'review_media',
  isPrimary: true,
  contentType: 'image/png',
  fileSize: 2048
}
const version = { versionId: 33, taskId: 21, versionNumber: 'V003', changelog: '当前版本', files: [file] }
const components = { ElAlert, ElButton, ElIcon, ElOption, ElSelect, ElSkeleton, ElTag }

describe('审核媒体工作区', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:review-media') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    downloadProtectedVersionFile.mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
    createVersionPlaybackTicket.mockResolvedValue({ data: { playbackUrl: '/shot-grid/playback/ticket/video' } })
    getTaskVersions.mockResolvedValue({ rows: [{ versionId: 32, taskId: 21, versionNumber: 'V002', changelog: '上一版本' }] })
    getVersionDetail.mockResolvedValue({ data: { ...version, versionId: 32, versionNumber: 'V002' } })
  })

  it('鉴权加载主审核图片并生成归一化点批注', async () => {
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version, canDownload: true, canCompare: true, canAnnotate: true },
      global: { components }
    })
    await flushPromises()

    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(33, file.fileId, { signal: expect.any(AbortSignal) })
    await wrapper.findAll('button').find(button => button.text().includes('标注此画面')).trigger('click')
    await wrapper.findAll('button').find(button => button.text().trim() === '点').trigger('click')
    const layer = wrapper.find('.annotation-layer')
    layer.element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 })
    await layer.trigger('pointerdown', { clientX: 50, clientY: 25, pointerId: 1 })
    await layer.trigger('pointerup', { clientX: 60, clientY: 40, pointerId: 1 })

    const payload = wrapper.emitted('annotations-change').at(-1)[0]
    expect(payload).toMatchObject({
      schemaVersion: 1,
      items: [{ type: 'point', points: [{ x: 0.3, y: 0.4 }] }]
    })

    expect(wrapper.text()).toContain('退出标注')
    wrapper.vm.clearDraft()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('标注此画面')
    expect(layer.attributes('data-active')).toBe('false')
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:review-media')
  })

  it('选择历史版本后通过鉴权接口加载只读 A/B 对比媒体', async () => {
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version, canDownload: true, canCompare: true },
      global: { components }
    })
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('与上一版对比')).trigger('click')
    await flushPromises()

    expect(getVersionDetail).toHaveBeenCalledWith(32, { signal: expect.any(AbortSignal) })
    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(32, file.fileId, { signal: expect.any(AbortSignal) })
    expect(wrapper.text()).toContain('历史版 · V002')
    const recordAction = wrapper.find('.media-columns > .record-action')
    expect(recordAction.classes()).toContain('is-compare-only')
    expect(recordAction.find('.record-action__summary').text()).toContain('当前仅支持查看历史版本')
    wrapper.unmount()
  })

  it('视频通过短期票据 URL 交给原生播放器发起 Range 请求', async () => {
    const videoFile = { ...file, originalName: 'review.mp4', contentType: 'video/mp4' }
    const videoVersion = { ...version, files: [videoFile] }
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version: videoVersion, canDownload: true },
      global: { components }
    })
    await flushPromises()

    expect(createVersionPlaybackTicket).toHaveBeenCalledWith(33, file.fileId, {
      signal: expect.any(AbortSignal)
    })
    expect(resolvePlaybackUrl).toHaveBeenCalledWith('/shot-grid/playback/ticket/video')
    expect(downloadProtectedVersionFile).not.toHaveBeenCalled()
    expect(wrapper.find('video').attributes('src')).toBe('/dev-api/shot-grid/playback/ticket/video')

    const videoElement = wrapper.find('video').element
    videoElement.pause = vi.fn()
    videoElement.currentTime = 4
    wrapper.element.scrollIntoView = vi.fn()
    wrapper.vm.seekToDraft(2000)
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(videoElement.currentTime).toBe(2)
    expect(videoElement.pause).toHaveBeenCalled()
    expect(wrapper.element.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
    expect(wrapper.find('.media-stage').classes()).toContain('is-note-focus')

    const warning = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
    await wrapper.setProps({ draftAnnotationCount: 1 })
    videoElement.pause.mockClear()
    await wrapper.find('video').trigger('play')

    expect(videoElement.pause).toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith('当前画面标注尚未保存，请先保存问题或清空草稿后再继续播放')
    expect(wrapper.text()).toContain('标注未保存，保存或清空后才能继续播放')
    wrapper.unmount()
  })

  it('查看已保存意见时播放会先退出定位并继续播放', async () => {
    const videoFile = { ...file, originalName: 'review.mp4', contentType: 'video/mp4' }
    const selectedNote = {
      noteId: 101,
      content: '这里有点模糊',
      mediaTimeMs: 5000,
      originVersionId: version.versionId,
      annotations: {
        schemaVersion: 1,
        sourceWidth: 1920,
        sourceHeight: 1080,
        items: [{ id: 'saved-note', type: 'point', color: '#ffb657', strokeWidth: 0.004, points: [{ x: 0.3, y: 0.4 }] }]
      }
    }
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version: { ...version, files: [videoFile] }, selectedNote, canDownload: true },
      global: { components }
    })
    await flushPromises()

    const videoElement = wrapper.find('video').element
    videoElement.pause = vi.fn()
    await wrapper.find('video').trigger('play')

    expect(wrapper.emitted('clear-note-focus')).toHaveLength(1)
    expect(videoElement.pause).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('优先加载网页代理媒体并在界面标识', async () => {
    const original = { ...file, originalName: 'review.mov', contentType: 'video/quicktime' }
    const proxy = {
      ...file,
      fileId: '7ed39e04-2f29-45ab-a58c-4f8168f5131b',
      originalName: 'review-proxy.mp4',
      role: 'proxy_media',
      isPrimary: false,
      contentType: 'video/mp4'
    }
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version: { ...version, files: [original, proxy] }, canDownload: true },
      global: { components }
    })
    await flushPromises()

    expect(createVersionPlaybackTicket).toHaveBeenCalledWith(33, proxy.fileId, {
      signal: expect.any(AbortSignal)
    })
    expect(wrapper.text()).toContain('流畅预览')
    const proxyTag = wrapper.findAllComponents(ElTag).find(tag => tag.text() === '流畅预览')
    expect(proxyTag.props()).toMatchObject({ type: 'success', effect: 'plain', size: 'small', round: true })
    wrapper.unmount()
  })

  it('拖拽生成带归一化起止点的箭头批注', async () => {
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version, canDownload: true, canAnnotate: true },
      global: { components }
    })
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('标注此画面')).trigger('click')
    await wrapper.findAll('button').find(button => button.text().includes('箭头')).trigger('click')
    const layer = wrapper.find('.annotation-layer')
    layer.element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 })
    await layer.trigger('pointerdown', { clientX: 20, clientY: 20, pointerId: 2 })
    await layer.trigger('pointerup', { clientX: 160, clientY: 70, pointerId: 2 })

    const payload = wrapper.emitted('annotations-change').at(-1)[0]
    expect(payload.items[0]).toMatchObject({
      type: 'arrow',
      points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }]
    })
    expect(wrapper.find('.annotation-arrow').exists()).toBe(true)
    wrapper.unmount()
  })

  it('点击画面后通过 Element Plus 输入框创建纯文本批注', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '  降低这里的高光  ' })
    const wrapper = mount(ReviewMediaWorkspace, {
      props: { version, canDownload: true, canAnnotate: true },
      global: { components }
    })
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('标注此画面')).trigger('click')
    await wrapper.findAll('button').find(button => button.text().includes('文字')).trigger('click')
    const layer = wrapper.find('.annotation-layer')
    layer.element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 })
    await layer.trigger('pointerdown', { clientX: 80, clientY: 30, pointerId: 3 })
    await layer.trigger('pointerup', { clientX: 80, clientY: 30, pointerId: 3 })
    await flushPromises()

    expect(ElMessageBox.prompt).toHaveBeenCalledWith(
      expect.any(String),
      '添加文字批注',
      expect.objectContaining({ inputType: 'textarea' })
    )
    const payload = wrapper.emitted('annotations-change').at(-1)[0]
    expect(payload.items[0]).toMatchObject({
      type: 'text',
      text: '降低这里的高光',
      points: [{ x: 0.4, y: 0.3 }]
    })
    expect(wrapper.find('.annotation-text').text()).toBe('降低这里的高光')
    wrapper.unmount()
  })
})
