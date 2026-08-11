import { ElButton, ElIcon } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { commitShotImport, downloadShotImportTemplate, previewShotImport } from '@/api/shot-grid/shots'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'

vi.mock('@/api/shot-grid/shots', () => ({
  commitShotImport: vi.fn(),
  downloadShotImportTemplate: vi.fn(),
  previewShotImport: vi.fn()
}))

const preview = {
  batchId: 6,
  importToken: 'token-6',
  expiresAt: '2026-08-11T14:00:00',
  summary: { totalRows: 3, validRows: 2, warningRows: 1, errorRows: 1, distinctEpisodes: 2, distinctScenes: 2, distinctShots: 2 },
  workbookWarnings: [{ errorKey: 'SG_SHEET_IGNORED', message: '隐藏 Sheet 已忽略' }],
  rows: [
    { sheetName: 'EP001', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { sceneCode: '001', shotCode: 'S001', durationMs: 3000, description: '建立镜头', assetRequirements: [] } },
    { sheetName: 'EP001', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_DESCRIPTION_REQUIRED', fieldName: 'description', message: '制作内容不能为空' }], normalized: null },
    { sheetName: 'EP002', rowNumber: 2, canImport: true, warnings: [{ errorKey: 'SG_ASSIGNEE_NOT_FOUND', fieldName: 'assigneeUserName', message: '制作人未匹配' }], errors: [], normalized: { sceneCode: '000', shotCode: 'S001', durationMs: 2000, description: '序场镜头', assigneeUserName: '未知', assetRequirements: [{ rawName: '校园' }] } }
  ]
}

describe('镜头 Excel 导入对话框', () => {
  beforeEach(() => {
    previewShotImport.mockResolvedValue({ data: preview })
    commitShotImport.mockResolvedValue({ data: { batchId: 6, committedRows: 2, createdEpisodes: 2, createdScenes: 2, createdShots: 2, createdTasks: 0, createdAssetRequirements: 1, idempotentReplay: false } })
    downloadShotImportTemplate.mockResolvedValue(new Blob(['xlsx']))
  })

  it('展示跨 Sheet 行级问题并只提交可导入选择', async () => {
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人' },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '镜头样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('开始预检')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('EP001')
    expect(wrapper.text()).toContain('EP002')
    expect(wrapper.text()).toContain('制作内容不能为空')
    expect(wrapper.text()).toContain('制作人未匹配')
    expect(wrapper.text()).toContain('已选 2 条可导入行')

    await wrapper.findAll('button').find(button => button.text().includes('正式导入 2 行')).trigger('click')
    await flushPromises()
    expect(commitShotImport).toHaveBeenCalledWith(
      8,
      {
        importToken: 'token-6',
        selectedRows: [
          { sheetName: 'EP001', rowNumber: 2 },
          { sheetName: 'EP002', rowNumber: 2 }
        ]
      },
      expect.stringContaining('shot-import-8:')
    )
    expect(wrapper.text()).toContain('镜头已按单事务完成导入')
    wrapper.unmount()
  })

  it('组件卸载会中止仍在进行的模板下载且不创建 object URL', async () => {
    let resolveDownload
    downloadShotImportTemplate.mockReturnValue(new Promise(resolve => { resolveDownload = resolve }))
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:template') })
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    await wrapper.findAll('button').find(button => button.text().includes('下载官方模板')).trigger('click')
    const signal = downloadShotImportTemplate.mock.calls[0][0].signal
    expect(signal.aborted).toBe(false)
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
    resolveDownload(new Blob(['xlsx']))
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
