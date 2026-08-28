import { describe, expect, it } from 'vitest'

import {
  assetAssigneeSummary,
  assetDirectoryStatusMeta,
  assetErrorState,
  assetItemStatusEntries,
  assetStatusMeta,
  assetStatusTagClass,
  assetTypeMeta,
  groupAssetPreviewRows,
  memberLabel,
  memberUserName,
  resolveAssetThumbnail,
  selectableAssetPreviewRows
} from '@/views/asset/assetPresentation'

describe('资产展示模型', () => {
  it('稳定映射三种资产类型、状态和延迟目录状态', () => {
    expect(assetTypeMeta('Character').label).toBe('角色')
    expect(assetTypeMeta('Environment').label).toBe('场景')
    expect(assetTypeMeta('Prop').label).toBe('道具')
    expect(assetStatusMeta('unassigned')).toMatchObject({ label: '待分配', tone: 'warning' })
    expect(assetStatusMeta('not_started')).toMatchObject({ label: '待开工', tone: 'muted' })
    expect(assetStatusMeta('in_progress')).toMatchObject({ label: '制作中', tone: 'primary' })
    expect(assetStatusMeta('reviewing').label).toBe('待审核')
    expect(assetStatusTagClass('in_progress')).toBe('asset-status-tag--in_progress')
    expect(assetStatusTagClass('unexpected')).toBe('asset-status-tag--unknown')
    expect(assetDirectoryStatusMeta('not_created')).toMatchObject({ label: '开始制作时创建', tone: 'muted' })
    expect(assetDirectoryStatusMeta('ready')).toMatchObject({ label: '目录已就绪', tone: 'info' })
    expect(assetDirectoryStatusMeta('failed')).toMatchObject({ label: '目录处理异常', tone: 'danger' })
  })

  it('固定展示七类制作分项状态数量，并忽略异常计数', () => {
    expect(assetItemStatusEntries({ not_started: 2, preparing: 1, in_progress: -4, unknown: 9 })).toEqual([
      { status: 'unassigned', label: '待分配', count: 0 },
      { status: 'not_started', label: '待开工', count: 2 },
      { status: 'preparing', label: '目录准备中', count: 1 },
      { status: 'in_progress', label: '制作中', count: 0 },
      { status: 'reviewing', label: '待审核', count: 0 },
      { status: 'revision', label: '修改中', count: 0 },
      { status: 'completed', label: '已完成', count: 0 }
    ])
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
    expect(assetAssigneeSummary([], members)).toBe('-')
  })
})
