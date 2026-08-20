import { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElRadioButton, ElRadioGroup, ElSkeleton, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectPage } from '@/api/shot-grid/projects'
import {
  addVersionIssue,
  createManualReviewList,
  createReviewAction,
  getReviewActions,
  getReviewListDetail,
  getReviewListPage,
  getVersionReviewContext
} from '@/api/shot-grid/reviews'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import { downloadProtectedThumbnail } from '@/api/shot-grid/shots'
import { useSessionStore } from '@/store/modules/session'
import ReviewDetailView from '@/views/review/ReviewDetailView.vue'
import ReviewListView from '@/views/review/ReviewListView.vue'
import ManualReviewDialog from '@/views/review/components/ManualReviewDialog.vue'

vi.mock('@/api/shot-grid/projects', () => ({
  assertPositiveId: value => {
    const result = Number(value)
    if (!Number.isSafeInteger(result) || result <= 0) throw new TypeError('ID 无效')
    return result
  },
  getProjectPage: vi.fn()
}))
vi.mock('@/api/shot-grid/reviews', () => ({
  addVersionIssue: vi.fn(),
  createManualReviewList: vi.fn(),
  createReviewAction: vi.fn(),
  getReviewActions: vi.fn(),
  getReviewListDetail: vi.fn(),
  getReviewListPage: vi.fn(),
  getVersionReviewContext: vi.fn(),
  transitionManualReviewList: vi.fn()
}))
vi.mock('@/api/shot-grid/versions', () => ({
  downloadProtectedVersionFile: vi.fn(),
  getTaskVersions: vi.fn(),
  getVersionDetail: vi.fn()
}))
vi.mock('@/api/shot-grid/shots', () => ({
  downloadProtectedThumbnail: vi.fn()
}))

const project = { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人' }
const ElSelectStub = { name: 'ElSelect', template: '<div class="el-select-stub" />' }
const review = {
  reviewListId: 101,
  projectId: 8,
  reviewListName: '动力舱合成 V003 审核',
  description: '自动单版本审核单',
  reviewDate: '2026-08-12',
  reviewMode: 'auto_single',
  reviewStatus: 'active',
  autoVersionId: 33,
  taskId: 21,
  versionNo: 3,
  versionNumber: 'V003',
  versionStatus: 'pending_review',
  thumbnail: { fileId: '5ed39e04-2f29-45ab-a58c-4f8168f5131a', url: '/shot-grid/versions/33/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download' },
  mediaDerivationStatus: 'completed',
  lockVersion: 0,
  createTime: '2026-08-12T10:00:00'
}
const version = {
  versionId: 33,
  projectId: 8,
  taskId: 21,
  versionNo: 3,
  versionNumber: 'V003',
  versionStatus: 'pending_review',
  changelog: '补充舱体冷凝效果',
  submittedBy: 7,
  submitterName: '制作人甲',
  submittedTime: '2026-08-12T09:30:00',
  lockVersion: 2,
  files: [],
  aiParams: null,
  autoReviewList: { reviewListId: 101, reviewListName: review.reviewListName }
}
function installSession(permissions) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.user = { userId: 1, userName: 'admin', nickName: '管理员' }
  session.permissions = permissions
  return pinia
}

async function mountList() {
  const pinia = installSession(['shotgrid:project:list', 'shotgrid:reviewList:list'])
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reviews', component: ReviewListView },
      { path: '/reviews/:reviewListId', component: { template: '<div>审核详情占位</div>' } }
    ]
  })
  await router.push('/reviews')
  await router.isReady()
  const wrapper = mount(ReviewListView, { global: { plugins: [pinia, router], components: { ElButton, ElIcon, ElTag } } })
  await flushPromises()
  return { wrapper, router }
}

