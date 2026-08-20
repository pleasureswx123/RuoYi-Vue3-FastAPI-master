import { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag } from 'element-plus'
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
    { sheetName: 'Sheet1', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { assetType: 'Character', assetName: '春霞', productionItem: '标准立绘', assigneeUserName: 'producer', assigneeUserId: 7, itemDescription: '正视图' } },
    { sheetName: 'Sheet1', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_TASK_ASSIGNEE_AMBIGUOUS', fieldName: 'assigneeUserName', message: '制作人必须唯一' }], normalized: { assetType: 'Character', assetName: '春霞', productionItem: '侧视图', assigneeUserName: '重复昵称' } },
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

  it('展示类型统计和行级问题，并按 Sheet 与源数据行提交可导入选择', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人', members: [{ userId: 7, userName: '庞晓亮', nickName: 'PXL', projectRole: 'creator' }] },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('角色 1 资产 / 2 分项')
    expect(wrapper.text()).toContain('制作人必须唯一')
    expect(wrapper.text()).toContain('制作分项可后补')
    expect(wrapper.text()).toContain('已选 2 行 · 2 条可导入')
    const previewTags = wrapper.findAllComponents(ElTag)
    expect(previewTags.find(tag => tag.text().includes('角色 1 资产'))?.props('type')).toBe('warning')
    expect(previewTags.find(tag => tag.text().includes('场景 1 资产'))?.props('type')).toBe('primary')
    expect(previewTags.find(tag => tag.text() === '1' && tag.props('type') === 'warning')).toBeTruthy()

    await wrapper.get('select[aria-label="选择 Sheet1 第 3 行制作人"]').setValue('')
    expect(wrapper.text()).toContain('将以未分配状态导入')
    expect(wrapper.text()).toContain('已选 3 行 · 3 条可导入')

    await wrapper.findAll('button').find(button => button.text().includes('正式导入 3 行')).trigger('click')
    await flushPromises()
    expect(commitAssetImport).toHaveBeenCalledWith(
      8,
      {
        importToken: 'asset-token-9',
        selectedRows: [
          { sheetName: 'Sheet1', rowNumber: 2, assigneeUserId: 7 },
          { sheetName: 'Sheet1', rowNumber: 3, assigneeUserId: null },
          { sheetName: '场景', rowNumber: 2, assigneeUserId: null }
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

  it('使用 Element Plus 选择列，并通过批量分配弹窗只覆盖勾选行', async () => {
    const wrapper = mount(AssetImportDialog, {
      props: {
        projectId: 8,
        operationGeneration: 1,
        members: [
          { userId: 7, userName: '庞晓亮', nickName: 'PXL', projectRole: 'creator' },
          { userId: 9, userName: '钱志锋', nickName: 'QZF', projectRole: 'creator' }
        ]
      },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('选择全部可处理行')
    expect(wrapper.findAllComponents(ElTableColumn).filter(column => column.props('type') === 'selection')).toHaveLength(2)

    const tables = wrapper.findAllComponents(ElTable)
    tables[1].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.text()).toContain('已选 1 行 · 1 条可导入')
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(true)

    await wrapper.findAll('button').find(button => button.text().includes('批量分配')).trigger('click')
    await wrapper.get('select[aria-label="批量分配资产制作人"]').setValue('9')
    await wrapper.findAll('button').find(button => button.text().includes('确认分配')).trigger('click')
    expect(wrapper.text()).toContain('已选 1 行 · 1 条可导入')
    expect(wrapper.get('select[aria-label="选择 Sheet1 第 2 行制作人"]').element.value).toBe('9')
    expect(wrapper.get('select[aria-label="选择 Sheet1 第 3 行制作人"]').element.value).toBe('__unresolved__')
    expect(wrapper.get('select[aria-label="选择 场景 第 2 行制作人"]').element.value).toBe('')

    wrapper.findAllComponents(ElTable)[0].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(false)
    wrapper.unmount()
  })

  it('更换文件会中止旧预检并拒绝迟到响应污染新文件', async () => {
    let resolveOldPreview
    previewAssetImport.mockImplementationOnce(() => new Promise(resolve => { resolveOldPreview = resolve }))
      .mockResolvedValueOnce({ data: { ...preview, rows: [{ ...preview.rows[0], normalized: { ...preview.rows[0].normalized, assetName: '新资产' } }] } })
    const wrapper = mount(AssetImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const oldFile = new File(['old'], '旧资产.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [oldFile] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    const oldSignal = previewAssetImport.mock.calls[0][2].signal

    const newFile = new File(['new'], '新资产.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [newFile] })
    await input.trigger('change')
    expect(oldSignal.aborted).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
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
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '资产样表.xlsx')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('正式导入 2 行')

    previewAssetImport.mockRejectedValueOnce({ httpStatus: 503, message: '预检缓存不可用' })
    await wrapper.findAll('button').find(button => button.text().includes('重新检查')).trigger('click')
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
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
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
