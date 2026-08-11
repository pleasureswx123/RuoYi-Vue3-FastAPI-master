import assert from 'node:assert/strict'
import test from 'node:test'
import { createObjectUrlOwner } from '../../src/components/media/objectUrl.js'

test('替换和释放媒体时回收全部 Object URL', () => {
  const revoked = []
  const api = { createObjectURL: blob => `blob:${blob}`, revokeObjectURL: url => revoked.push(url) }
  const owner = createObjectUrlOwner(api)
  assert.equal(owner.replace('one'), 'blob:one')
  assert.equal(owner.replace('two'), 'blob:two')
  owner.release()
  owner.release()
  assert.deepEqual(revoked, ['blob:one', 'blob:two'])
})
