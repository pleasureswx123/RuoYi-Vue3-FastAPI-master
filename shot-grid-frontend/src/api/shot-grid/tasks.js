import request from '@/utils/request'
import { assertPositiveId } from '@/api/shot-grid/projects'

function taskUrl(taskId, suffix = '') {
  return `/shot-grid/tasks/${assertPositiveId(taskId, '任务')}${suffix}`
}

export function getMineTaskPage(params, options = {}) {
  return request({
    url: '/shot-grid/tasks/mine',
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getProjectTaskPage(projectId, params, options = {}) {
  return request({
    url: `/shot-grid/projects/${assertPositiveId(projectId, '项目')}/tasks`,
    method: 'get',
    params,
    signal: options.signal,
    silentError: true
  })
}

export function getTaskDetail(taskId, options = {}) {
  return request({
    url: taskUrl(taskId),
    method: 'get',
    signal: options.signal,
    silentError: true
  })
}

export function updateTask(taskId, data) {
  return request({
    url: taskUrl(taskId),
    method: 'put',
    data,
    silentError: true
  })
}

export function startTask(taskId, data) {
  return request({
    url: taskUrl(taskId, '/start'),
    method: 'post',
    data,
    silentError: true
  })
}
