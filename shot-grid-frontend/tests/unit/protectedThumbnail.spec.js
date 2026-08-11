import { ElIcon } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadProtectedThumbnail } from '@/api/shot-grid/shots'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'

vi.mock('@/api/shot-grid/shots', () => ({ downloadProtectedThumbnail: vi.fn() }))

describe('受保护镜头缩略图', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:shot-thumbnail') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  })

  it('通过统一请求层取得 blob，并在卸载时中止请求和释放 object URL', async () => {
    downloadProtectedThumbnail.mockResolvedValue(new Blob(['image'], { type: 'image/jpeg' }))
    const thumbnail = { fileId: 'file-1', url: '/shot-grid/versions/31/files/file-1/download' }
    const wrapper = mount(ProtectedThumbnail, {
      props: { thumbnail, alt: 'S001 缩略图' },
      global: { components: { ElIcon } }
    })
    await flushPromises()

    const options = downloadProtectedThumbnail.mock.calls[0][1]
    expect(options.signal.aborted).toBe(false)
    expect(wrapper.find('img').attributes()).toMatchObject({ src: 'blob:shot-thumbnail', alt: 'S001 缩略图' })
    wrapper.unmount()
    expect(options.signal.aborted).toBe(true)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:shot-thumbnail')
  })

  it('403 只显示安全占位，不把受保护 API URL交给 img', async () => {
    downloadProtectedThumbnail.mockRejectedValue({ httpStatus: 403, message: '无权访问' })
    const wrapper = mount(ProtectedThumbnail, {
      props: { thumbnail: { fileId: 'file-2', url: '/shot-grid/versions/31/files/file-2/download' } },
      global: { components: { ElIcon } }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('缩略图无权访问')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('/shot-grid/versions/31/files/file-2/download')
    wrapper.unmount()
  })
})
