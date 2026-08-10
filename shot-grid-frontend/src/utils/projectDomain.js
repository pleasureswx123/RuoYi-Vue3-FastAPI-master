export const PROJECT_STATUS = {
  preparing: { label: '筹备中', type: 'warning' },
  active: { label: '制作中', type: 'success' },
  completed: { label: '已完成', type: 'info' },
  archived: { label: '已归档', type: 'info' }
}

export const STORAGE_STATUS = {
  initializing: { label: '正在初始化', type: 'warning', description: '目录正在创建，仅可查看项目与维护成员。' },
  ready: { label: '存储就绪', type: 'success', description: '目录已就绪，可以导入和开展正式业务。' },
  failed: { label: '初始化失败', type: 'danger', description: '目录初始化失败，正式业务写入已暂停。' },
  migrating: { label: '正在迁移', type: 'warning', description: '存储正在迁移，正式业务写入已暂停。' }
}

export const PROJECT_CONFLICT_MESSAGES = {
  SG_PROJECT_CODE_CONFLICT: '项目代号已被使用，请更换后重试。',
  SG_STORAGE_PATH_CONFLICT: '该 NAS 项目路径已被占用，请修改目录名称。',
  SG_MEMBER_ALREADY_EXISTS: '该用户已经是项目成员。',
  SG_MEMBER_HAS_ACTIVE_TASKS: '成员仍有未完成任务，请先改派任务再移除。',
  SG_LAST_DIRECTOR_REQUIRED: '项目必须保留至少一名项目总监。',
  SG_PRODUCER_CODE_CONFLICT: '制作人缩写在项目内已被使用。',
  SG_PRODUCER_CODE_REQUIRED: '仍有未完成任务的成员不能清空制作人缩写。',
  SG_PROJECT_NOT_READY: '项目存储尚未就绪，暂不能执行正式业务写入。'
}

export function domainErrorMessage(error, fallback = '操作失败，请稍后重试。') {
  return PROJECT_CONFLICT_MESSAGES[error?.errorKey] || error?.message || fallback
}

export function createIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `sg-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function normalizeUserIds(value) {
  return [...new Set(String(value || '').split(/[，,\s]+/).filter(Boolean).map(Number).filter(Number.isInteger).filter((id) => id > 0))]
}

export function canWriteBusiness(storageStatus) {
  return storageStatus === 'ready'
}
