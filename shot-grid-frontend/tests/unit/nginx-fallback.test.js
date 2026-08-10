import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('Nginx 将 Shot Grid 深层路由回退到应用入口', async () => {
  const config = await readFile(new URL('../../nginx.conf', import.meta.url), 'utf8')
  assert.match(config, /location \/shot-grid\/\s*\{[\s\S]*try_files \$uri \$uri\/ \/shot-grid\/index\.html;/)
})
