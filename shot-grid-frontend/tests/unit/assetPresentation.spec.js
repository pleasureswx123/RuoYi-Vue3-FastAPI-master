import { describe, expect, it } from 'vitest'

import {
  assetAssigneeSummary,
  assetDirectoryStatusMeta,
  assetErrorState,
  assetStatusMeta,
  assetTypeMeta,
  groupAssetPreviewRows,
  memberLabel,
  memberUserName,
  resolveAssetThumbnail,
  selectableAssetPreviewRows
} from '@/views/asset/assetPresentation'

describe('资产展示模型', () => {
  it('稳定映射三种资产类型、状态和目录状态', () => {
    expect(assetTypeMeta('Character').label).toBe('角色')
    expect(assetTypeMeta('Environment').label).toBe('场景')
    expect(assetTypeMeta('Prop').label).toBe('道具')
    expect(assetStatusMeta('reviewing').label).toBe('待审核')
    expect(assetDirectoryStatusMeta('failed').tone).toBe('danger')
  })

  it('按真实 HTTP 状态分流而不把权限失败伪装成空列表', () => {
    expect(assetErrorState({ httpStatus: 403, message: '不是项目成员' })).toMatchObject({
      title: '没有资产访问权限',
      retryable: false,
      message: '不是项目成员'
    })
    expect(assetErrorState({ httpStatus: 409, errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT' })).toMatchObject({
      title: '资产状态已发生变化',
      retryable: true,
      errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT'
    })
  })

  it('跨 Sheet 选择使用复合身份且只包含可导入行', () => {
    const rows = [
      { sheetName: 'Sheet1', rowNumber: 2, canImport: true },
      { sheetName: '角色', rowNumber: 2, canImport: true },
      { sheetName: '角色', rowNumber: 3, canImport: false }
    ]
    expect(Object.keys(groupAssetPreviewRows(rows))).toEqual(['Sheet1', '角色'])
    expect(selectableAssetPreviewRows(rows)).toEqual([
      { sheetName: 'Sheet1', rowNumber: 2 },
      { sheetName: '角色', rowNumber: 2 }
    ])
  })

  it('只消费后端明确投影的缩略图并安全格式化成员名', () => {
    const thumbnail = { fileId: 'file-1', name: 'thumb.png', url: '/shot-grid/versions/1/files/file-1/download' }
    expect(resolveAssetThumbnail({ thumbnail, items: [] })).toBe(thumbnail)
    expect(resolveAssetThumbnail({ items: [{ thumbnail }] })).toBeNull()
    expect(resolveAssetThumbnail({ items: [{ latestVersion: { versionId: 1 } }] })).toBeNull()
    expect(memberLabel({ userId: 7, userName: '杨景锋', nickName: 'YJF', producerCode: 'OLD' })).toBe('杨景锋（YJF）')
    expect(memberUserName({ userId: 7, userName: '杨景锋', nickName: 'YJF' })).toBe('杨景锋')
    expect(memberLabel({ userId: 8, userName: 'producer' })).toBe('producer')
  })

  it('只用安全制作人选项映射列表 ID，未命中身份不猜姓名', () => {
    const members = [{ userId: 7, userName: '杨景锋', nickName: 'YJF', producerCode: 'YJF' }]
    expect(assetAssigneeSummary([7], members)).toBe('杨景锋')
    expect(assetAssigneeSummary([7, 99], members)).toBe('杨景锋、另 1 人不可分配')
    expect(assetAssigneeSummary([99], members)).toBe('另 1 人不可分配')
    expect(assetAssigneeSummary([], members)).toBe('未分配')
  })
})
