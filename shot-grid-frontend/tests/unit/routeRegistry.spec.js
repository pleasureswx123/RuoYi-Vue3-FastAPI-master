import { describe, expect, it } from 'vitest'

import {
  getFirstAuthorizedPath,
  getRouteKeyByPath,
  normalizeNavigation,
  sanitizeInternalRedirect,
  SHOT_GRID_ROUTE_KEYS
} from '@/router/routeRegistry'

const serverNavigation = [
  { routeKey: 'files', title: '文件与 NAS', path: '/files', icon: 'folder-opened', orderNum: 6 },
  { routeKey: 'workbench', title: '工作台', path: '/workbench', icon: 'dashboard', orderNum: 1 },
  { routeKey: 'projects', title: '项目', path: '/projects', icon: 'project', orderNum: 2 },
  { routeKey: 'shots', title: '镜头管理', path: '/shots', icon: 'video-camera', orderNum: 3 },
  { routeKey: 'assets', title: '资产库管理', path: '/assets', icon: 'picture', orderNum: 4 },
  { routeKey: 'reviews', title: '版本审核', path: '/reviews', icon: 'eye-open', orderNum: 5 }
]

describe('Shot Grid 本地路由白名单', () => {
  it('兼容原导航并接受每日记录和统计的稳定键', () => {
    const navigation = normalizeNavigation(serverNavigation)

    expect(navigation.map(item => item.routeKey)).toEqual(['workbench', 'projects', 'shots', 'assets', 'reviews', 'files'])
    expect(SHOT_GRID_ROUTE_KEYS).toContain('daily-records')
    expect(SHOT_GRID_ROUTE_KEYS).toContain('production-statistics')
    expect(normalizeNavigation([{routeKey: 'daily-records', path: '/daily-records'}, {routeKey: 'production-statistics', path: '/production-statistics'}])).toHaveLength(2)
    expect(getFirstAuthorizedPath(navigation)).toBe('/projects')
    expect(getRouteKeyByPath('/reviews')).toBe('reviews')
    expect(getRouteKeyByPath('/projects/11/schedule')).toBe('projects')
  })

  it('拒绝未知键、重复键和路径注入', () => {
    const navigation = normalizeNavigation([
      serverNavigation[1],
      { ...serverNavigation[1], title: '伪造工作台' },
      { routeKey: 'system', title: '系统管理', path: '/system', orderNum: 0 },
      { routeKey: '__proto__', title: '原型注入', orderNum: 0 },
      { routeKey: 'constructor', title: '构造器注入', orderNum: 0 },
      { routeKey: 'projects', title: '项目', path: '/admin/users', orderNum: 2 }
    ])

    expect(navigation).toHaveLength(1)
    expect(navigation[0].title).toBe('工作台')
  })

  it('只保留站内 redirect', () => {
    expect(sanitizeInternalRedirect('/shots?status=doing')).toBe('/shots?status=doing')
    expect(sanitizeInternalRedirect('//evil.example/path', '/workbench')).toBe('/workbench')
    expect(sanitizeInternalRedirect('https://evil.example/path', '/workbench')).toBe('/workbench')
    expect(sanitizeInternalRedirect('/\\evil.example', '/workbench')).toBe('/workbench')
  })
})
