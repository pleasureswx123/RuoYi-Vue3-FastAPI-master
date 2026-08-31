import { describe, expect, it } from 'vitest'

import { createShotGridRouter } from '@/router'

describe('任务、版本与项目排期深层路由', () => {
  it('任务详情归属工作台，版本详情归属审核，项目排期归属项目导航', () => {
    const router = createShotGridRouter()
    const taskRoute = router.getRoutes().find(route => route.name === 'task-detail')
    const versionRoute = router.getRoutes().find(route => route.name === 'version-detail')
    const scheduleRoute = router.getRoutes().find(route => route.name === 'project-schedule')

    expect(taskRoute).toMatchObject({ path: '/tasks/:taskId', meta: { routeKey: 'workbench' } })
    expect(versionRoute).toMatchObject({ path: '/versions/:versionId', meta: { routeKey: 'reviews' } })
    expect(scheduleRoute).toMatchObject({ path: '/projects/:projectId/schedule', meta: { routeKey: 'projects' } })
    expect(router.resolve('/tasks/31').name).toBe('task-detail')
    expect(router.resolve('/versions/41').name).toBe('version-detail')
    expect(router.resolve('/projects/11/schedule').name).toBe('project-schedule')
  })
})
