import { ElButton, ElIcon } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectListView from '@/views/project/ProjectListView.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  getProjectPage: vi.fn()
}))

const projectRow = {
  projectId: 8,
  projectCode: 'LCFR',
  projectName: '罗刹夫人',
  projectTypeName: 'AI 影视短片',
  aspectRatio: '16:9',
  projectStatus: 'active',
  storageStatus: 'ready',
  myProjectRole: 'director',
  currentPhase: 'shot_production',
  completedShots: 12,
  totalShots: 30,
  completedAssets: 4,
  totalAssets: 7,
  plannedDurationMs: 5_400_000,
  overallProgress: 40
}

async function mountProjectList(permissions = []) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin', nickName: '管理员', dept: null }
  session.permissions = permissions
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects', component: ProjectListView },
      { path: '/projects/:projectId/overview', component: { template: '<div>详情</div>' } }
    ]
  })
  await router.push('/projects')
  await router.isReady()
  const wrapper = mount(ProjectListView, {
    global: { plugins: [pinia, router], components: { ElButton, ElIcon } }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('项目管理页面', () => {
  beforeEach(() => {
    getProjectPage.mockResolvedValue({ rows: [projectRow], total: 1, hasNext: false })
  })

  it('展示真实范围列表并按接口权限显示创建入口', async () => {
    const { wrapper } = await mountProjectList(['shotgrid:project:add'])

    expect(wrapper.text()).toContain('罗刹夫人')
    expect(wrapper.text()).toContain('创建项目')
    expect(wrapper.text()).toContain('12/30')
    wrapper.unmount()
  })

  it('没有 project:add 权限时不渲染创建动作', async () => {
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])

    expect(wrapper.text()).not.toContain('创建项目')
    wrapper.unmount()
  })

  it('403 不会伪装成空列表', async () => {
    getProjectPage.mockRejectedValue({ httpStatus: 403, message: '无权查看全部项目' })
    const { wrapper } = await mountProjectList(['shotgrid:project:list'])

    expect(wrapper.text()).toContain('没有项目访问权限')
    expect(wrapper.text()).toContain('无权查看全部项目')
    expect(wrapper.text()).not.toContain('当前范围暂无项目')
    wrapper.unmount()
  })
})
