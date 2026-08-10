import assert from 'node:assert/strict'
import test from 'node:test'
import { getErrorDetails, parseBlobError, parseResponseEnvelope } from '../../src/utils/requestErrors.js'
import { createSingleFlight } from '../../src/utils/singleFlight.js'
import { shouldEncryptRequest } from '../../src/utils/transportCryptoPolicy.js'
import { shouldRetryTransportWithFreshKey } from '../../src/utils/transportCrypto.js'

const activePolicy = { transportCryptoActive: true, enabledPaths: [], excludePaths: ['/common/files', '/shot-grid/media'], requiredPaths: ['/login'] }

test('公开下载和 Range 媒体请求保持明文，普通鉴权请求仍加密', () => {
  assert.equal(shouldEncryptRequest({ url: '/common/files/1/download/a.mp4', headers: {} }, activePolicy), false)
  assert.equal(shouldEncryptRequest({ url: '/shot-grid/media/1', headers: { Range: 'bytes=0-99' } }, activePolicy), false)
  assert.equal(shouldEncryptRequest({ url: '/getInfo', headers: { Authorization: 'Bearer test-token' } }, activePolicy), true)
})

test('必须加密路径启用加密决策，二进制响应保持明文', () => {
  assert.equal(shouldEncryptRequest({ url: '/login', method: 'post', headers: {}, data: {} }, activePolicy), true)
  assert.equal(shouldEncryptRequest({ url: '/shot-grid/projects', responseType: 'blob', headers: {} }, activePolicy), false)
})

test('密钥过期允许刷新，重试标记将上限约束为一次', () => {
  const expired = { response: { data: { msg: '密钥版本不存在' } }, config: {} }
  assert.equal(shouldRetryTransportWithFreshKey(expired), true)
  assert.equal(Boolean(shouldRetryTransportWithFreshKey(expired) && !expired.config.__transportRetried), true)
  expired.config.__transportRetried = true
  assert.equal(Boolean(shouldRetryTransportWithFreshKey(expired) && !expired.config.__transportRetried), false)
  assert.equal(shouldRetryTransportWithFreshKey({ response: { data: { msg: '普通错误' } } }), false)
})

test('401 并发响应共享一次退出处理', async () => {
  let calls = 0
  const handle401 = createSingleFlight(async () => { calls += 1; await Promise.resolve(); return 'cleared' })
  assert.deepEqual(await Promise.all([handle401(), handle401(), handle401()]), ['cleared', 'cleared', 'cleared'])
  assert.equal(calls, 1)
})

test('统一 envelope 保留业务冲突，不把服务失败转换为空列表', () => {
  assert.deepEqual(parseResponseEnvelope({ code: 200, msg: '成功', data: [1] }), [1])
  assert.throws(() => parseResponseEnvelope({ code: 409, msg: '版本冲突', data: { version: 2 } }), (error) => {
    assert.equal(error.code, 409)
    assert.equal(error.message, '版本冲突')
    assert.deepEqual(error.payload, { version: 2 })
    return true
  })
  assert.equal(getErrorDetails({ response: { status: 500, data: {} } }).message, '服务暂时不可用，请稍后重试')
})

test('Blob JSON 错误响应解析出状态和服务端消息', async () => {
  const details = await parseBlobError(new Blob([JSON.stringify({ code: 416, msg: 'RangeNotSatisfiable' })], { type: 'application/json' }), 416)
  assert.equal(details.status, 416)
  assert.equal(details.message, '媒体请求范围无效，请重新加载媒体')
  assert.equal(details.body.msg, 'RangeNotSatisfiable')
})
