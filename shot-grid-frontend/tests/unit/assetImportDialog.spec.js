import { ElButton, ElIcon } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'

vi.mock('@/api/shot-grid/assets', () => ({
  commitAssetImport: vi.fn(),
  downloadAssetImportTemplate: vi.fn(),
  previewAssetImport: vi.fn()
}))

const preview = {
  batchId: 9,
  importToken: 'asset-token-9',
  expiresAt: '2026-08-11T14:00:00',
  summary: {
    totalRows: 3,
    validRows: 2,
    warningRows: 1,
    errorRows: 1,
    distinctAssets: 2,
    distinctAssetItems: 2,
    estimatedAutoMatches: 1,
    byType: {
      Character: { assets: 1, items: 2, validRows: 1, warningRows: 1, errorRows: 1 },
      Environment: { assets: 1, items: 1, validRows: 1, warningRows: 0, errorRows: 0 }
    }
  },
  workbookWarnings: [{ errorKey: 'SG_IMPORT_READONLY_COLUMNS_IGNORED', message: '状态列已忽略' }],
  rows: [
    { sheetName: 'Sheet1', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { assetType: 'Character', assetName: '春霞', productionItem: '标准立绘', assigneeUserName: '杨景锋', itemDescription: '正视图' } },
    { sheetName: 'Sheet1', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_TASK_ASSIGNEE_AMBIGUOUS', fieldName: 'assigneeUserName', message: '制作人必须唯一' }], normalized: { assetType: 'Character', assetName: '春霞', productionItem: '侧视图' } },
    { sheetName: '场景', rowNumber: 2, canImport: true, warnings: [{ errorKey: 'SG_ASSET_PRODUCTION_ITEM_MISSING', fieldName: 'productionItem', message: '制作分项可后补' }], errors: [], normalized: { assetType: 'Environment', assetName: '动力舱', productionItem: null, itemDescription: '冷蓝色调' } }
  ]
}

describe('资产 Excel 导入对话框', () => {
  beforeEach(() => {
    previewAssetImport.mockResolvedValue({ data: preview })
    commitAssetImport.mockResolvedValue({ data: {
      batchId: 9,
      committedRows: 2,
      createdAssetsByType: { Character: 1, Environment: 1, Prop: 0 },
      reusedAssets: 0,
      createdAssetItems: 2,
      createdTasks: 1,
      missingProductionItemWarnings: 1,
      autoMatchedRequirements: 1,
      pendingRequirements: 0,
      conflictRequirements: 0
    } })
    downloadAssetImportTemplate.mockResolvedValue(new Blob(['xlsx']))
  })

  it('展示类型统计和行级问题，并按 Sheet+物理行提交可导入选择', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人' },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('开始预检')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('角色 1 资产 / 2 分项')
    expect(wrapper.text()).toContain('制作人必须唯一')
    expect(wrapper.text()).toContain('制作分项可后补')
    expect(wrapper.text()).toContain('已选 2 条可导入行')

    await wrapper.findAll('button').find(button => button.text().includes('正式导入 2 行')).trigger('click')
    await flushPromises()
    expect(commitAssetImport).toHaveBeenCalledWith(
      8,
      {
        importToken: 'asset-token-9',
        selectedRows: [
          { sheetName: 'Sheet1', rowNumber: 2 },
          { sheetName: '场景', rowNumber: 2 }
        ]
      },
      expect.stringContaining('asset-import-8:')
    )
    expect(wrapper.text()).toContain('资产已按单事务完成导入')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    wrapper.unmount()
  })

  it('更换文件会中止旧预检并拒绝迟到响应污染新文件', async () => {
    let resolveOldPreview
    previewAssetImport.mockImplementationOnce(() => new Promise(resolve => { resolveOldPreview = resolve }))
      .mockResolvedValueOnce({ data: { ...preview, rows: [{ ...preview.rows[0], normalized: { ...preview.rows[0].normalized, assetName: '新资产' } }] } })
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const oldFile = new File(['old'], '旧资产.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [oldFile] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('开始预检')).trigger('click')
    const oldSignal = previewAssetImport.mock.calls[0][2].signal

    const newFile = new File(['new'], '新资产.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [newFile] })
    await input.trigger('change')
    expect(oldSignal.aborted).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('开始预检')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('新资产')

    resolveOldPreview({ data: { ...preview, rows: [{ ...preview.rows[0], normalized: { ...preview.rows[0].normalized, assetName: '迟到旧资产' } }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('新资产')
    expect(wrapper.text()).not.toContain('迟到旧资产')
    wrapper.unmount()
  })

  it('重新预检开始即清除旧 Token 和选择，失败后不能提交旧预检', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('开始预检')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('正式导入 2 行')

    previewAssetImport.mockRejectedValueOnce({ httpStatus: 503, message: '预检缓存不可用' })
    await wrapper.findAll('button').find(button => button.text().includes('重新预检')).trigger('click')
    expect(wrapper.text()).not.toContain('正式导入 2 行')
    await flushPromises()
    expect(wrapper.text()).toContain('预检缓存不可用')
    expect(wrapper.text()).not.toContain('正式导入')
    expect(commitAssetImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('下载已通过匿名化和摘要门禁的官方资产模板', async () => {
    const createObjectURL = vi.fn(() => 'blob:asset-template')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElIcon }, stubs: { teleport: true } }
    })
    const button = wrapper.findAll('button').find(item => item.text().includes('下载官方模板'))
    await button.trigger('click')
    await flushPromises()
    expect(downloadAssetImportTemplate).toHaveBeenCalledWith({ signal: expect.any(AbortSignal) })
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:asset-template')
    wrapper.unmount()
    delete URL.createObjectURL
    delete URL.revokeObjectURL
    click.mockRestore()
  })
})
