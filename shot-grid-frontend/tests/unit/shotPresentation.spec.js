import { describe, expect, it } from 'vitest'

import {
  formatShotDuration,
  groupPreviewRows,
  secondsToDurationMs,
  selectablePreviewRows,
  shotAssigneeName,
  shotAssigneeOptionLabel,
  shotErrorState,
  shotStatusMeta
} from '@/views/shot/shotPresentation'

describe('镜头展示规则', () => {
  it('集中映射任务聚合状态和时长', () => {
    expect(shotStatusMeta('reviewing')).toMatchObject({ label: '待审核', tone: 'info' })
    expect(formatShotDuration(2500)).toBe('2.5 秒')
    expect(formatShotDuration(0)).toBe('0 ms')
    expect(secondsToDurationMs('1.001')).toBe(1001)
    expect(() => secondsToDurationMs('1.0001')).toThrow('最多精确到 1 毫秒')
    expect(() => secondsToDurationMs(Number.MAX_SAFE_INTEGER)).toThrow('数值不能过大')
  })

  it('制作人展示优先用户名，选择项保留昵称用于辨识', () => {
    const assignee = { userId: 7, nickName: 'YJF' }
    const members = [{ userId: 7, userName: '杨景锋', nickName: 'YJF' }]
    expect(shotAssigneeName(assignee, members)).toBe('杨景锋')
    expect(shotAssigneeOptionLabel(members[0])).toBe('杨景锋（YJF）')
    expect(shotAssigneeName(assignee, [])).toBe('YJF')
  })

  it('以 Sheet 名和物理行保留跨 Sheet 可导入选择', () => {
    const rows = [
      { sheetName: 'EP001', rowNumber: 2, canImport: true },
      { sheetName: 'EP001', rowNumber: 3, canImport: false },
      { sheetName: 'EP002', rowNumber: 2, canImport: true }
    ]
    expect(Object.keys(groupPreviewRows(rows))).toEqual(['EP001', 'EP002'])
    expect(selectablePreviewRows(rows)).toEqual([
      { sheetName: 'EP001', rowNumber: 2 },
      { sheetName: 'EP002', rowNumber: 2 }
    ])
  })

  it('区分无权限、Token 过期、冲突和服务异常', () => {
    expect(shotErrorState({ httpStatus: 403, message: '无权访问' }).title).toBe('没有镜头访问权限')
    expect(shotErrorState({ httpStatus: 410, message: '已过期' }).title).toBe('导入检查结果已过期')
    expect(shotErrorState({ httpStatus: 409, message: '锁冲突', errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT', details: { lockVersion: 2 } })).toMatchObject({
      retryable: true,
      errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT',
      details: { lockVersion: 2 }
    })
    expect(shotErrorState({ httpStatus: 503, message: '缓存不可用' }).retryable).toBe(true)
  })
})
