import assert from 'node:assert/strict'
import test from 'node:test'
import { createLatestRequest } from '../../src/utils/latestRequest.js'

test('过期搜索响应不会覆盖最新响应且旧请求被取消', async () => {
  const gate = createLatestRequest()
  let release
  const first = gate.run(signal => new Promise(resolve => { release = () => resolve({ old: true }); signal.addEventListener('abort', release) }))
  const second = gate.run(async () => ({ newest: true }))
  assert.deepEqual(await second, { accepted: true, value: { newest: true } })
  assert.deepEqual(await first, { accepted: false })
})
