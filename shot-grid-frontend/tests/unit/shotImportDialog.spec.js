import { ElAlert, ElButton, ElDialog, ElIcon, ElStatistic, ElTable, ElTableColumn, ElTag, ElTooltip, ElUpload } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { commitShotImport, downloadShotImportTemplate, previewShotImport } from '@/api/shot-grid/shots'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'

vi.mock('@/api/shot-grid/shots', () => ({
  commitShotImport: vi.fn(),
  downloadShotImportTemplate: vi.fn(),
  previewShotImport: vi.fn()
}))

const components = { ElAlert, ElButton, ElDialog, ElIcon, ElStatistic, ElTable, ElTableColumn, ElTag, ElTooltip, ElUpload }
const dialogStub = { template: '<section><slot name="header" /><slot /></section>' }

const preview = {
  batchId: 6,
  importToken: 'token-6',
  expiresAt: '2026-08-11T14:00:00',
  summary: { totalRows: 3, validRows: 2, warningRows: 1, errorRows: 1, distinctEpisodes: 2, distinctScenes: 2, distinctShots: 2 },
  workbookWarnings: [{ errorKey: 'SG_SHEET_IGNORED', message: '隐藏 Sheet 已忽略' }],
  rows: [
    { sheetName: 'EP001', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { sceneCode: '001', shotCode: 'S001', durationMs: 3000, description: '建立镜头', shotSize: '近景', cameraPosition: '低机位', cameraMovement: '缓慢推进', focalLength: '35/25', dialogue: '快离开这里', soundEffect: '舱门报警声', colorReference: '冷蓝色调', remark: '注意节奏', assetRequirements: [] } },
    { sheetName: 'EP001', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_DESCRIPTION_REQUIRED', fieldName: 'description', message: '制作内容不能为空' }], normalized: null },
    { sheetName: 'EP002', rowNumber: 2, canImport: true, warnings: [{ errorKey: 'SG_ASSET_REQUIREMENT_PENDING', fieldName: 'sceneName', message: '场景资产将在导入后待匹配' }], errors: [], normalized: { sceneCode: '000', shotCode: 'S001', durationMs: 2000, description: '序场镜头', assetRequirements: [{ rawName: '校园' }] } }
  ]
}

describe('镜头 Excel 导入对话框', () => {
  beforeEach(() => {
    previewShotImport.mockResolvedValue({ data: preview })
    commitShotImport.mockResolvedValue({ data: { batchId: 6, committedRows: 2, createdEpisodes: 2, createdScenes: 2, createdShots: 2, createdAssetRequirements: 1, idempotentReplay: false } })
    downloadShotImportTemplate.mockResolvedValue(new Blob(['xlsx']))
  })

  it('展示跨 Sheet 行级问题并只提交可导入选择', async () => {
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人' },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '镜头样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('EP001')
    expect(wrapper.text()).toContain('EP002')
    expect(wrapper.text()).toContain('制作内容不能为空')
    expect(wrapper.text()).toContain('场景资产将在导入后待匹配')
    expect(wrapper.text()).not.toContain('物理行')
    expect(wrapper.text()).toContain('近景')
    expect(wrapper.text()).toContain('低机位')
    expect(wrapper.text()).toContain('缓慢推进')
    expect(wrapper.text()).toContain('35/25')
    expect(wrapper.text()).toContain('快离开这里')
    expect(wrapper.text()).toContain('舱门报警声')
    expect(wrapper.text()).toContain('冷蓝色调')
    expect(wrapper.text()).toContain('注意节奏')
    expect(wrapper.text()).toContain('导入后可在镜头列表统一分配制作任务')
    expect(wrapper.text()).toContain('已选择 2 条')
    expect(wrapper.text()).toContain('导入有效期')
    expect(wrapper.text()).toContain('前完成导入')
    expect(wrapper.text()).toContain('正常')
    expect(wrapper.findAll('.shot-preview-summary strong')[0].text()).toBe('2 / 3')
    const summaryTags = wrapper.findAllComponents(ElTag)
    expect(summaryTags.find(tag => tag.text() === '1')?.props()).toMatchObject({ type: 'warning', effect: 'plain', size: 'small', round: true })
    expect(wrapper.findAllComponents(ElTableColumn).some(column => column.props('label') === '制作人')).toBe(false)
    expect(wrapper.find('select').exists()).toBe(false)

    await wrapper.findAll('button').find(button => button.text().includes('确认导入 2 条')).trigger('click')
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
    expect(wrapper.text()).toContain('镜头导入完成')
    wrapper.unmount()
  })

  it('使用 Element Plus 选择列调整本次未分配导入范围', async () => {
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '镜头样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('预览导入内容')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('选择全部可处理行')
    expect(wrapper.findAllComponents(ElTableColumn).filter(column => column.props('type') === 'selection')).toHaveLength(2)

    expect(wrapper.text()).toContain('已选择 2 条')
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(false)
    wrapper.findAllComponents(ElTable)[1].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.text()).toContain('已选择 1 条')
    expect(wrapper.findAll('button').find(button => button.text().includes('确认导入')).text()).toContain('1 条')
    wrapper.unmount()
  })

  it('组件卸载会中止仍在进行的模板下载且不创建 object URL', async () => {
    let resolveDownload
    downloadShotImportTemplate.mockReturnValue(new Promise(resolve => { resolveDownload = resolve }))
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:template') })
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components, stubs: { teleport: true, ElDialog: dialogStub } }
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
