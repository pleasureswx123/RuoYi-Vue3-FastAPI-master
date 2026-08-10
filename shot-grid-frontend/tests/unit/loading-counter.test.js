import assert from 'node:assert/strict'
import test from 'node:test'
import { createLoadingCounter } from '../../src/utils/loadingCounter.js'

test('并发请求全部结束后计数归零且不会成为负数', () => {
  const counter = createLoadingCounter()
  counter.begin()
  counter.begin()
  counter.end()
  assert.equal(counter.value(), 1)
  counter.end()
  counter.end()
  assert.equal(counter.value(), 0)
})
