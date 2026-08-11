import { describe, expect, it } from 'vitest'

import { createShotGridRouter } from '@/router'

describe('任务与版本深层路由', () => {
  it('任务详情归属工作台，独立版本详情归属审核导航', () => {
    const router = createShotGridRouter()
    const taskRoute = router.getRoutes().find(route => route.name === 'task-detail')
    const versionRoute = router.getRoutes().find(route => route.name === 'version-detail')

    expect(taskRoute).toMatchObject({ path: '/tasks/:taskId', meta: { routeKey: 'workbench' } })
    expect(versionRoute).toMatchObject({ path: '/versions/:versionId', meta: { routeKey: 'reviews' } })
    expect(router.resolve('/tasks/31').name).toBe('task-detail')
    expect(router.resolve('/versions/41').name).toBe('version-detail')
  })
})
