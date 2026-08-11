import { afterEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/utils/auth'
import request, { setSessionExpiredHandler } from '@/utils/request'

vi.mock('@/utils/transportCrypto', () => ({
  decryptTransportErrorResponse: vi.fn(async error => error),
  decryptTransportResponse: vi.fn(async response => response),
  encryptTransportRequest: vi.fn(async config => config),
  invalidateTransportKeyMeta: vi.fn(),
  resetTransportRequestConfig: vi.fn(),
  shouldRetryTransportWithFreshKey: vi.fn(() => false)
}))

function successAdapter(data) {
  return async config => ({ data, status: 200, statusText: 'OK', headers: {}, config, request: {} })
}

describe('统一请求层', () => {
  afterEach(() => setSessionExpiredHandler(null))

  it('携带 Bearer Token 并返回完整成功 envelope', async () => {
    setToken('token-1')
    let authorization = ''
    const response = await request.get('/shot-grid/navigation', {
      adapter: async config => {
        authorization = config.headers.Authorization
        return successAdapter({ code: 200, data: [{ routeKey: 'workbench' }] })(config)
      }
    })

    expect(authorization).toBe('Bearer token-1')
    expect(response.data).toEqual([{ routeKey: 'workbench' }])
  })

  it('业务失败不会丢失 errorKey 与详情', async () => {
    await expect(
      request.get('/conflict', {
        silentError: true,
        adapter: successAdapter({
          code: 409,
          msg: '数据已被修改',
          errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT',
          details: { expected: 3 }
        })
      })
    ).rejects.toMatchObject({
      status: 409,
      httpStatus: 200,
      errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT',
      details: { expected: 3 }
    })
  })

  it('并发 401 只触发一次会话失效处理', async () => {
    const handler = vi.fn(async () => Promise.resolve())
    setSessionExpiredHandler(handler)
    const config = {
      silentError: true,
      adapter: successAdapter({ code: 401, msg: '会话已过期' })
    }

    await Promise.allSettled([request.get('/identity', config), request.get('/navigation', config)])

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('重复提交保留稳定的 409 和客户端错误键', async () => {
    const adapter = successAdapter({ code: 200, data: { accepted: true } })
    await request.post('/projects', { projectName: '罗刹夫人' }, { adapter })

    await expect(request.post('/projects', { projectName: '罗刹夫人' }, { adapter })).rejects.toMatchObject({
      status: 409,
      errorKey: 'SG_CLIENT_REPEAT_SUBMIT'
    })
  })
})
