export const PRODUCTION_STATUS = Object.freeze({
  no_task: Object.freeze({ label: '无任务', type: 'info' }),
  not_started: Object.freeze({ label: '未开始', type: 'info' }),
  in_progress: Object.freeze({ label: '制作中', type: 'primary' }),
  pending_review: Object.freeze({ label: '待审核', type: 'warning' }),
  revision: Object.freeze({ label: '修改中', type: 'danger' }),
  completed: Object.freeze({ label: '已完成', type: 'success' })
})

export const productionStatusOptions = Object.freeze(
  Object.entries(PRODUCTION_STATUS).map(([value, meta]) => Object.freeze({ value, label: meta.label }))
)

export function productionStatusMeta(status) {
  return PRODUCTION_STATUS[status] || Object.freeze({ label: status || '未知状态', type: 'info' })
}
