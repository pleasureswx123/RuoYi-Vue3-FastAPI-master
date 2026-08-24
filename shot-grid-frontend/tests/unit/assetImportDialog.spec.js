import { ElAlert, ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElDialog, ElIcon, ElResult, ElTable, ElTableColumn, ElTag, ElTooltip, ElUpload } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'

vi.mock('@/api/shot-grid/assets', () => ({
  commitAssetImport: vi.fn(),
  downloadAssetImportTemplate: vi.fn(),
  previewAssetImport: vi.fn()
}))

const components = { ElAlert, ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElDialog, ElIcon, ElResult, ElTable, ElTableColumn, ElTag, ElTooltip, ElUpload }
const dialogStub = { template: '<section><slot name="header" /><slot /></section>' }

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
    { sheetName: 'Sheet1', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { assetType: 'Character', assetName: '春霞', productionItem: '标准立绘', itemDescription: '正视图' } },
    { sheetName: 'Sheet1', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_ASSET_NAME_REQUIRED', fieldName: 'assetName', message: '资产名称不能为空' }], normalized: { assetType: 'Character', assetName: null, productionItem: '侧视图' } },
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
      missingProductionItemWarnings: 1,
      autoMatchedRequirements: 1,
      pendingRequirements: 0,
      conflictRequirements: 0
    } })
    downloadAssetImportTemplate.mockResolvedValue(new Blob(['xlsx']))
  })

  it('展示类型统计和行级问题，并按 Sheet 与源数据行提交可导入选择', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人' },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('角色 1 资产 / 2 分项')
    expect(wrapper.text()).toContain('资产名称不能为空')
    expect(wrapper.text()).toContain('制作分项可后补')
    expect(wrapper.text()).toContain('已选择 2 条')
    const previewTags = wrapper.findAllComponents(ElTag)
    expect(previewTags.find(tag => tag.text().includes('角色 1 资产'))?.props('type')).toBe('warning')
    expect(previewTags.find(tag => tag.text().includes('场景 1 资产'))?.props('type')).toBe('primary')
    expect(previewTags.find(tag => tag.text() === '1' && tag.props('type') === 'warning')).toBeTruthy()

    expect(wrapper.text()).toContain('导入后可在资产列表统一分配制作任务')
    expect(wrapper.text()).toContain('导入有效期')
    expect(wrapper.text()).toContain('前完成导入')
    expect(wrapper.text()).toContain('正常')
    expect(wrapper.findAllComponents(ElTableColumn).some(column => column.props('label') === '制作人')).toBe(false)
    expect(wrapper.find('select').exists()).toBe(false)

    await wrapper.findAll('button').find(button => button.text().includes('确认导入 2 条')).trigger('click')
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
    expect(wrapper.text()).toContain('资产导入完成')
    const resultTags = wrapper.findAllComponents(ElTag)
    expect(resultTags.find(tag => tag.text() === '角色 1')?.props('type')).toBe('warning')
    expect(resultTags.find(tag => tag.text() === '场景 1')?.props('type')).toBe('primary')
    expect(resultTags.find(tag => tag.text() === '复用资产 0')?.props('type')).toBe('info')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    wrapper.unmount()
  })

  it('使用 Element Plus 选择列调整本次未分配导入范围', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('选择全部可处理行')
    expect(wrapper.findAllComponents(ElTableColumn).filter(column => column.props('type') === 'selection')).toHaveLength(2)

    const tables = wrapper.findAllComponents(ElTable)
    tables[1].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.text()).toContain('已选择 1 条')
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(false)

    wrapper.findAllComponents(ElTable)[0].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.text()).toContain('已选择 0 条')
    expect(wrapper.findAll('button').find(button => button.text().includes('确认导入')).attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('更换文件会中止旧预检并拒绝迟到响应污染新文件', async () => {
    let resolveOldPreview
    previewAssetImport.mockImplementationOnce(() => new Promise(resolve => { resolveOldPreview = resolve }))
      .mockResolvedValueOnce({ data: { ...preview, rows: [{ ...preview.rows[0], normalized: { ...preview.rows[0].normalized, assetName: '新资产' } }] } })
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const oldFile = new File(['old'], '旧资产.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [oldFile] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    const oldSignal = previewAssetImport.mock.calls[0][2].signal

    const newFile = new File(['new'], '新资产.xlsx')
    await wrapper.findComponent(ElUpload).props('onChange')({ raw: newFile })
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
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
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('确认导入 2 条')

    previewAssetImport.mockRejectedValueOnce({ httpStatus: 503, message: '预检缓存不可用' })
    await wrapper.findAll('button').find(button => button.text().includes('重新预览')).trigger('click')
    expect(wrapper.text()).not.toContain('确认导入 2 条')
    await flushPromises()
    expect(wrapper.text()).toContain('预检缓存不可用')
    expect(wrapper.text()).not.toContain('确认导入')
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
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
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
