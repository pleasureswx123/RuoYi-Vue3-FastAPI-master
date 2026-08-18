import { ElButton, ElIcon, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'

vi.mock('@/api/shot-grid/versions', () => ({ downloadProtectedVersionFile: vi.fn() }))

const fileId = '550e8400-e29b-41d4-a716-446655440000'
const mountOptions = {
  global: {
    components: { ElButton, ElIcon, ElTag },
    stubs: { ProtectedVersionPreview: true }
  }
}

function version(versionId = 7, overrides = {}) {
  return {
    versionId,
    taskId: 31,
    versionNumber: `V00${versionId}`,
    versionStatus: 'pending_review',
    changelog: '完成第一版',
    submittedBy: 8,
    submitterName: '制作人甲',
    submittedTime: '2026-08-11T12:00:00',
    lockVersion: 0,
    aiParams: null,
    autoReviewList: { reviewListName: '自动审核 V001' },
    files: [{
      fileId,
      originalName: '原始.mov',
      businessFileName: 'WGZR_EP001_001_S001_YJF_V001_1.mov',
      role: 'primary',
      isPrimary: true,
      fileSize: 2048,
      contentType: 'video/quicktime'
    }],
    ...overrides
  }
}

describe('版本详情与受保护下载', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:version-file') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    downloadProtectedVersionFile.mockResolvedValue(new Blob(['media']))
  })

  it('通过 versionId+fileId 专用接口下载并立即释放 Object URL', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(VersionDetailCard, { ...mountOptions, props: { version: version(), canDownload: true } })
    await wrapper.findAll('button').find(item => item.text().includes('下载')).trigger('click')
    await flushPromises()

    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(7, fileId, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(click).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:version-file')
    expect(wrapper.html()).not.toContain('/shot-grid/versions/7/files/')
    click.mockRestore()
    wrapper.unmount()
  })

  it('版本切换与卸载会取消旧下载，迟到 Blob 不会生成 URL', async () => {
    let resolveDownload
    downloadProtectedVersionFile.mockImplementationOnce((_versionId, _fileId, options) => new Promise(resolve => {
      resolveDownload = resolve
      expect(options.signal.aborted).toBe(false)
    }))
    const wrapper = mount(VersionDetailCard, { ...mountOptions, props: { version: version(7), canDownload: true } })
    await wrapper.findAll('button').find(item => item.text().includes('下载')).trigger('click')
    const signal = downloadProtectedVersionFile.mock.calls[0][2].signal
    await wrapper.setProps({ version: version(8) })
    expect(signal.aborted).toBe(true)
    resolveDownload(new Blob(['late']))
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('403/404/5xx 下载失败以明确错误显示且不泄露存储路径', async () => {
    downloadProtectedVersionFile.mockRejectedValueOnce({ httpStatus: 403, errorKey: 'SG_VERSION_FILE_FORBIDDEN', message: '无权下载文件' })
    const wrapper = mount(VersionDetailCard, { ...mountOptions, props: { version: version(), canDownload: true } })
    await wrapper.findAll('button').find(item => item.text().includes('下载')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('无权访问版本')
    expect(wrapper.text()).toContain('SG_VERSION_FILE_FORBIDDEN')
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('没有文件下载权限时不显示操作且不请求', async () => {
    const wrapper = mount(VersionDetailCard, { ...mountOptions, props: { version: version(), canDownload: false } })
    expect(wrapper.findAll('button').some(item => item.text().includes('下载'))).toBe(false)
    expect(downloadProtectedVersionFile).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
