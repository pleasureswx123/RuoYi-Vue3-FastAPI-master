import assert from 'node:assert/strict'
import test from 'node:test'

import { PRODUCTION_STATUS, productionStatusMeta, productionStatusOptions } from '../../src/utils/productionStatus.js'

test('镜头、资产和任务共享冻结的六态代码与中文映射', () => {
  assert.deepEqual(Object.keys(PRODUCTION_STATUS), [
    'no_task', 'not_started', 'in_progress', 'pending_review', 'revision', 'completed'
  ])
  assert.deepEqual(productionStatusOptions.map(item => item.label), [
    '无任务', '未开始', '制作中', '待审核', '修改中', '已完成'
  ])
  assert.equal(productionStatusMeta('pending_review').label, '待审核')
})

test('未知后端状态不会被错误展示成未开始', () => {
  assert.equal(productionStatusMeta('future_status').label, 'future_status')
  assert.equal(productionStatusMeta().label, '未知状态')
})
