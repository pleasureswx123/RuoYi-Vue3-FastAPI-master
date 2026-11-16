import { describe, expect, it } from 'vitest'
import { finalBadge, assetFinalSummary } from '@/components/version/finalPresentation'
import { localLayoutFolderUrl } from '@/utils/folderOpener'

describe('定稿展示', () => {
  const approvedVersion = { versionId: 8, versionNo: 3, versionStatus: 'final', deliveryStatus: 'published' }
  it('仅发布成功显示绿色定稿，失败和无记录不能冒充归档完成', () => {
    expect(finalBadge({ status: 'completed', approvedVersion })).toEqual({ type: 'success', label: '定稿 V003' })
    for (const state of ['pending', 'publishing', 'failed', null]) {
      const badge = finalBadge({ status: 'completed', approvedVersion: { ...approvedVersion, deliveryStatus: state } })
      expect(badge.type).toBe('warning')
      expect(badge.label).not.toBe('定稿 V003')
    }
    expect(finalBadge({ status: 'completed' })).toBeNull()
  })
  it('反馈后保留上次定稿，父级只汇总成功归档的活动分项', () => {
    expect(finalBadge({ assetStatus: 'revision', approvedVersion: { ...approvedVersion, versionStatus: 'rejected' } }).label).toBe('修改中 · 上次定稿 V003')
    expect(assetFinalSummary({ itemCount: 3, finalizedItemCount: 1, itemStatusCounts: { completed: 2 } })).toBe('已定稿 1/3')
  })
  it('本地打开器只允许有效业务层级末尾一个 FINAL', () => {
    for (const path of [String.raw`项目\SHOT\EP001\001\0001\V001\FINAL`, String.raw`项目\ASSET\Prop\宝剑\正面__7\V003\FINAL`, String.raw`项目\VIDEO\EP01\001_0001\FINAL`]) {
      expect(localLayoutFolderUrl(path)).toMatch(/^shotgrid-folder:\/\/demo-layout\//)
    }
    for (const path of [String.raw`项目\SHOT\EP001\001\0001\V001\FINAL\FINAL`, String.raw`项目\SHOT\EP001\001\0001\V001\..\FINAL`, String.raw`项目\SHOT\FINAL`, String.raw`C:\Windows\FINAL`]) expect(localLayoutFolderUrl(path)).toBe('')
  })
})
