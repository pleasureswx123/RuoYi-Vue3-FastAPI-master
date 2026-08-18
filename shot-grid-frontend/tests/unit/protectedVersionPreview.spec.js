import { ElButton, ElIcon, ElImage, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createVersionPlaybackTicket,
  downloadProtectedVersionFile,
  resolvePlaybackUrl
} from '@/api/shot-grid/versions'
import ProtectedVersionPreview from '@/components/version/ProtectedVersionPreview.vue'

vi.mock('@/api/shot-grid/versions', () => ({
  createVersionPlaybackTicket: vi.fn(),
  downloadProtectedVersionFile: vi.fn(),
  resolvePlaybackUrl: vi.fn(value => `/dev-api${value}`)
}))

const imageFileId = '550e8400-e29b-41d4-a716-446655440000'
const videoFileId = '550e8400-e29b-41d4-a716-446655440001'
const mountOptions = { global: { components: { ElButton, ElIcon, ElImage, ElTag } } }

function version(file, overrides = {}) {
  return {
    versionId: 7,
    versionNumber: 'V001',
    files: [file],
    ...overrides
  }
}

describe('受保护版本预览', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:version-preview') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    downloadProtectedVersionFile.mockResolvedValue(new Blob(['image']))
    createVersionPlaybackTicket.mockResolvedValue({ data: { playbackUrl: '/shot-grid/playback/ticket' } })
  })

  it('通过受保护文件接口直接预览主审核图片并在卸载时释放 URL', async () => {
    const file = { fileId: imageFileId, role: 'review_media', isPrimary: true, contentType: 'image/jpeg', businessFileName: 'V001.jpg' }
    const wrapper = mount(ProtectedVersionPreview, { ...mountOptions, props: { version: version(file), canPreview: true } })
    await flushPromises()

    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(7, imageFileId, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.findComponent(ElImage).props('previewSrcList')).toEqual(['blob:version-preview'])
    expect(wrapper.find('img').attributes('src')).toBe('blob:version-preview')
    expect(wrapper.findComponent(ElTag).props()).toMatchObject({ type: 'info', effect: 'dark', size: 'small', round: true })
    expect(wrapper.findComponent(ElTag).text()).toBe('图片')
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:version-preview')
  })

  it('视频使用短期播放票据交给原生播放器加载', async () => {
    const file = { fileId: videoFileId, role: 'review_media', isPrimary: true, contentType: 'video/mp4', businessFileName: 'V001.mp4' }
    const wrapper = mount(ProtectedVersionPreview, { ...mountOptions, props: { version: version(file), canPreview: true } })
    await flushPromises()

    expect(createVersionPlaybackTicket).toHaveBeenCalledWith(7, videoFileId, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(resolvePlaybackUrl).toHaveBeenCalledWith('/shot-grid/playback/ticket')
    expect(wrapper.find('video').attributes('src')).toBe('/dev-api/shot-grid/playback/ticket')
    expect(wrapper.findComponent(ElTag).text()).toBe('视频')
    wrapper.unmount()
  })

  it('无文件权限时显示权限状态且不请求媒体', async () => {
    const file = { fileId: imageFileId, role: 'review_media', isPrimary: true, contentType: 'image/jpeg' }
    const wrapper = mount(ProtectedVersionPreview, { ...mountOptions, props: { version: version(file), canPreview: false } })
    await flushPromises()

    expect(wrapper.text()).toContain('没有版本文件预览权限')
    expect(downloadProtectedVersionFile).not.toHaveBeenCalled()
    expect(createVersionPlaybackTicket).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('切换版本时取消旧请求并拒绝迟到文件覆盖新预览', async () => {
    let resolveOld
    downloadProtectedVersionFile.mockImplementationOnce((_versionId, _fileId, options) => new Promise(resolve => {
      resolveOld = resolve
      expect(options.signal.aborted).toBe(false)
    })).mockResolvedValueOnce(new Blob(['new']))
    const first = { fileId: imageFileId, role: 'review_media', isPrimary: true, contentType: 'image/jpeg' }
    const second = { fileId: videoFileId, role: 'review_media', isPrimary: true, contentType: 'image/png' }
    const wrapper = mount(ProtectedVersionPreview, { ...mountOptions, props: { version: version(first), canPreview: true } })
    const oldSignal = downloadProtectedVersionFile.mock.calls[0][2].signal
    await wrapper.setProps({ version: version(second, { versionId: 8, versionNumber: 'V002' }) })
    await flushPromises()

    expect(oldSignal.aborted).toBe(true)
    resolveOld(new Blob(['late']))
    await flushPromises()
    expect(wrapper.find('img').attributes('src')).toBe('blob:version-preview')
    expect(downloadProtectedVersionFile).toHaveBeenLastCalledWith(8, videoFileId, expect.any(Object))
    wrapper.unmount()
  })
})
