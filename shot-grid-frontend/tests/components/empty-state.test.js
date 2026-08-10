import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('空状态组件提供语义化标题和可配置说明', async () => {
  const component = await readFile(new URL('../../src/components/EmptyState.vue', import.meta.url), 'utf8')
  assert.match(component, /<h2>\{\{ title \}\}<\/h2>/)
  assert.match(component, /<p>\{\{ description \}\}<\/p>/)
  assert.match(component, /required: true/)
})
