import { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag } from 'element-plus'
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
    { sheetName: 'EP001', rowNumber: 2, canImport: true, warnings: [], errors: [], normalized: { sceneCode: '001', shotCode: 'S001', durationMs: 3000, description: '建立镜头', shotSize: '近景', cameraPosition: '低机位', cameraMovement: '缓慢推进', focalLength: '35/25', dialogue: '快离开这里', soundEffect: '舱门报警声', colorReference: '冷蓝色调', remark: '注意节奏', assetRequirements: [] } },
    { sheetName: 'EP001', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_DESCRIPTION_REQUIRED', fieldName: 'description', message: '制作内容不能为空' }], normalized: null },
    { sheetName: 'EP002', rowNumber: 2, canImport: false, warnings: [], errors: [{ errorKey: 'SG_TASK_ASSIGNEE_INVALID', fieldName: 'assigneeUserName', message: '制作人未匹配' }], normalized: { sceneCode: '000', shotCode: 'S001', durationMs: 2000, description: '序场镜头', assigneeUserName: '未知', assetRequirements: [{ rawName: '校园' }] } }
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
      props: { projectId: 8, operationGeneration: 1, projectName: '罗刹夫人', members: [{ userId: 7, nickName: 'YJF', userName: '杨景锋', projectRole: 'creator' }] },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '镜头样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('EP001')
    expect(wrapper.text()).toContain('EP002')
    expect(wrapper.text()).toContain('制作内容不能为空')
    expect(wrapper.text()).toContain('制作人未匹配')
    expect(wrapper.text()).not.toContain('物理行')
    expect(wrapper.text()).toContain('近景')
    expect(wrapper.text()).toContain('低机位')
    expect(wrapper.text()).toContain('缓慢推进')
    expect(wrapper.text()).toContain('35/25')
    expect(wrapper.text()).toContain('快离开这里')
    expect(wrapper.text()).toContain('舱门报警声')
    expect(wrapper.text()).toContain('冷蓝色调')
    expect(wrapper.text()).toContain('注意节奏')
    expect(wrapper.text()).toContain('已选 1 行 · 1 条可导入')
    expect(wrapper.findAll('.shot-preview-summary strong')[0].text()).toBe('1 / 3')
    const summaryTags = wrapper.findAllComponents(ElTag)
    expect(summaryTags.find(tag => tag.text() === '1')?.props()).toMatchObject({ type: 'warning', effect: 'plain', size: 'small', round: true })

    const assigneeSelect = wrapper.get('select[aria-label="选择 EP002 第 2 行制作人"]')
    await assigneeSelect.setValue('7')
    expect(wrapper.text()).toContain('已选择：YJF（杨景锋）')
    expect(wrapper.text()).toContain('已选 2 行 · 2 条可导入')
    expect(wrapper.findAll('.shot-preview-summary strong')[0].text()).toBe('2 / 3')

    await wrapper.findAll('button').find(button => button.text().includes('正式导入 2 行')).trigger('click')
    await flushPromises()
    expect(commitShotImport).toHaveBeenCalledWith(
      8,
      {
        importToken: 'token-6',
        selectedRows: [
          { sheetName: 'EP001', rowNumber: 2, assigneeUserId: null },
          { sheetName: 'EP002', rowNumber: 2, assigneeUserId: 7 }
        ]
      },
      expect.stringContaining('shot-import-8:')
    )
    expect(wrapper.text()).toContain('镜头导入完成')
    wrapper.unmount()
  })

  it('使用 Element Plus 选择列，并通过批量分配弹窗只覆盖勾选行', async () => {
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1, members: [{ userId: 7, nickName: 'YJF', userName: '杨景锋', projectRole: 'creator' }] },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn, ElTag }, stubs: { teleport: true } }
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['xlsx'], '镜头样表.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text().includes('检查文件')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('选择全部可处理行')
    expect(wrapper.findAllComponents(ElTableColumn).filter(column => column.props('type') === 'selection')).toHaveLength(2)

    const tables = wrapper.findAllComponents(ElTable)
    const unmatchedCheckbox = tables[1].findAll('input[type="checkbox"]')[1]
    expect(unmatchedCheckbox.element.disabled).toBe(false)
    expect(wrapper.text()).toContain('已选 1 行 · 1 条可导入')
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(true)

    await wrapper.findAll('button').find(button => button.text().includes('批量分配')).trigger('click')
    await wrapper.get('select[aria-label="批量分配镜头制作人"]').setValue('7')
    await wrapper.findAll('button').find(button => button.text().includes('确认分配')).trigger('click')

    expect(wrapper.text()).toContain('已选 1 行 · 1 条可导入')
    expect(wrapper.text()).toContain('已选择：YJF（杨景锋）')
    expect(wrapper.findAll('.shot-preview-summary strong')[0].text()).toBe('1 / 3')
    expect(wrapper.get('select[aria-label="选择 EP001 第 2 行制作人"]').element.value).toBe('7')
    expect(wrapper.get('select[aria-label="选择 EP002 第 2 行制作人"]').element.value).toBe('__unresolved__')

    wrapper.findAllComponents(ElTable)[0].vm.$emit('selection-change', [])
    await flushPromises()
    expect(wrapper.findAll('button').some(button => button.text().includes('批量分配'))).toBe(false)
  })

  it('组件卸载会中止仍在进行的模板下载且不创建 object URL', async () => {
    let resolveDownload
    downloadShotImportTemplate.mockReturnValue(new Promise(resolve => { resolveDownload = resolve }))
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:template') })
    const wrapper = mount(ShotImportDialog, {
      props: { projectId: 8, operationGeneration: 1 },
      global: { components: { ElButton, ElDialog, ElIcon, ElTable, ElTableColumn }, stubs: { teleport: true } }
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
