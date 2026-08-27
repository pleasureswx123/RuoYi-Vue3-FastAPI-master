import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  archiveAsset,
  archiveAssetItem,
  assertProtectedAssetThumbnailUrl,
  assignAssetItemTask,
  commitAssetImport,
  createAsset,
  createAssetItem,
  deleteAssetItem,
  downloadAssetImportTemplate,
  downloadAssetThumbnail,
  getAssetDetail,
  getAssetItems,
  getAssetPage,
  getAssetRequirementPage,
  ignoreAssetRequirement,
  listAssetAssignees,
  previewAssetImport,
  rematchAssetRequirements,
  resolveAssetRequirement,
  updateAsset,
  updateAssetItem
} from '@/api/shot-grid/assets'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('资产 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('列表、详情和制作人选项使用真实项目范围路径与取消信号', () => {
    const signal = new AbortController().signal
    getAssetPage(8, { assetType: 'Character', pageNum: 2 }, { signal })
    getAssetDetail(8, 31, { signal })
    listAssetAssignees(8, { pageNum: 1, pageSize: 100 }, { signal })

    expect(request.mock.calls.map(([config]) => config.url)).toEqual([
      '/shot-grid/projects/8/assets',
      '/shot-grid/projects/8/assets/31',
      '/shot-grid/projects/8/asset-assignee-options'
    ])
    expect(request.mock.calls[0][0]).toMatchObject({ method: 'get', params: { assetType: 'Character', pageNum: 2 }, signal })
  })

  it('资产和制作分项 CRUD 使用受控路径并拒绝非法 ID', () => {
    expect(() => getAssetDetail(8, '../31')).toThrow('资产 ID 必须为正整数')
    createAsset(8, { assetType: 'Prop', assetName: '灯', items: [{}] })
    updateAsset(8, 31, { description: null, sortOrder: 1, remark: null, lockVersion: 0 })
    archiveAsset(8, 31, { reason: '不再生产', lockVersion: 1 })
    getAssetItems(8, 31)
    createAssetItem(8, 31, { productionItem: '正视图' })
    updateAssetItem(8, 41, { productionItem: '侧视图', lockVersion: 0 })
    archiveAssetItem(8, 41, { reason: '合并分项', lockVersion: 1 })
    deleteAssetItem(8, 41, { reason: '误建分项', lockVersion: 1 })
    expect(request).toHaveBeenLastCalledWith(expect.objectContaining({ data: { reason: '误建分项', lockVersion: 1 } }))
    expect(() => deleteAssetItem(8, '../41', {})).toThrow()
    assignAssetItemTask(8, 41, { assigneeUserId: 7, taskLockVersion: null })

    expect(request.mock.calls.map(([config]) => [config.method, config.url])).toEqual([
      ['post', '/shot-grid/projects/8/assets'],
      ['put', '/shot-grid/projects/8/assets/31'],
      ['post', '/shot-grid/projects/8/assets/31/archive'],
      ['get', '/shot-grid/projects/8/assets/31/items'],
      ['post', '/shot-grid/projects/8/assets/31/items'],
      ['put', '/shot-grid/projects/8/asset-items/41'],
      ['post', '/shot-grid/projects/8/asset-items/41/archive'],
      ['post', '/shot-grid/projects/8/asset-items/41/delete'],
      ['post', '/shot-grid/projects/8/asset-items/41/assign']
    ])
  })

  it('模板通过鉴权请求层下载，预检使用 multipart', () => {
    const signal = new AbortController().signal
    downloadAssetImportTemplate({ signal })
    const file = new File(['xlsx'], '资产.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    previewAssetImport(8, file, { signal })

    expect(request.mock.calls[0][0]).toMatchObject({
      url: '/shot-grid/imports/assets/template',
      method: 'get',
      responseType: 'blob',
      signal
    })
    expect(request.mock.calls[1][0]).toMatchObject({
      url: '/shot-grid/projects/8/assets/import/preview',
      method: 'post',
      timeout: 60_000,
      headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
    })
    expect(request.mock.calls[1][0].data).toBeInstanceOf(FormData)
  })

  it('受保护缩略图只接受版本文件相对路径', () => {
    const signal = new AbortController().signal
    const url = '/shot-grid/versions/31/files/550e8400-e29b-41d4-a716-446655440000/download'
    downloadAssetThumbnail(url, { signal })
    expect(request).toHaveBeenCalledWith({ url, method: 'get', responseType: 'blob', signal, silentError: true })
    expect(() => assertProtectedAssetThumbnailUrl('https://example.com/private.png')).toThrow('受保护版本文件路径')
    expect(() => assertProtectedAssetThumbnailUrl('/shot-grid/versions/1/files/../download')).toThrow('受保护版本文件路径')
  })

  it('资产需求列表、解决、忽略和重新匹配使用冻结路径与幂等请求头', () => {
    const signal = new AbortController().signal
    getAssetRequirementPage(8, { resolutionStatus: 'pending' }, { signal })
    resolveAssetRequirement(8, 91, { assetId: 31, reason: '同一设定' }, 'resolve-key')
    ignoreAssetRequirement(8, 92, { reason: '镜头文本误填' }, 'ignore-key')
    rematchAssetRequirements(8)

    expect(request.mock.calls.map(([config]) => [config.method, config.url])).toEqual([
      ['get', '/shot-grid/projects/8/asset-requirements'],
      ['post', '/shot-grid/projects/8/asset-requirements/91/resolve'],
      ['post', '/shot-grid/projects/8/asset-requirements/92/ignore'],
      ['post', '/shot-grid/projects/8/asset-requirements/rematch']
    ])
    expect(request.mock.calls[1][0].headers).toEqual({ 'X-Idempotency-Key': 'resolve-key', repeatSubmit: false })
    expect(request.mock.calls[2][0].headers).toEqual({ 'X-Idempotency-Key': 'ignore-key', repeatSubmit: false })
  })

  it('正式导入保留跨 Sheet 选择并携带内存幂等键', () => {
    const payload = {
      importToken: 'token-asset-1',
      selectedRows: [
        { sheetName: 'Sheet1', rowNumber: 2 },
        { sheetName: '角色', rowNumber: 2 }
      ]
    }
    commitAssetImport(8, payload, 'asset-import:key-1')
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/shot-grid/projects/8/assets/import/commit',
      method: 'post',
      data: payload,
      headers: { 'X-Idempotency-Key': 'asset-import:key-1', repeatSubmit: false }
    }))
  })
})
