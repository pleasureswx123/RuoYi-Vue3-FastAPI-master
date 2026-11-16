import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import TaskRelationsShortcut from '@/views/task/components/TaskRelationsShortcut.vue'
import RelatedAssetResult from '@/views/asset/components/RelatedAssetResult.vue'
import { getShotDetail } from '@/api/shot-grid/shots'
import { getAssetRelations } from '@/api/shot-grid/assets'
import { getVersionDetail } from '@/api/shot-grid/versions'
vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/assets', () => ({ getAssetRelations: vi.fn() }))
vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn() }))
vi.mock('@/components/version/ProtectedVersionPreview.vue', () => ({ default: { props: ['version', 'canPreview'], template: '<div data-testid="preview">{{ version.files[0]?.fileId }}</div>' } }))
vi.mock('@/components/version/VersionFolderButton.vue', () => ({ default: { props: ['version', 'file', 'canDownload'], template: '<button data-testid="folder" :disabled="!canDownload">{{ file.fileId }}</button>' } }))
let pinia
const shot = { taskId: 15, taskKind: 'shot_video', project: { projectId: 1 }, target: { shotId: 9 } }
const asset = { taskId: 16, taskKind: 'asset_image', project: { projectId: 1 }, target: { assetId: 2 } }
beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia)
  useSessionStore().permissions = ['*:*:*']
  getShotDetail.mockResolvedValue({ data: { projectId: 1, shotId: 9, assets: [{ assetId: 2 }, { assetId: 3 }, { assetId: 2 }] } })
  getAssetRelations.mockResolvedValue({ data: { projectId: 1, assetId: 2, relatedAssets: [] } })
})
it('镜头关联去重、资产关联零项也能定位，点击不冒泡到任务行', async () => {
  const wrapper = mount(TaskRelationsShortcut, { props: { task: shot }, global: { plugins: [pinia] } })
  await flushPromises()
  expect(wrapper.text()).toBe('关联资产 2 项')
  const bubbled = vi.fn(); wrapper.element.addEventListener('click', bubbled)
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('open')).toHaveLength(1)
  expect(bubbled).not.toHaveBeenCalled()
  await wrapper.setProps({ task: asset }); await flushPromises()
  expect(wrapper.text()).toBe('暂无关联资产')
  expect(getAssetRelations).toHaveBeenCalledWith(1, 2, expect.objectContaining({ signal: expect.any(AbortSignal) }))
  wrapper.unmount()
})
it('关联读取失败可重试，归属错误不显示数量，权限撤销清空', async () => {
  getShotDetail.mockRejectedValueOnce(new Error('失败'))
  const wrapper = mount(TaskRelationsShortcut, { props: { task: shot }, global: { plugins: [pinia] } })
  await flushPromises(); expect(wrapper.text()).toContain('加载失败')
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('2 项')
  getShotDetail.mockResolvedValueOnce({ data: { projectId: 2, shotId: 9, assets: [] } })
  await wrapper.setProps({ refreshKey: 1 }); await flushPromises()
  expect(wrapper.text()).toContain('加载失败')
  useSessionStore().permissions = []
  await flushPromises(); expect(wrapper.text()).toBe('')
  wrapper.unmount()
})
it('切任务取消旧关联请求并隔离迟到结果', async () => {
  let resolve
  getShotDetail.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const wrapper = mount(TaskRelationsShortcut, { props: { task: shot }, global: { plugins: [pinia] } })
  const signal = getShotDetail.mock.lastCall[2].signal
  await wrapper.setProps({ task: asset }); await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve({ data: { projectId: 1, shotId: 9, assets: [{ assetId: 3 }] } })
  await flushPromises(); expect(wrapper.text()).toBe('暂无关联资产')
  wrapper.unmount()
})
const item = { task: { taskId: 16 }, version: { versionId: 71 } }
function result() { return mount(RelatedAssetResult, { props: { projectId: 1, item }, global: { plugins: [pinia] } }) }
it('关联成果按需读取，默认最佳候选，预览与文件夹使用同一文件', async () => {
  getVersionDetail.mockResolvedValue({ data: { projectId: 1, taskId: 16, versionId: 71, selectedCandidateId: 2, candidates: [
    { candidateId: 1, candidateNumber: '01', files: [{ fileId: 'file-1', role: 'review_media' }] },
    { candidateId: 2, candidateNumber: '02', files: [{ fileId: 'file-2', role: 'review_media' }] }
  ] } })
  const wrapper = result()
  expect(getVersionDetail).not.toHaveBeenCalled()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('[data-testid="preview"]').text()).toBe('file-2')
  expect(wrapper.get('[data-testid="folder"]').text()).toBe('file-2')
  wrapper.getComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 1)
  await flushPromises(); expect(wrapper.get('[data-testid="folder"]').text()).toBe('file-1')
  useSessionStore().permissions = ['shotgrid:version:query']
  await flushPromises(); expect(wrapper.find('[data-testid="preview"]').exists()).toBe(false)
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('[data-testid="folder"]').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})
it('关联成果拒绝错任务版本，切版本取消旧请求', async () => {
  getVersionDetail.mockResolvedValueOnce({ data: { projectId: 1, versionId: 71, taskId: 99 } })
  const wrapper = result()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('归属不匹配')
  expect(wrapper.find('[data-testid="folder"]').exists()).toBe(false)
  let resolve
  getVersionDetail.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  await wrapper.findAll('button').find(button => button.text() === '重试').trigger('click')
  const signal = getVersionDetail.mock.lastCall[1].signal
  await wrapper.setProps({ item: { task: { taskId: 17 }, version: { versionId: 72 } } })
  expect(signal.aborted).toBe(true)
  resolve({ data: { projectId: 1, versionId: 71, taskId: 16, files: [] } })
  await flushPromises(); expect(wrapper.find('[data-testid="preview"]').exists()).toBe(false)
  wrapper.unmount()
})
