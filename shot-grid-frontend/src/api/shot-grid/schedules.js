import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function projectScheduleUrl(projectId, suffix = '') {
  return `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/schedule${suffix}`
}

function taskScheduleUrl(taskId, suffix = '') {
  return `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}${suffix}`
}

export function getProjectSchedule(projectId, params, options = {}) {
  return request({
    url: projectScheduleUrl(projectId),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getUnscheduledScheduleTasks(projectId, params, options = {}) {
  return request({
    url: projectScheduleUrl(projectId, '/unscheduled'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getTaskScheduleChanges(taskId, params, options = {}) {
  return request({
    url: taskScheduleUrl(taskId, '/schedule-changes'),
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function updateTaskSchedule(taskId, data, idempotencyKey) {
  const stableKey = typeof idempotencyKey === 'string' ? idempotencyKey.trim() : ''
  if (!stableKey) {
    throw new Error('幂等键不能为空')
  }
  return request({
    url: taskScheduleUrl(taskId, '/schedule'),
    method: 'put',
    data,
    headers: { 'X-Idempotency-Key': stableKey },
    repeatSubmit: false,
    silentError: true
  })
}
