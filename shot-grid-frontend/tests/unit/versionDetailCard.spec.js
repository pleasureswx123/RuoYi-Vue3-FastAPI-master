import { ElButton, ElIcon, ElRadioButton, ElRadioGroup, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'

vi.mock('@/api/shot-grid/versions', () => ({ downloadProtectedVersionFile: vi.fn() }))

const fileId = '550e8400-e29b-41d4-a716-446655440000'
const mountOptions = {
  global: {
    components: { ElButton, ElIcon, ElRadioButton, ElRadioGroup, ElTag },
    stubs: {
      ElDialog: {
        name: 'ElDialog',
        props: ['modelValue', 'title'],
        template: '<section v-if="modelValue" data-testid="file-preview-dialog"><h2>{{ title }}</h2><slot /><slot name="footer" /></section>'
      },
      ProtectedVersionPreview: {
        name: 'ProtectedVersionPreview',
        props: ['version', 'canPreview'],
        template: '<div data-testid="protected-version-preview" />'
      }
    }
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
      role: 'review_media',
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
    const tags = wrapper.findAllComponents(ElTag)
    expect(tags.map(tag => tag.text())).toEqual(['待审核', '审核文件', '主审核文件'])
    expect(tags.map(tag => tag.props('type'))).toEqual(['warning', 'info', 'warning'])
    expect(tags[0].props()).toMatchObject({ effect: 'light', size: 'small', round: true })
    expect(tags[1].props()).toMatchObject({ effect: 'plain', size: 'small', round: true })
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(click).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:version-file')
    expect(wrapper.html()).not.toContain('/shot-grid/versions/7/files/')
    click.mockRestore()
    wrapper.unmount()
  })

  it('版本文件列表不展示系统生成的缩略图和代理文件', () => {
    const wrapper = mount(VersionDetailCard, {
      ...mountOptions,
      props: {
        version: version(7, {
          files: [
            ...version().files,
            { fileId: 'thumbnail-file', originalName: 'thumbnail.jpg', role: 'thumbnail', fileSize: 1024, contentType: 'image/jpeg' },
            { fileId: 'proxy-file', originalName: 'proxy_media.mp4', role: 'proxy_media', fileSize: 1536, contentType: 'video/mp4' }
          ]
        }),
        canDownload: true
      }
    })

    expect(wrapper.find('.subheading').text()).toContain('1 个交付文件')
    expect(wrapper.findAll('.file-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('WGZR_EP001_001_S001_YJF_V001_1.mov')
    expect(wrapper.text()).not.toContain('thumbnail.jpg')
    expect(wrapper.text()).not.toContain('proxy_media.mp4')
    wrapper.unmount()
  })

  it('多候选版本可逐个切换预览，并在文件列表标明候选归属', async () => {
    const secondFileId = '550e8400-e29b-41d4-a716-446655440001'
    const firstFile = { ...version().files[0], candidateId: 701 }
    const secondFile = {
      ...firstFile,
      fileId: secondFileId,
      candidateId: 702,
      originalName: '候选乙.mp4',
      businessFileName: 'WGZR_EP001_001_S001_YJF_V007_02.mp4',
      isPrimary: false,
      contentType: 'video/mp4'
    }
    const wrapper = mount(VersionDetailCard, {
      ...mountOptions,
      props: {
        version: version(7, {
          candidateCount: 2,
          selectedCandidateId: null,
          files: [firstFile, secondFile],
          candidates: [
            { candidateId: 701, candidateNo: 1, candidateNumber: 'V007_01', candidateNote: '光影更稳', sortOrder: 0, isSelected: false, files: [firstFile] },
            { candidateId: 702, candidateNo: 2, candidateNumber: 'V007_02', candidateNote: '动作更顺', sortOrder: 1, isSelected: false, files: [secondFile] }
          ]
        }),
        canDownload: true
      }
    })

    const radioGroup = wrapper.getComponent(ElRadioGroup)
    const preview = wrapper.getComponent({ name: 'ProtectedVersionPreview' })
    expect(wrapper.findAllComponents(ElRadioButton).map(item => item.text())).toEqual([
      expect.stringContaining('V007_01'),
      expect.stringContaining('V007_02')
    ])
    expect(preview.props('version').files).toEqual([firstFile])
    expect(wrapper.findAll('.file-row')[0].classes()).toContain('is-previewing')
    expect(wrapper.findAllComponents(ElTag).map(tag => tag.text())).toEqual(expect.arrayContaining(['V007_01', 'V007_02']))

    radioGroup.vm.$emit('update:modelValue', 702)
    await flushPromises()

    expect(preview.props('version').files).toEqual([secondFile])
    expect(wrapper.text()).toContain('当前预览 V007_02')
    expect(wrapper.text()).toContain('动作更顺')
    expect(wrapper.findAll('.file-row')[1].classes()).toContain('is-previewing')
    expect(wrapper.findAll('.file-row')[0].classes()).not.toContain('is-previewing')
    wrapper.unmount()
  })

  it('任务历史关闭整块预览时可从每个文件打开对应候选预览', async () => {
    const firstFile = { ...version().files[0], candidateId: 701 }
    const secondFile = {
      ...firstFile,
      fileId: '550e8400-e29b-41d4-a716-446655440001',
      candidateId: 702,
      businessFileName: 'WGZR_EP001_001_S001_YJF_V007_02.mp4',
      contentType: 'video/mp4'
    }
    const wrapper = mount(VersionDetailCard, {
      ...mountOptions,
      props: {
        version: version(7, {
          files: [firstFile, secondFile],
          candidates: [
            { candidateId: 701, candidateNo: 1, candidateNumber: 'V007_01', sortOrder: 0, files: [firstFile] },
            { candidateId: 702, candidateNo: 2, candidateNumber: 'V007_02', sortOrder: 1, files: [secondFile] }
          ]
        }),
        canDownload: true,
        showPreview: false,
        showFilePreviewAction: true
      }
    })

    const previewButtons = wrapper.findAll('.file-actions button').filter(button => button.text().includes('预览'))
    expect(previewButtons).toHaveLength(2)
    expect(wrapper.find('[data-testid="file-preview-dialog"]').exists()).toBe(false)

    await previewButtons[1].trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="file-preview-dialog"]').text()).toContain('预览 V007_02')
    expect(wrapper.getComponent({ name: 'ProtectedVersionPreview' }).props('version').files).toEqual([secondFile])
    expect(wrapper.getComponent({ name: 'ProtectedVersionPreview' }).props('canPreview')).toBe(true)
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
    expect(wrapper.text()).toContain('无权下载文件')
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
