import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveNavigation } from '../../src/router/navigation.js'

test('导航解析只接受六个稳定路由键并按顺序排列', () => {
  const warnings = []
  const result = resolveNavigation([
    { routeKey: 'projects', title: '项目', path: '/system/user', orderNum: 2 },
    { routeKey: 'workbench', title: '工作台', orderNum: 1 },
    { routeKey: 'system-user', title: '用户管理', orderNum: 0 }
  ], (key) => warnings.push(key))
  assert.deepEqual(result.entries.map(({ routeKey, path }) => ({ routeKey, path })), [
    { routeKey: 'workbench', path: '/workbench' },
    { routeKey: 'projects', path: '/projects' }
  ])
  assert.deepEqual(result.rejected, ['system-user'])
  assert.deepEqual(warnings, ['system-user'])
})

test('无菜单权限时解析为空导航', () => {
  assert.deepEqual(resolveNavigation([]).entries, [])
})
