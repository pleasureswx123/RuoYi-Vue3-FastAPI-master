import { describe, expect, it } from 'vitest'
import { shotStatusMeta } from '@/views/shot/shotPresentation'
import { historyStageMeta, currentProductionHandoff, productionHistoryActiveStep } from '@/components/production-history/productionHistoryPresentation'

describe('镜头分配前阶段', () => {
  it('列表和履历一致显示待完善，并明确下一步', () => {
    expect(shotStatusMeta({ status: 'pending_info' }).label).toBe('待完善')
    expect(historyStageMeta('pending_info').label).toBe('待完善')
    expect(currentProductionHandoff({ currentStage: 'pending_info' }).next).toContain('完善制作内容')
    expect(productionHistoryActiveStep('pending_info')).toBe(1)
    expect(productionHistoryActiveStep('unassigned')).toBe(2)
  })
  it('已有任务不会因内容空白退回待完善', () => {
    expect(shotStatusMeta({ status: 'in_progress', description: '' }).label).toBe('制作中')
    expect(shotStatusMeta({ status: 'unassigned' }).label).toBe('待分配')
  })
})
