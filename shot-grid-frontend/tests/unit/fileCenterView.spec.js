import { ElButton, ElIcon, ElImage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectFilePage } from '@/api/shot-grid/files'
import { getProjectPage } from '@/api/shot-grid/projects'
import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import FileCenterView from '@/views/file/FileCenterView.vue'

vi.mock('@/api/shot-grid/files', () => ({ getProjectFilePage: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => Number(value),
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/versions', () => ({ downloadProtectedVersionFile: vi.fn() }))

const project = {
  projectId: 8,
  projectCode: 'LCFR',
  projectName: '罗刹夫人',
  myProjectRole: 'director'
}
const file = {
  fileId: '018f1e40-1111-4111-8111-111111111111',
  projectId: 8,
  versionId: 33,
  taskId: 21,
  taskName: '动力舱合成',
  taskKind: 'shot_video',
  versionNo: 3,
  versionNumber: 'V003',
  versionStatus: 'pending_review',
  originalName: 'output.mp4',
  businessFileName: 'LCFR_EP001_001_S001_YJF_V003_1786.mp4',
  role: 'review_media',
  isPrimary: true,
  contentType: 'video/mp4',
  fileSize: 1024,
  nasRelativePath: 'EP01/SHOT/S001/LCFR_V003.mp4',
  submittedTime: '2026-08-12T10:00:00',
  thumbnail: {
    fileId: '018f1e40-2222-4222-8222-222222222222',
    url: '/shot-grid/versions/33/files/018f1e40-2222-4222-8222-222222222222/download'
  },
  proxyMedia: {
    fileId: '018f1e40-3333-4333-8333-333333333333',
    url: '/shot-grid/versions/33/files/018f1e40-3333-4333-8333-333333333333/download'
  }
}

async function mountView(permissions = ['shotgrid:storage:path', 'shotgrid:file:download']) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.permissions = permissions
  const wrapper = mount(FileCenterView, {
    global: {
      plugins: [pinia],
      components: { ElButton, ElIcon },
      stubs: { ProjectStoragePanel: { template: '<div class="storage-panel-stub">存储诊断</div>' } }
    }
  })
  await flushPromises()
  return wrapper
}

describe('文件与 NAS 一级页', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:file-thumbnail') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    getProjectPage.mockResolvedValue({ rows: [project], total: 1 })
    getProjectFilePage.mockResolvedValue({ rows: [file], total: 1 })
    downloadProtectedVersionFile.mockResolvedValue(new Blob(['file']))
  })

  it('按项目读取可追溯正式版本文件并展示 NAS 相对路径', async () => {
    const wrapper = await mountView()

    expect(getProjectFilePage).toHaveBeenCalledWith('8', expect.objectContaining({
      pageNum: 1,
      fileRole: undefined,
      orderByColumn: 'submittedTime'
    }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('LCFR_EP001_001_S001_YJF_V003_1786.mp4')
    expect(wrapper.text()).toContain('动力舱合成 · V003 · 审核文件')
    expect(wrapper.text()).toContain('EP01/SHOT/S001/LCFR_V003.mp4')
    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(
      33,
      '018f1e40-2222-4222-8222-222222222222',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(wrapper.find('.file-thumbnail img').attributes()).toMatchObject({
      src: 'blob:file-thumbnail',
      alt: 'LCFR_EP001_001_S001_YJF_V003_1786.mp4 缩略图'
    })
    expect(wrapper.find('.file-thumbnail__video-trigger').attributes('aria-label')).toContain('点击预览视频')
    await wrapper.find('.file-thumbnail__video-trigger').trigger('click')
    await flushPromises()
    expect(downloadProtectedVersionFile).toHaveBeenCalledWith(
      33,
      '018f1e40-3333-4333-8333-333333333333',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(document.body.querySelector('.file-video-preview__player')?.getAttribute('src')).toBe('blob:file-thumbnail')
    expect(wrapper.find('.storage-panel-stub').exists()).toBe(true)
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:file-thumbnail')
  })

  it('图片文件点击缩略图时保留大图预览能力', async () => {
    getProjectFilePage.mockResolvedValueOnce({
      rows: [{ ...file, taskKind: 'asset_image', contentType: 'image/png', proxyMedia: null }],
      total: 1
    })
    const wrapper = await mountView()

    expect(wrapper.find('.file-thumbnail__video-trigger').exists()).toBe(false)
    expect(wrapper.findComponent(ElImage).props()).toMatchObject({
      fit: 'contain',
      previewSrcList: ['blob:file-thumbnail'],
      previewTeleported: true,
      hideOnClickModal: true
    })
    wrapper.unmount()
  })

  it('没有文件与 NAS 权限时失败关闭且不请求文件列表', async () => {
    const wrapper = await mountView(['shotgrid:project:list'])

    expect(getProjectFilePage).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('当前账号没有文件与 NAS 访问权限')
    wrapper.unmount()
  })
})
