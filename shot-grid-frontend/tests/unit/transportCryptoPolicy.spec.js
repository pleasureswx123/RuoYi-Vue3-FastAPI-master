import { describe, expect, it } from 'vitest'

import {
  shouldEncryptQuery,
  shouldEncryptRequest,
  shouldEncryptResponse
} from '@/utils/transportCryptoPolicy'

const activePolicy = {
  transportCryptoActive: true,
  enabledPaths: ['/login', '/getInfo', '/shot-grid'],
  requiredPaths: ['/login'],
  excludePaths: ['/common/files/']
}

describe('传输加密策略适配', () => {
  it('后端明确关闭传输加密时不访问浏览器 Web Crypto 链路', () => {
    const offPolicy = {
      transportCryptoActive: false,
      enabledPaths: ['/login', '/getInfo', '/shot-grid'],
      requiredPaths: ['/login'],
      excludePaths: []
    }
    const config = { url: '/login', method: 'post', headers: {} }

    expect(shouldEncryptRequest(config, offPolicy)).toBe(false)
    expect(shouldEncryptQuery(config, offPolicy)).toBe(false)
    expect(shouldEncryptResponse(config, offPolicy)).toBe(false)
  })

  it('业务 JSON 请求与查询遵循后端路径策略', () => {
    const config = { url: '/shot-grid/navigation', method: 'get', headers: {} }

    expect(shouldEncryptRequest(config, activePolicy)).toBe(true)
    expect(shouldEncryptQuery(config, activePolicy)).toBe(true)
    expect(shouldEncryptResponse(config, activePolicy)).toBe(true)
  })

  it('受保护文件与二进制响应不进入应用层加密', () => {
    expect(shouldEncryptRequest({ url: '/common/files/upload', method: 'post', headers: {} }, activePolicy)).toBe(false)
    expect(
      shouldEncryptRequest(
        { url: '/shot-grid/tasks/1/version-submissions', method: 'post', headers: { 'Content-Type': 'multipart/form-data' } },
        activePolicy
      )
    ).toBe(false)
    expect(
      shouldEncryptResponse({ url: '/shot-grid/versions/1/files/2/download', responseType: 'blob', headers: {} }, activePolicy)
    ).toBe(false)
  })
})
