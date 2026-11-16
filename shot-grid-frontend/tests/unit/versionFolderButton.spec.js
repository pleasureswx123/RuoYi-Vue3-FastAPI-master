import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ElButton } from 'element-plus'
import VersionFolderButton from '@/components/version/VersionFolderButton.vue'
import { useSessionStore } from '@/store/modules/session'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { requestLocalDemoFolder } from '@/utils/folderOpener'
vi.mock('@/api/shot-grid/tasks', () => ({ getTaskDetail: vi.fn() }))
vi.mock('@/utils/folderOpener', () => ({ requestLocalDemoFolder: vi.fn(() => true), candidateFolderPath: vi.fn(() => '') }))
const props = { version: { versionId: 3, projectId: 1, taskId: 9 }, file: { fileId: 'f', role: 'review_media', candidateId: 4, folderRelativePath: String.raw`演示项目\SHOT\EP001\001\0001\V001` }, canDownload: true }
function setup() {
  const pinia = createPinia(); setActivePinia(pinia); useSessionStore().permissions = ['shotgrid:task:query']
  return mount(VersionFolderButton, { props, global: { plugins: [pinia] } })
}
beforeEach(() => { vi.stubEnv('DEV', true) })
afterEach(() => vi.unstubAllEnvs())
describe('制作任务文件夹模拟', () => {
  it.each([false, true])('先核对归属，再打开对应镜头/资产分项目录：资产=%s', async asset => {
    getTaskDetail.mockResolvedValue({ data: { taskId: 9, project: { projectId: 1 }, target: asset ? { targetType: 'asset_item', assetId: 2, assetItemId: 7 } : { targetType: 'shot', shotId: 5 } } })
    const wrapper = setup()
    try {
      await wrapper.getComponent(ElButton).trigger('click'); await flushPromises()
      expect(requestLocalDemoFolder).toHaveBeenCalledWith(1, asset ? 7 : 5, 3, 4, asset ? 2 : 0, props.file.folderRelativePath)
    } finally { wrapper.unmount() }
  })
  it('归属错误、无文件权限和迟到请求都不打开目录', async () => {
    getTaskDetail.mockResolvedValueOnce({ data: { taskId: 9, project: { projectId: 2 } } })
    const wrapper = setup()
    try {
      await wrapper.getComponent(ElButton).trigger('click'); await flushPromises()
      expect(requestLocalDemoFolder).not.toHaveBeenCalled()
      await wrapper.setProps({ canDownload: false })
      expect(wrapper.getComponent(ElButton).props('disabled')).toBe(true)
      await wrapper.setProps({ canDownload: true })
      let finish
      getTaskDetail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      await wrapper.getComponent(ElButton).trigger('click')
      await wrapper.setProps({ version: { ...props.version, versionId: 6 } })
      finish({ data: { taskId: 9, project: { projectId: 1 }, target: { targetType: 'shot', shotId: 5 } } }); await flushPromises()
      expect(requestLocalDemoFolder).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
})
