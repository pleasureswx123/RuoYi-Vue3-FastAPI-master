import { describe, expect, it } from 'vitest'

import { ApiError, createApiError } from '@/utils/apiError'

describe('ApiError', () => {
  it('保留真实 HTTP 状态、业务码、稳定错误键与详情', () => {
    const error = createApiError({
      status: 409,
      data: {
        code: 409,
        msg: '版本冲突',
        errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT',
        data: { lockVersion: 4 },
        details: { expected: 3 }
      }
    })

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      httpStatus: 409,
      code: 409,
      errorKey: 'SG_OPTIMISTIC_LOCK_CONFLICT',
      data: { lockVersion: 4 },
      details: { expected: 3 }
    })
  })

  it('兼容 HTTP 200 但业务失败的基座响应', () => {
    const error = createApiError({
      status: 200,
      data: { code: 403, msg: '无权访问', data: { errorKey: 'SG_PROJECT_ACCESS_DENIED' } }
    })

    expect(error.httpStatus).toBe(200)
    expect(error.status).toBe(403)
    expect(error.code).toBe(403)
    expect(error.errorKey).toBe('SG_PROJECT_ACCESS_DENIED')
  })
})
