const STORAGE_PREFIX = 'shot-grid:import-operation:'

export const rowIdentity = (row) => `${row.sheetName}\u0000${row.rowNumber}`

export function selectableRows(rows) {
  return rows.filter((row) => row.canImport === true && !(row.errors?.length))
}

export function toSelectedRows(rows) {
  return selectableRows(rows).map(({ sheetName, rowNumber }) => ({ sheetName, rowNumber }))
}

export function createIdempotencyKey() {
  const uuid = globalThis.crypto?.randomUUID?.()
  return `sg-import-${uuid || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`
}

const operationKey = (projectId, importType, batchId) =>
  `${STORAGE_PREFIX}${projectId}:${importType}:${batchId}`

export function getOrCreateImportOperation(storage, { projectId, importType, batchId, selectedRows }) {
  const key = operationKey(projectId, importType, batchId)
  const selection = selectedRows.map(({ sheetName, rowNumber }) => ({ sheetName, rowNumber }))
  const existing = JSON.parse(storage.getItem(key) || 'null')
  if (existing) return existing
  const operation = { idempotencyKey: createIdempotencyKey(), batchId, selectedRows: selection }
  storage.setItem(key, JSON.stringify(operation))
  return operation
}

export function saveLastCommittedBatch(storage, projectId, batchId) {
  storage.setItem(`${STORAGE_PREFIX}last:${projectId}`, String(batchId))
}

export function getLastCommittedBatch(storage, projectId) {
  const value = Number(storage.getItem(`${STORAGE_PREFIX}last:${projectId}`))
  return Number.isSafeInteger(value) && value > 0 ? value : null
}

export function classifyImportCommitError(details) {
  return {
    tokenExpired: details.status === 410 || details.errorKey === 'SG_IMPORT_TOKEN_EXPIRED',
    conflict: details.status === 409
  }
}