async function mountDetail(permissions = ['shotgrid:reviewList:query', 'shotgrid:version:query', 'shotgrid:version:review', 'shotgrid:note:list']) {
  const pinia = installSession(permissions)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reviews', component: { template: '<div>审核列表</div>' } },
      { path: '/reviews/:reviewListId', component: ReviewDetailView },
      { path: '/tasks/:taskId', component: { template: '<div>任务修订</div>' } }
    ]
  })
  await router.push('/reviews/101')
  await router.isReady()
  const wrapper = mount(ReviewDetailView, {
    global: {
      plugins: [pinia, router],
      components: { ElAlert, ElButton, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElRadioButton, ElRadioGroup, ElSkeleton, ElTag }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('版本审核页面', () => {
  beforeEach(() => {
    getProjectPage.mockResolvedValue({ rows: [project], total: 1 })
    getReviewListPage.mockResolvedValue({ rows: [review], total: 1 })
    getReviewListDetail.mockResolvedValue({ data: { ...review, version } })
    getVersionDetail.mockResolvedValue({ data: version })
    getVersionReviewContext.mockResolvedValue({ data: { currentVersion: version, carriedIssues: [], currentVersionIssues: [] } })
    getReviewActions.mockResolvedValue({ rows: [], total: 0 })
    getTaskVersions.mockResolvedValue({ rows: [], total: 0 })
    downloadProtectedThumbnail.mockResolvedValue(new Blob(['thumbnail'], { type: 'image/jpeg' }))
    addVersionIssue.mockResolvedValue({ data: { issueId: 502 } })
    createManualReviewList.mockResolvedValue({ data: { reviewListId: 202 } })
    createReviewAction.mockResolvedValue({ data: { actionId: 901 } })
  })

  it('按项目加载自动审核单并进入真实详情路由', async () => {
    const { wrapper, router } = await mountList()

    expect(getReviewListPage).toHaveBeenCalledWith('8', expect.objectContaining({ reviewStatus: undefined }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('动力舱合成 V003 审核')
    expect(wrapper.text()).toContain('预览已优化')
    const tags = wrapper.find('.review-card').findAllComponents(ElTag)
    expect(tags.map(tag => tag.text())).toEqual(['自动单版', '待审核', '预览已优化', '待审核'])
    expect(tags.map(tag => tag.props('type'))).toEqual(['primary', 'warning', 'success', 'warning'])
    tags.slice(0, 3).forEach(tag => expect(tag.props()).toMatchObject({ effect: 'plain', size: 'small', round: true }))
    expect(tags[3].props()).toMatchObject({ effect: 'light', size: 'small', round: true })
    await wrapper.find('.review-card').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/reviews/101')
    wrapper.unmount()
  })

  it('加载版本、意见和动作历史，并使用版本锁提交通过决定', async () => {
    const { wrapper } = await mountDetail()

    expect(getReviewListDetail).toHaveBeenCalledWith(101, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(getVersionDetail).toHaveBeenCalledWith(33, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('补充舱体冷凝效果')
    const headingTags = wrapper.find('.heading-actions').findAllComponents(ElTag)
    expect(headingTags.map(tag => tag.text())).toEqual(['自动单版', '待审核'])
    expect(headingTags[0].props()).toMatchObject({ type: 'primary', effect: 'plain', size: 'small', round: true })
    expect(headingTags[1].props()).toMatchObject({ type: 'warning', effect: 'light', size: 'small', round: true })

    const approveButton = wrapper.findAll('button').find(button => button.text().includes('确认通过'))
    await approveButton.trigger('click')
    await flushPromises()

    expect(createReviewAction).toHaveBeenCalledWith(33, {
      actionType: 'approve',
      reason: null,
      lockVersion: 2,
      issueVerifications: []
    }, expect.stringMatching(/^review-action:/))
    wrapper.unmount()
  })

  it('把媒体工作区生成的归一化批注随审核意见提交', async () => {
    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:note:list',
      'shotgrid:note:add'
    ])
    const workspace = wrapper.findComponent({ name: 'ReviewMediaWorkspace' })
    const annotations = {
      schemaVersion: 1,
      sourceWidth: 1920,
      sourceHeight: 1080,
      items: [{ id: 'annotation-test', type: 'rectangle', color: '#ff6b6b', strokeWidth: 0.004, points: [{ x: 0.1, y: 0.2 }, { x: 0.4, y: 0.5 }] }]
    }
    workspace.vm.$emit('annotations-change', annotations)
    await wrapper.find('.issue-compose textarea').setValue('这里需要降低高光')
    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('保存为一条修改问题')).trigger('click')
    await flushPromises()

    expect(addVersionIssue).toHaveBeenCalledWith(33, {
      content: '问题：这里需要降低高光',
      mediaTimeMs: null,
      annotations
    })
    wrapper.unmount()
  })

  it('已退回版本提供原任务修订提交入口', async () => {
    getReviewListDetail.mockResolvedValueOnce({ data: { ...review, reviewStatus: 'completed', version: { ...version, versionStatus: 'rejected' } } })
    getVersionDetail.mockResolvedValueOnce({ data: { ...version, versionStatus: 'rejected' } })
    const { wrapper, router } = await mountDetail()

    await wrapper.findAll('button').find(button => button.text().includes('查看制作任务')).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/tasks/21#version-workspace')
    wrapper.unmount()
  })

  it('人工审核单由按钮显式触发 ElForm 字段校验并阻止无效请求', async () => {
    const wrapper = mount(ManualReviewDialog, {
      props: {
        modelValue: true,
        projectId: 8,
        candidates: [{ autoVersionId: 33, versionNumber: 'V003', reviewListName: '动力舱审核' }]
      },
      global: {
        components: { ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElInput, ElSelect: ElSelectStub },
        stubs: { teleport: true }
      }
    })
    await flushPromises()

    const createButton = wrapper.findAllComponents(ElButton).find(button => button.text() === '创建审核单')
    const formWrapper = wrapper.findComponent(ElForm)
    expect(formWrapper.props('rules')).toHaveProperty('reviewListName')
    expect(formWrapper.props('rules')).toHaveProperty('versionIds')
    await createButton.trigger('click')
    await flushPromises()
    expect(createManualReviewList).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
