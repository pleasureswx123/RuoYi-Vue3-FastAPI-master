import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  getAssetProductionHistory,
  getProductionHistory,
  getShotProductionHistory
} from '@/api/shot-grid/productionHistory'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('制作履历 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('镜头与资产使用项目范围专用路径并透传取消信号', () => {
    const signal = new AbortController().signal
    getShotProductionHistory(8, 41, { signal })
    getAssetProductionHistory(8, 31, { signal })

    expect(request.mock.calls.map(([config]) => config.url)).toEqual([
      '/shot-grid/projects/8/shots/41/production-history',
      '/shot-grid/projects/8/assets/31/production-history'
    ])
    expect(request.mock.calls[0][0]).toMatchObject({ method: 'get', signal, silentError: true })
    expect(request.mock.calls[1][0]).toMatchObject({ method: 'get', signal, silentError: true })
  })

  it('拒绝非法对象类型与非法资源 ID', () => {
    expect(() => getProductionHistory(8, 'project', 1)).toThrow('制作履历对象类型无效')
    expect(() => getShotProductionHistory(8, '../41')).toThrow('镜头 ID 必须为正整数')
    expect(() => getAssetProductionHistory(0, 31)).toThrow('项目 ID 必须为正整数')
    expect(request).not.toHaveBeenCalled()
  })
})
