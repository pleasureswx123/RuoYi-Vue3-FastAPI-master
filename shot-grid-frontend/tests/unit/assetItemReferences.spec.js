import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import AssetItemReferences from '@/views/asset/components/AssetItemReferences.vue'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
let wrapper
const detail = { taskId: 20, project: { projectId: 6 }, requirements: '保持角色比例', referenceDescription: '服装参考', referenceFiles: [{ fileId: 'f1', originalName: '角色参考.pdf', contentType: 'application/pdf', fileSize: 100, downloadUrl: '/shot-grid/tasks/20/reference-files/f1/download' }] }
beforeEach(() => getTaskDetail.mockReset().mockResolvedValue({ data: detail }))
afterEach(() => wrapper?.unmount())
it('回显要求、参考说明与附件，不依赖编辑权限且不提供删除', async () => {
  wrapper = mount(AssetItemReferences, { props: { projectId: 6, taskId: 20 } })
  await flushPromises()
  expect(wrapper.text()).toContain('保持角色比例')
  expect(wrapper.text()).toContain('服装参考')
  expect(wrapper.text()).toContain('角色参考.pdf')
  expect(wrapper.getComponent(ReviewReferenceFiles).props('removable')).toBe(false)
})
it('权限失败显示错误而非无资料，可重试', async () => {
  getTaskDetail.mockRejectedValueOnce({ status: 403 })
  wrapper = mount(AssetItemReferences, { props: { projectId: 6, taskId: 20 } })
  await flushPromises()
  expect(wrapper.text()).toContain('暂无权限')
  expect(wrapper.text()).not.toContain('暂无参考资料')
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('服装参考')
})
it('切换任务隔离迟到内容，并随任务版本刷新', async () => {
  let resolve
  getTaskDetail.mockReturnValueOnce(new Promise(done => { resolve = done }))
  wrapper = mount(AssetItemReferences, { props: { projectId: 6, taskId: 20 } })
  getTaskDetail.mockResolvedValue({ data: { ...detail, taskId: 21, referenceDescription: '新资料' } })
  await wrapper.setProps({ taskId: 21 }); await flushPromises()
  resolve({ data: detail }); await flushPromises()
  expect(wrapper.text()).toContain('新资料')
  expect(wrapper.text()).not.toContain('服装参考')
  await wrapper.setProps({ taskVersion: 2 }); await flushPromises()
  expect(getTaskDetail).toHaveBeenCalledTimes(3)
})
