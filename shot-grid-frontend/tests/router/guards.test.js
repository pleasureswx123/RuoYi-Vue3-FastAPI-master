import test from 'node:test'
import assert from 'node:assert/strict'
import { createNavigationGuard, isValidRouteId } from '../../src/router/guards.js'

const target = (overrides = {}) => ({ name: 'Workbench', fullPath: '/workbench', params: {}, meta: { navigationKey: 'workbench' }, ...overrides })
const dependencies = (overrides = {}) => ({
  getToken: () => 'token',
  userStore: { restored: false, restore: async () => true },
  navigationStore: { loaded: false, entries: [], rejectedRouteKeys: [], load: async () => {}, hasRoute: () => true },
  clearProjectResources: () => {},
  ...overrides
})

test('未登录时保留刷新目标并跳转登录页', async () => {
  const guard = createNavigationGuard(dependencies({ getToken: () => null }))
  assert.deepEqual(await guard(target()), { name: 'Login', query: { redirect: '/workbench' } })
})

test('刷新恢复先获取用户信息再加载导航', async () => {
  const calls = []
  const guard = createNavigationGuard(dependencies({
    userStore: { restored: false, restore: async () => { calls.push('getInfo'); return true } },
    navigationStore: { loaded: false, load: async () => calls.push('navigation'), hasRoute: () => true }
  }))
  assert.equal(await guard(target()), true)
  assert.deepEqual(calls, ['getInfo', 'navigation'])
})

test('无菜单权限拒绝业务页面', async () => {
  const guard = createNavigationGuard(dependencies({ navigationStore: { loaded: true, hasRoute: () => false } }))
  assert.deepEqual(await guard(target()), { name: 'Forbidden' })
})

test('后端仅返回未知路由键时跳转功能不可用页', async () => {
  const navigationStore = { loaded: true, entries: [], rejectedRouteKeys: ['unknown'], hasRoute: () => false }
  const guard = createNavigationGuard(dependencies({ navigationStore }))
  assert.deepEqual(await guard(target()), { name: 'FeatureUnavailable' })
})

test('登录过期进入明确的会话失效页', async () => {
  const guard = createNavigationGuard(dependencies({ userStore: { restored: false, restore: async () => { throw { status: 401 } } } }))
  assert.deepEqual(await guard(target()), { name: 'SessionExpired' })
})

test('详情路由参数只接受正整数标识', async () => {
  assert.equal(isValidRouteId('42'), true)
  assert.equal(isValidRouteId('../42'), false)
  const guard = createNavigationGuard(dependencies())
  assert.deepEqual(await guard(target({ name: 'ShotDetail', params: { shotId: 'bad-id' } })), { name: 'NotFound' })
})

test('项目切换和离开项目均清理旧项目资源', async () => {
  let cleared = 0
  const guard = createNavigationGuard(dependencies({ clearProjectResources: () => cleared++ }))
  await guard(target({ name: 'ProjectOverview', params: { projectId: '1' }, meta: { navigationKey: 'projects' } }))
  await guard(target({ name: 'ProjectOverview', params: { projectId: '2' }, meta: { navigationKey: 'projects' } }))
  await guard(target())
  assert.equal(cleared, 2)
})
