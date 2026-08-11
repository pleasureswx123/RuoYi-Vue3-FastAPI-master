import assert from 'node:assert/strict'
import test from 'node:test'
import { createLatestPreview, hasDirector, uniqueUserIds } from '../../src/utils/projectCreation.js'

test('至少一名总监校验并去重用户', () => {
  assert.equal(hasDirector([]), false)
  assert.equal(hasDirector([8, 8]), true)
  assert.deepEqual(uniqueUserIds([8, '8', 0, 9]), [8, 9])
})

test('路径预览只接纳最后一次请求结果', async () => {
  const values = []
  const preview = createLatestPreview((value) => values.push(value), (error) => { throw error })
  let release
  const first = preview.run(() => new Promise((resolve) => { release = resolve }))
  await preview.run(async () => 'new')
  release('old')
  await first
  assert.deepEqual(values, ['new'])
})
