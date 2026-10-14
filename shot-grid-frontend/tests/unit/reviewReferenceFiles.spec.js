import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ElDialog } from 'element-plus'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import { downloadReviewReferenceFile } from '@/api/shot-grid/reviews'

vi.mock('@/api/shot-grid/reviews', () => ({ downloadReviewReferenceFile: vi.fn() }))
const file = { fileId: 'video-1', originalName: '参考.mp4', downloadUrl: '/protected/download' }
let wrapper
beforeEach(() => {
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:video'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  downloadReviewReferenceFile.mockReset()
})
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('视频按需鉴权加载，关闭弹窗停止播放并释放地址', async () => {
  downloadReviewReferenceFile.mockResolvedValue(new Blob(['video'], { type: 'application/octet-stream' }))
  wrapper = mount(ReviewReferenceFiles, { props: { files: [file] } })
  expect(downloadReviewReferenceFile).not.toHaveBeenCalled()
  await wrapper.get('button[aria-label="预览视频 参考.mp4"]').trigger('click')
  await flushPromises()
  expect(downloadReviewReferenceFile).toHaveBeenCalledWith(file, { signal: expect.any(AbortSignal) })
  expect(URL.createObjectURL.mock.calls[0][0].type).toBe('video/mp4')
  expect(document.querySelector('video').getAttribute('src')).toBe('blob:video')
  wrapper.getComponent(ElDialog).vm.$emit('close')
  await flushPromises()
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:video')
})

it('切换资料时取消请求并忽略迟到的视频响应', async () => {
  let resolve
  downloadReviewReferenceFile.mockImplementation(() => new Promise(done => { resolve = done }))
  wrapper = mount(ReviewReferenceFiles, { props: { files: [file] } })
  await wrapper.get('button[aria-label="预览视频 参考.mp4"]').trigger('click')
  const signal = downloadReviewReferenceFile.mock.calls[0][1].signal
  await wrapper.setProps({ files: [] })
  expect(signal.aborted).toBe(true)
  resolve(new Blob(['video']))
  await flushPromises()
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})

it('加载失败显示重试和下载入口', async () => {
  downloadReviewReferenceFile.mockRejectedValue(new Error('失败'))
  wrapper = mount(ReviewReferenceFiles, { props: { files: [file] } })
  await wrapper.get('button[aria-label="预览视频 参考.mp4"]').trigger('click')
  await flushPromises()
  expect(document.body.textContent).toContain('视频加载失败，请重试或下载文件查看。')
  expect(document.body.textContent).toContain('重新加载')
  expect(document.body.textContent).toContain('下载视频')
})

it('PDF 图标按需鉴权预览并保留下载', async () => {
  const pdf = { ...file, originalName: '资料.pdf' }
  downloadReviewReferenceFile.mockResolvedValue(new Blob(['%PDF'], { type: 'application/octet-stream' }))
  wrapper = mount(ReviewReferenceFiles, { props: { files: [pdf] }, global: { stubs: { ReferencePdfPreview: { props: ['src'], template: '<div class="pdf-renderer" :data-src="src" />' } } } })
  expect(downloadReviewReferenceFile).not.toHaveBeenCalled()
  await wrapper.get('button[aria-label="预览文件 资料.pdf"]').trigger('click')
  await flushPromises()
  expect(URL.createObjectURL.mock.calls[0][0].type).toBe('application/pdf')
  expect(document.querySelector('.pdf-renderer').getAttribute('data-src')).toBe('blob:video')
  expect(document.body.textContent).toContain('下载文件')
})

it('旧版 Office 明确提示兼容范围而不发起无效预览', async () => {
  wrapper = mount(ReviewReferenceFiles, { props: { files: [{ ...file, originalName: '旧资料.doc' }] } })
  await wrapper.get('button[aria-label="预览文件 旧资料.doc"]').trigger('click')
  await flushPromises()
  expect(document.body.textContent).toContain('旧版 DOC/XLS/PPT')
  expect(downloadReviewReferenceFile).not.toHaveBeenCalled()
})
