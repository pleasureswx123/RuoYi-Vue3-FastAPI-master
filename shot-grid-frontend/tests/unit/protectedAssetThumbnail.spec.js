import { ElIcon, ElImage } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadAssetThumbnail } from '@/api/shot-grid/assets'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'

vi.mock('@/api/shot-grid/assets', () => ({ downloadAssetThumbnail: vi.fn() }))

describe('资产受保护缩略图', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:asset-thumbnail') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  })

  it('通过鉴权 Blob 下载并在切换/卸载时回收对象 URL', async () => {
    downloadAssetThumbnail.mockResolvedValue(new Blob(['image']))
    const first = { url: '/shot-grid/versions/1/files/file-1/download' }
    const second = { url: '/shot-grid/versions/2/files/file-2/download' }
    const wrapper = mount(ProtectedAssetThumbnail, { props: { thumbnail: first }, global: { components: { ElIcon } } })
    await flushPromises()
    expect(wrapper.find('img').attributes('src')).toBe('blob:asset-thumbnail')
    expect(wrapper.findComponent(ElImage).props()).toMatchObject({
      fit: 'contain',
      previewSrcList: ['blob:asset-thumbnail'],
      previewTeleported: true,
      hideOnClickModal: true
    })
    expect(downloadAssetThumbnail).toHaveBeenCalledWith(first.url, expect.objectContaining({ signal: expect.any(AbortSignal) }))

    await wrapper.setProps({ thumbnail: second })
    await flushPromises()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:asset-thumbnail')
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  })

  it('403 显示无权访问且不回退公开地址', async () => {
    downloadAssetThumbnail.mockRejectedValue({ httpStatus: 403 })
    const wrapper = mount(ProtectedAssetThumbnail, {
      props: { thumbnail: { url: '/shot-grid/versions/1/files/file-1/download' } },
      global: { components: { ElIcon } }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('缩略图无权访问')
    expect(wrapper.find('img').exists()).toBe(false)
    wrapper.unmount()
  })
})
