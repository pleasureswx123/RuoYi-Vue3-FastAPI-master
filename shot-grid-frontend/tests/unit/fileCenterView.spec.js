import { ElButton, ElCard, ElEmpty, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElPagination, ElSkeleton, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectFilePage } from '@/api/shot-grid/files'
import { getProjectPage } from '@/api/shot-grid/projects'
import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import { copyTextToClipboard } from '@/utils/clipboard'
import FileCenterView from '@/views/file/FileCenterView.vue'
import { setElSelectValue } from '../helpers/elementPlus'

vi.mock('@/api/shot-grid/files', () => ({ getProjectFilePage: vi.fn() }))
vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => Number(value),
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/versions', () => ({ downloadProtectedVersionFile: vi.fn() }))
vi.mock('@/utils/clipboard', () => ({ copyTextToClipboard: vi.fn() }))

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
      components: { ElButton, ElCard, ElEmpty, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElPagination, ElSkeleton, ElTag },
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
    copyTextToClipboard.mockResolvedValue(true)
  })

  it('按项目读取可追溯正式版本文件并展示 NAS 相对路径', async () => {
    const wrapper = await mountView()

    const toolbarForm = wrapper.find('form.file-toolbar')
    const filterForm = wrapper.find('form.file-filters')
    const toolbarFormComponent = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('file-toolbar'))
    expect(toolbarForm.classes()).toContain('el-form')
    expect(toolbarForm.findAll('.el-form-item')).toHaveLength(2)
    expect(toolbarFormComponent.props('labelPosition')).toBe('top')
    expect(filterForm.classes()).toContain('el-form')
    expect(filterForm.findAll('.el-form-item')).toHaveLength(4)
    const roleOptionValues = filterForm.findAllComponents({ name: 'ElOption' }).map(option => option.props('value'))
    expect(roleOptionValues).not.toContain('thumbnail')
    expect(roleOptionValues).not.toContain('proxy_media')
    expect(getProjectFilePage).toHaveBeenCalledWith('8', expect.objectContaining({
      pageNum: 1,
      fileRole: undefined,
      orderByColumn: 'submittedTime'
    }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('LCFR_EP001_001_S001_YJF_V003_1786.mp4')
    expect(wrapper.text()).toContain('动力舱合成 · V003')
    expect(wrapper.text()).toContain('审核文件')
    expect(wrapper.text()).toContain('EP01/SHOT/S001/LCFR_V003.mp4')
    expect(wrapper.find('.file-card.el-card').exists()).toBe(true)
    const fileTags = wrapper.find('.file-card').findAllComponents(ElTag)
    expect(fileTags.map(tag => tag.text())).toEqual(['待审核', '审核文件', '主文件'])
    expect(fileTags.map(tag => tag.props('type'))).toEqual(['warning', 'info', 'warning'])
    fileTags.forEach(tag => expect(tag.props()).toMatchObject({ effect: 'plain', size: 'small', round: true }))
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

  it('搜索与分页使用 Element Plus 组件协议并提交真实查询模型', async () => {
    getProjectFilePage.mockResolvedValue({ rows: [file], total: 21 })
    const wrapper = await mountView()

    await wrapper.find('input[aria-label="搜索业务文件"]').setValue('动力舱')
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '搜索').trigger('click')
    await flushPromises()
    expect(getProjectFilePage).toHaveBeenLastCalledWith('8', expect.objectContaining({ keyword: '动力舱', pageNum: 1 }), expect.anything())

    expect(wrapper.find('.file-pagination.el-pagination').exists()).toBe(true)
    await wrapper.find('.file-pagination .btn-next').trigger('click')
    await flushPromises()
    expect(getProjectFilePage).toHaveBeenLastCalledWith('8', expect.objectContaining({ keyword: '动力舱', pageNum: 2 }), expect.anything())
    wrapper.unmount()
  })

  it('复制文件 NAS 相对路径时使用共享剪贴板兼容链路', async () => {
    const wrapper = await mountView()

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '复制路径').trigger('click')
    await flushPromises()

    expect(copyTextToClipboard).toHaveBeenCalledWith('EP01/SHOT/S001/LCFR_V003.mp4')
    wrapper.unmount()
  })

  it('通过两个 Element Plus Form 重置完整文件查询且保留当前项目', async () => {
    const wrapper = await mountView()
    const toolbarForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('file-toolbar'))
    const filterForm = wrapper.findAllComponents(ElForm).find(form => form.classes().includes('file-filters'))
    await toolbarForm.find('input[aria-label="搜索业务文件"]').setValue('动力舱')
    const filterSelects = filterForm.findAllComponents({ name: 'ElSelect' })
    await setElSelectValue(filterSelects[0], 'review_media')
    await setElSelectValue(filterSelects[1], 'shot_video')
    await setElSelectValue(filterSelects[2], 'pending_review')
    getProjectFilePage.mockClear()

    await filterForm.findAllComponents(ElButton).find(button => button.text() === '重置').trigger('click')
    await flushPromises()

    expect(toolbarForm.props('model')).toMatchObject({ projectId: '8', keyword: '' })
    expect(filterForm.props('model')).toMatchObject({ fileRole: '', taskKind: '', versionStatus: '', pageNum: 1 })
    expect(getProjectFilePage).toHaveBeenLastCalledWith('8', expect.objectContaining({
      keyword: undefined,
      fileRole: undefined,
      taskKind: undefined,
      versionStatus: undefined,
      pageNum: 1
    }), expect.anything())
    wrapper.unmount()
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
