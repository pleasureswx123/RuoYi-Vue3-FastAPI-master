import test from 'node:test'
import assert from 'node:assert/strict'
import { classifyImportCommitError, getOrCreateImportOperation, selectableRows, toSelectedRows } from '../../src/utils/importWorkflow.js'

function memoryStorage() { const values = new Map(); return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) } }

test('多 Sheet 的相同行号使用完整复合身份提交', () => {
  assert.deepEqual(toSelectedRows([
    { sheetName: 'EP001', rowNumber: 2, canImport: true, errors: [] },
    { sheetName: 'EP002', rowNumber: 2, canImport: true, errors: [] }
  ]), [{ sheetName: 'EP001', rowNumber: 2 }, { sheetName: 'EP002', rowNumber: 2 }])
})

test('warning 行可提交而 error 行不可提交', () => {
  const rows = [
    { sheetName: 'Sheet1', rowNumber: 2, canImport: true, warnings: [{ errorKey: 'SG_ASSET_PRODUCTION_ITEM_MISSING' }], errors: [] },
    { sheetName: 'Sheet1', rowNumber: 3, canImport: false, warnings: [], errors: [{ errorKey: 'SG_IMPORT_FIELD_REQUIRED' }] }
  ]
  assert.deepEqual(selectableRows(rows).map((row) => row.rowNumber), [2])
})

test('网络超时重试持久复用同一幂等键和全事务选择集', () => {
  const storage = memoryStorage(), input = { projectId: 7, importType: 'shot', batchId: 9, selectedRows: [{ sheetName: 'EP001', rowNumber: 2 }] }
  const first = getOrCreateImportOperation(storage, input)
  const retry = getOrCreateImportOperation(storage, { ...input, selectedRows: [{ sheetName: 'EP001', rowNumber: 99 }] })
  assert.equal(retry.idempotencyKey, first.idempotencyKey)
  assert.deepEqual(retry.selectedRows, input.selectedRows)
})

test('全事务提交选择不会丢弃任一合法行', () => {
  const rows = Array.from({ length: 3 }, (_, index) => ({ sheetName: 'EP001', rowNumber: index + 2, canImport: true, errors: [] }))
  assert.equal(toSelectedRows(rows).length, 3)
})

test('Token 过期要求重新预检，409 保留为具体冲突', () => {
  assert.deepEqual(classifyImportCommitError({ status: 410, errorKey: 'SG_IMPORT_TOKEN_EXPIRED' }), { tokenExpired: true, conflict: false })
  assert.deepEqual(classifyImportCommitError({ status: 409, errorKey: 'SG_IMPORT_DATABASE_CONFLICT' }), { tokenExpired: false, conflict: true })
})
