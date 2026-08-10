import assert from 'node:assert/strict'
import test from 'node:test'
import { canWriteBusiness, createIdempotencyKey, domainErrorMessage, normalizeUserIds } from '../../src/utils/projectDomain.js'

test('项目表单规范化总监用户并去重', () => {
  assert.deepEqual(normalizeUserIds('12, 7，12 invalid -1'), [12, 7])
  assert.deepEqual(normalizeUserIds(''), [])
})

test('每次项目提交生成独立幂等键', () => {
  const first = createIdempotencyKey()
  const second = createIdempotencyKey()
  assert.ok(first)
  assert.notEqual(first, second)
})

test('成员和项目冲突使用稳定 errorKey 文案', () => {
  assert.match(domainErrorMessage({ errorKey: 'SG_PROJECT_CODE_CONFLICT' }), /项目代号/)
  assert.match(domainErrorMessage({ errorKey: 'SG_STORAGE_PATH_CONFLICT' }), /NAS 项目路径/)
  assert.match(domainErrorMessage({ errorKey: 'SG_LAST_DIRECTOR_REQUIRED' }), /至少一名项目总监/)
  assert.match(domainErrorMessage({ errorKey: 'SG_PRODUCER_CODE_CONFLICT' }), /制作人缩写/)
  assert.match(domainErrorMessage({ errorKey: 'SG_MEMBER_HAS_ACTIVE_TASKS' }), /未完成任务/)
})

test('只有 ready 存储状态允许正式业务写入', () => {
  assert.equal(canWriteBusiness('ready'), true)
  for (const status of ['initializing', 'failed', 'migrating', undefined]) assert.equal(canWriteBusiness(status), false)
})
