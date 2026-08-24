import { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElMessageBox, ElRadioButton, ElRadioGroup, ElSkeleton, ElTag } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProjectPage } from '@/api/shot-grid/projects'
import {
  addVersionIssueDraft,
  createManualReviewList,
  createReviewAction,
  deleteVersionIssueDraft,
  getReviewActions,
  getReviewListDetail,
  getReviewListPage,
  getVersionReviewContext,
  updateVersionIssueDraft
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
  addVersionIssueDraft: vi.fn(),
  createManualReviewList: vi.fn(),
  createReviewAction: vi.fn(),
  getReviewActions: vi.fn(),
  getReviewListDetail: vi.fn(),
  getReviewListPage: vi.fn(),
  getVersionReviewContext: vi.fn(),
  transitionManualReviewList: vi.fn(),
  updateVersionIssueDraft: vi.fn(),
  deleteVersionIssueDraft: vi.fn()
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
  productionTarget: {
    targetType: 'shot',
    requirements: '稍带斜角度拍门上贴纸：“禁止入内”“内有恶犬”',
    shot: {
      durationMs: 1500,
      description: '稍带斜角度拍门上贴纸：“禁止入内”“内有恶犬”',
      shotSize: '特写',
      cameraPosition: '平视机位',
      cameraMovement: '手持呼吸感',
      focalLength: '85',
      dialogue: null,
      soundEffect: '轻微电流声',
      colorReference: '暖色顶光',
      remark: '保持视觉中心表达'
    },
    asset: null
  },
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
    getVersionReviewContext.mockResolvedValue({ data: { currentVersion: version, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } })
    getReviewActions.mockResolvedValue({ rows: [], total: 0 })
    getTaskVersions.mockResolvedValue({ rows: [], total: 0 })
    downloadProtectedThumbnail.mockResolvedValue(new Blob(['thumbnail'], { type: 'image/jpeg' }))
    addVersionIssueDraft.mockResolvedValue({ data: { draftId: 502 } })
    updateVersionIssueDraft.mockResolvedValue({ data: { draftId: 502, lockVersion: 4 } })
    deleteVersionIssueDraft.mockResolvedValue({ code: 200 })
    createManualReviewList.mockResolvedValue({ data: { reviewListId: 202 } })
    createReviewAction.mockResolvedValue({ data: { actionId: 901 } })
  })

  it('按项目加载自动审核单并进入真实详情路由', async () => {
    const { wrapper, router } = await mountList()

    expect(getReviewListPage).toHaveBeenCalledWith('8', expect.objectContaining({ reviewStatus: undefined }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('动力舱合成 V003 审核')
    const tags = wrapper.find('.review-card').findAllComponents(ElTag)
    expect(tags.map(tag => tag.text())).toEqual(['待审核', '待审核'])
    expect(tags.map(tag => tag.props('type'))).toEqual(['warning', 'warning'])
    expect(tags[0].props()).toMatchObject({ effect: 'dark', size: 'small', round: true })
    expect(tags[1].props()).toMatchObject({ effect: 'light', size: 'small', round: true })
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
    expect(wrapper.text()).toContain('审核依据')
    expect(wrapper.text()).toContain('稍带斜角度拍门上贴纸')
    expect(wrapper.text()).toContain('手持呼吸感')
    expect(wrapper.text()).not.toContain('任务补充要求')
    expect(wrapper.findComponent({ name: 'VersionDetailCard' }).props('showPreview')).toBe(false)
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

  it('资产图片审核展示父资产和制作分项依据', async () => {
    getVersionDetail.mockResolvedValueOnce({
      data: {
        ...version,
        productionTarget: {
          targetType: 'asset_item',
          requirements: '保持正视图和统一轮廓光',
          shot: null,
          asset: {
            assetId: 71,
            assetItemId: 72,
            assetType: 'Character',
            assetName: '罗峰',
            assetDescription: '青年战士角色',
            assetRemark: '沿用项目设定比例',
            productionItem: '正视图',
            itemDescription: '完成角色正视图设定',
            itemRemark: '注意服装层次'
          }
        }
      }
    })
    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain('资产图片')
    expect(wrapper.text()).toContain('罗峰')
    expect(wrapper.text()).toContain('正视图')
    expect(wrapper.text()).toContain('保持正视图和统一轮廓光')
    wrapper.unmount()
  })

  it('把媒体工作区生成的时间点与归一化批注带入右侧问题并一并提交', async () => {
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
    workspace.vm.$emit('capture-time', 3250)
    workspace.vm.$emit('annotations-change', annotations)
    await flushPromises()
    expect(wrapper.find('.issue-compose-meta').text()).toContain('回到 00:03')
    expect(wrapper.find('.issue-compose-meta').text()).toContain('查看 1 处标注')
    await wrapper.find('.issue-compose textarea').setValue('这里需要降低高光')
    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('保存问题草稿')).trigger('click')
    await flushPromises()

    expect(addVersionIssueDraft).toHaveBeenCalledWith(33, {
      content: '问题：这里需要降低高光',
      mediaTimeMs: 3250,
      annotations
    })
    wrapper.unmount()
  })

  it('退回前允许编辑和删除私有问题草稿，并携带乐观锁版本', async () => {
    const annotations = {
      schemaVersion: 1,
      sourceWidth: 1920,
      sourceHeight: 1080,
      items: [{ id: 'annotation-draft', type: 'rectangle', color: '#ff6b6b', strokeWidth: 0.004, points: [{ x: 0.1, y: 0.2 }, { x: 0.4, y: 0.5 }] }]
    }
    const draft = {
      draftId: 502,
      projectId: 8,
      reviewListId: 101,
      versionId: 33,
      reviewerUserId: 1,
      reviewerName: '场景锋',
      content: '问题：画面偏暗\n修改目标：提高主体亮度',
      mediaTimeMs: 3250,
      annotations,
      lockVersion: 3,
      createTime: '2026-08-12T10:10:00',
      updateTime: '2026-08-12T10:10:00'
    }
    getVersionReviewContext.mockResolvedValue({
      data: { currentVersion: version, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [draft] }
    })
    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:note:list',
      'shotgrid:note:add'
    ])

    const draftCard = wrapper.find('.issue-draft-card')
    expect(draftCard.text()).toContain('场景锋')
    expect(draftCard.text()).not.toContain('制作人暂不可见')
    await draftCard.findAllComponents(ElButton).find(button => button.text() === '编辑').trigger('click')
    await flushPromises()
    const textareas = wrapper.findAll('.issue-compose textarea')
    expect(textareas[0].element.value).toBe('画面偏暗')
    expect(textareas[1].element.value).toBe('提高主体亮度')
    await textareas[0].setValue('画面主体仍然偏暗')
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '更新问题草稿').trigger('click')
    await flushPromises()

    expect(updateVersionIssueDraft).toHaveBeenCalledWith(33, 502, {
      content: '问题：画面主体仍然偏暗\n修改目标：提高主体亮度',
      mediaTimeMs: 3250,
      annotations,
      lockVersion: 3
    })

    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    await wrapper.find('.issue-draft-card').findAllComponents(ElButton).find(button => button.text() === '删除').trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringContaining('不会发送给制作人'),
      '删除问题草稿',
      expect.objectContaining({ confirmButtonText: '确认删除' })
    )
    expect(deleteVersionIssueDraft).toHaveBeenCalledWith(33, 502, { lockVersion: 3 })
    confirmSpy.mockRestore()
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
