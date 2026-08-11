import { afterEach, describe, expect, it, vi } from 'vitest'

import { createIdempotencyState } from '@/utils/idempotency'

describe('幂等键状态', () => {
  afterEach(() => vi.restoreAllMocks())

  it('同一业务载荷重试复用同一键，载荷变化后生成新键', () => {
    vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222')
    const state = createIdempotencyState('project-create')
    const first = state.forPayload({ projectName: '罗刹夫人', members: [2, 1] })
    const replay = state.forPayload({ members: [2, 1], projectName: '罗刹夫人' })
    const changed = state.forPayload({ projectName: '罗刹夫人', members: [1, 2] })

    expect(replay).toBe(first)
    expect(changed).not.toBe(first)
    expect(first).toHaveLength(51)
  })

  it('reset 后不复用先前业务键', () => {
    vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValueOnce('33333333-3333-4333-8333-333333333333')
      .mockReturnValueOnce('44444444-4444-4444-8444-444444444444')
    const state = createIdempotencyState('retry')
    const first = state.forPayload({ reason: '网络恢复' })
    state.reset()
    expect(state.forPayload({ reason: '网络恢复' })).not.toBe(first)
  })
})
