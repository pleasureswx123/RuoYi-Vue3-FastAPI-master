import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectDetail } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectScheduleView from '@/views/schedule/ProjectScheduleView.vue'
import { normalizeScheduleRouteQuery } from '@/views/schedule/scheduleRouteQuery'

vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  getProjectDetail: vi.fn()
}))

vi.mock('@/views/schedule/ScheduleBoard.vue', () => ({
  default: {
    name: 'ScheduleBoard',
    props: ['projectId', 'targetKind', 'initialMode', 'initialScale', 'initialGroupBy', 'initialWindowStart', 'initialWindowEnd', 'editableAllowed'],
    emits: ['query-change'],
    template: '<section data-testid="project-schedule-board" :data-editable="String(editableAllowed)" />'
  }
}))

const project = {
  projectId: 11,
  projectCode: 'LCFR',
  projectName: '罗刹夫人',
  projectStatus: 'active',
  myProjectRole: 'director'
}

async function mountView(path, permissions = ['shotgrid:task:list', 'shotgrid:task:schedule'], projectPatch = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin' }
  session.permissions = permissions
  getProjectDetail.mockResolvedValue({ data: { ...project, ...projectPatch } })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects/:projectId/schedule', name: 'project-schedule', component: ProjectScheduleView },
      { path: '/projects/:projectId/overview', name: 'project-overview', component: { template: '<div>项目详情</div>' } }
    ]
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ProjectScheduleView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await flushPromises()
  return { wrapper, router }
}

describe('项目排期深层页面', () => {
  beforeEach(() => vi.clearAllMocks())

  it('非法或缺失查询参数统一归一化为本月人员泳道周视图', async () => {
    const { wrapper, router } = await mountView('/projects/11/schedule?mode=invalid&scale=year&groupBy=unknown&windowStart=bad')

    expect(router.currentRoute.value.query).toEqual(normalizeScheduleRouteQuery({}))
    const board = wrapper.getComponent({ name: 'ScheduleBoard' })
    expect(board.props()).toMatchObject({
      projectId: 11,
      targetKind: 'all',
      initialMode: 'swimlane',
      initialScale: 'week',
      initialGroupBy: 'assignee',
      editableAllowed: true
    })
  })

  it('制作人员及已完成项目均保持只读，管理人活动项目才允许显式编辑', async () => {
    const creator = await mountView('/projects/11/schedule', ['shotgrid:task:list', 'shotgrid:task:schedule'], { myProjectRole: 'creator' })
    expect(creator.wrapper.getComponent({ name: 'ScheduleBoard' }).props('editableAllowed')).toBe(false)
    creator.wrapper.unmount()

    const completed = await mountView('/projects/11/schedule', ['shotgrid:task:list', 'shotgrid:task:schedule'], { projectStatus: 'completed' })
    expect(completed.wrapper.getComponent({ name: 'ScheduleBoard' }).props('editableAllowed')).toBe(false)
  })

  it('共享面板切换模式和时间窗口后写回可分享 URL', async () => {
    const { wrapper, router } = await mountView('/projects/11/schedule')
    wrapper.getComponent({ name: 'ScheduleBoard' }).vm.$emit('query-change', {
      mode: 'gantt',
      scale: 'month',
      groupBy: 'priority',
      windowStart: '2026-09-01T00:00:00',
      windowEnd: '2026-10-01T00:00:00'
    })
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({
      mode: 'gantt',
      scale: 'month',
      groupBy: 'priority',
      windowStart: '2026-09-01T00:00:00',
      windowEnd: '2026-10-01T00:00:00'
    })
  })
})
