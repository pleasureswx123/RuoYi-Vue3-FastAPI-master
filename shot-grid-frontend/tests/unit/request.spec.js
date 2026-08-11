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

function acceptedAdapter(data) {
  return async config => ({ data, status: 202, statusText: 'Accepted', headers: {}, config, request: {} })
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

  it('接受真实 HTTP 202 与 code 202 的异步受理响应', async () => {
    const response = await request.post(
      '/shot-grid/projects',
      { projectCode: 'LCFR' },
      {
        headers: { repeatSubmit: false },
        adapter: acceptedAdapter({
          code: 202,
          success: true,
          data: { projectId: 8, storageStatus: 'initializing' }
        })
      }
    )

    expect(response.data).toEqual({ projectId: 8, storageStatus: 'initializing' })
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

  it('二进制请求的 JSON Blob 错误仍保留 errorKey 与详情', async () => {
    await expect(request.get('/shot-grid/versions/7/files/file-id/download', {
      responseType: 'blob',
      silentError: true,
      adapter: async config => {
        const error = new Error('Request failed with status code 416')
        error.config = config
        error.response = {
          status: 416,
          statusText: 'Range Not Satisfiable',
          headers: { 'content-type': 'application/json; charset=utf-8' },
          config,
          data: new Blob([JSON.stringify({
            code: 416,
            msg: '媒体分段范围无效',
            errorKey: 'SG_FILE_RANGE_NOT_SATISFIABLE',
            details: { fileSize: 1024 }
          })], { type: 'application/json' })
        }
        throw error
      }
    })).rejects.toMatchObject({
      status: 416,
      httpStatus: 416,
      errorKey: 'SG_FILE_RANGE_NOT_SATISFIABLE',
      details: { fileSize: 1024 }
    })
  })
})
