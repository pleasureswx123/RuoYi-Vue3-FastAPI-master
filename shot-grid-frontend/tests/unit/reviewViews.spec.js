import { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElMessageBox, ElRadioButton, ElRadioGroup, ElSkeleton, ElTag, ElUpload } from 'element-plus'
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
  retryFinalDelivery,
  selectVersionCandidate,
  uploadReviewReferenceFile,
  updateVersionIssueDraft
} from '@/api/shot-grid/reviews'
import {
  createVersionPlaybackTicket,
  downloadProtectedVersionFile,
  getTaskVersions,
  getVersionDetail,
  resolvePlaybackUrl
} from '@/api/shot-grid/versions'
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
  selectVersionCandidate: vi.fn(),
  getVersionReviewContext: vi.fn(),
  retryFinalDelivery: vi.fn(),
  uploadReviewReferenceFile: vi.fn(),
  downloadReviewReferenceFile: vi.fn(),
  transitionManualReviewList: vi.fn(),
  updateVersionIssueDraft: vi.fn(),
  deleteVersionIssueDraft: vi.fn()
}))
vi.mock('@/api/shot-grid/versions', () => ({
  createVersionPlaybackTicket: vi.fn(),
  downloadProtectedVersionFile: vi.fn(),
  getTaskVersions: vi.fn(),
  getVersionDetail: vi.fn(),
  resolvePlaybackUrl: vi.fn(url => `/dev-api${url}`)
}))
vi.mock('@/api/shot-grid/shots', () => ({
  downloadProtectedThumbnail: vi.fn()
}))

const project = { projectId: 8, projectCode: 'LCFR', projectName: '罗刹夫人' }
const ElSelectStub = { name: 'ElSelect', template: '<div class="el-select-stub" />' }
let objectUrlSequence = 0
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
  candidateCount: 1,
  selectedCandidateId: 3301,
  lockVersion: 2,
  files: [],
  candidates: [{
    candidateId: 3301,
    candidateNo: 1,
    candidateNumber: 'V003_01',
    candidateNote: null,
    sortOrder: 0,
    isSelected: true,
    files: [],
    mediaDerivationStatus: 'completed'
  }],
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
      components: { ElAlert, ElButton, ElDialog, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElRadioButton, ElRadioGroup, ElSkeleton, ElTag, ElUpload }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('版本审核页面', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    objectUrlSequence = 0
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => `blob:review-candidate-${++objectUrlSequence}`) })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    getProjectPage.mockResolvedValue({ rows: [project], total: 1 })
    getReviewListPage.mockResolvedValue({ rows: [review], total: 1 })
    getReviewListDetail.mockResolvedValue({ data: { ...review, version } })
    getVersionDetail.mockResolvedValue({ data: version })
    getVersionReviewContext.mockResolvedValue({ data: { currentVersion: version, candidates: version.candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } })
    getReviewActions.mockResolvedValue({ rows: [], total: 0 })
    getTaskVersions.mockResolvedValue({ rows: [], total: 0 })
    downloadProtectedVersionFile.mockResolvedValue(new Blob(['preview'], { type: 'image/jpeg' }))
    createVersionPlaybackTicket.mockResolvedValue({ data: { playbackUrl: '/shot-grid/playback/ticket/candidate' } })
    resolvePlaybackUrl.mockImplementation(url => `/dev-api${url}`)
    downloadProtectedThumbnail.mockResolvedValue(new Blob(['thumbnail'], { type: 'image/jpeg' }))
    addVersionIssueDraft.mockResolvedValue({ data: { draftId: 502 } })
    updateVersionIssueDraft.mockResolvedValue({ data: { draftId: 502, lockVersion: 4 } })
    deleteVersionIssueDraft.mockResolvedValue({ code: 200 })
    createManualReviewList.mockResolvedValue({ data: { reviewListId: 202 } })
    createReviewAction.mockResolvedValue({ data: { actionId: 901 } })
    retryFinalDelivery.mockResolvedValue({ data: { deliveryStatus: 'pending' } })
    uploadReviewReferenceFile.mockResolvedValue({ fileId: '11111111-1111-4111-8111-111111111111' })
    selectVersionCandidate.mockResolvedValue({ data: { selectedCandidateId: 3301, lockVersion: 3 } })
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
    expect(wrapper.find('.candidate-selector').exists()).toBe(false)
    expect(wrapper.text()).toContain('播放并检查 V003_01')
    expect(wrapper.text()).not.toContain('尚未选择')
    const headingTags = wrapper.find('.heading-actions').findAllComponents(ElTag)
    expect(headingTags.map(tag => tag.text())).toEqual(['自动单版', '待审核'])
    expect(headingTags[0].props()).toMatchObject({ type: 'primary', effect: 'plain', size: 'small', round: true })
    expect(headingTags[1].props()).toMatchObject({ type: 'warning', effect: 'light', size: 'small', round: true })

    const approveButton = wrapper.findAll('button').find(button => button.text().includes('确认通过'))
    await approveButton.trigger('click')
    await flushPromises()

    expect(createReviewAction).toHaveBeenCalledWith(33, {
      actionType: 'approve',
      selectedCandidateId: 3301,
      reason: null,
      lockVersion: 2,
      issueVerifications: []
    }, expect.stringMatching(/^review-action:/))
    wrapper.unmount()
  })

  it('多候选版本必须先选择最佳文件，选择后才开放问题与审核决定', async () => {
    const candidates = [
      { candidateId: 3301, candidateNo: 1, candidateNumber: 'V003_01', candidateNote: '光影更稳', sortOrder: 0, isSelected: false, files: [], mediaDerivationStatus: 'completed' },
      { candidateId: 3302, candidateNo: 2, candidateNumber: 'V003_02', candidateNote: '动作更顺', sortOrder: 1, isSelected: false, files: [], mediaDerivationStatus: 'completed' }
    ]
    const unselectedVersion = { ...version, candidateCount: 2, selectedCandidateId: null, candidates }
    const selectedVersion = {
      ...unselectedVersion,
      selectedCandidateId: 3302,
      lockVersion: 3,
      candidates: candidates.map(item => ({ ...item, isSelected: item.candidateId === 3302 }))
    }
    getReviewListDetail.mockResolvedValue({ data: { ...review, version: unselectedVersion } })
    getVersionDetail
      .mockResolvedValueOnce({ data: unselectedVersion })
      .mockResolvedValueOnce({ data: selectedVersion })
    getVersionReviewContext
      .mockResolvedValueOnce({ data: { currentVersion: unselectedVersion, candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } })
      .mockResolvedValueOnce({ data: { currentVersion: selectedVersion, candidates: selectedVersion.candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } })
    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:note:list',
      'shotgrid:note:add'
    ])

    expect(wrapper.text()).toContain('尚未选择')
    expect(wrapper.find('.issue-compose').exists()).toBe(false)
    expect(wrapper.findAllComponents(ElButton).find(button => button.text().includes('确认通过')).attributes('disabled')).toBeDefined()
    const chooseButtons = wrapper.findAllComponents(ElButton).filter(button => button.text() === '设为本轮最佳候选')
    await chooseButtons[1].trigger('click')
    await flushPromises()

    expect(selectVersionCandidate).toHaveBeenCalledWith(
      33,
      { candidateId: 3302, lockVersion: 2 },
      expect.stringMatching(/^review-candidate:/)
    )
    expect(wrapper.text()).toContain('已选择最佳候选')
    expect(wrapper.find('.issue-compose').exists()).toBe(true)
    expect(wrapper.findAllComponents(ElButton).find(button => button.text().includes('确认通过')).attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('审核退回后锁定最佳候选但保留历史候选预览', async () => {
    const candidates = [
      { candidateId: 3301, candidateNo: 1, candidateNumber: 'V003_01', candidateNote: '光影更稳', sortOrder: 0, isSelected: false, files: [], mediaDerivationStatus: 'completed' },
      { candidateId: 3302, candidateNo: 2, candidateNumber: 'V003_02', candidateNote: '动作更顺', sortOrder: 1, isSelected: true, files: [], mediaDerivationStatus: 'completed' }
    ]
    const rejectedVersion = {
      ...version,
      versionStatus: 'rejected',
      candidateCount: 2,
      selectedCandidateId: 3302,
      candidates
    }
    getReviewListDetail.mockResolvedValue({
      data: { ...review, reviewStatus: 'completed', versionStatus: 'rejected', version: rejectedVersion }
    })
    getVersionDetail.mockResolvedValue({ data: rejectedVersion })
    getVersionReviewContext.mockResolvedValue({
      data: { currentVersion: rejectedVersion, candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] }
    })

    const { wrapper } = await mountDetail()
    const selectionButtons = wrapper.findAllComponents(ElButton).filter(button => button.text() === '本轮最佳')

    expect(selectionButtons).toHaveLength(1)
    expect(selectionButtons.every(button => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('审核已结束，仅可预览历史候选')
    expect(wrapper.text()).toContain('本轮审核已结束，最佳候选不可更改')
    expect(wrapper.text()).not.toContain('审核已结束，不可切换')
    expect(wrapper.text()).not.toContain('本轮最佳（已锁定）')

    await wrapper.findAll('.candidate-choice')[0].find('.el-radio').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('播放并检查 V003_01')
    expect(selectVersionCandidate).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('直接展示候选画面并通过候选卡片切换中央播放器', async () => {
    const candidateFiles = candidateNo => [
      {
        fileId: `5ed39e04-2f29-45ab-a58c-4f8168f513${candidateNo}a`,
        businessFileName: `LCFR_V003_0${candidateNo}.jpg`,
        role: 'thumbnail',
        isPrimary: false,
        contentType: 'image/jpeg',
        fileSize: 1024
      },
      {
        fileId: `6ed39e04-2f29-45ab-a58c-4f8168f513${candidateNo}a`,
        businessFileName: `LCFR_V003_0${candidateNo}.mov`,
        role: 'review_media',
        isPrimary: true,
        contentType: 'video/quicktime',
        fileSize: 4096
      }
    ]
    const candidates = [
      { candidateId: 3301, candidateNo: 1, candidateNumber: 'V003_01', candidateNote: '光影更稳', sortOrder: 0, isSelected: false, files: candidateFiles(1), mediaDerivationStatus: 'completed' },
      { candidateId: 3302, candidateNo: 2, candidateNumber: 'V003_02', candidateNote: '动作更顺', sortOrder: 1, isSelected: false, files: candidateFiles(2), mediaDerivationStatus: 'completed' }
    ]
    const multiCandidateVersion = { ...version, files: candidates[0].files, candidateCount: 2, selectedCandidateId: null, candidates }
    getReviewListDetail.mockResolvedValue({ data: { ...review, version: multiCandidateVersion } })
    getVersionDetail.mockResolvedValue({ data: multiCandidateVersion })
    getVersionReviewContext.mockResolvedValue({ data: { currentVersion: multiCandidateVersion, candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] } })

    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:note:list',
      'shotgrid:file:download'
    ])

    const candidateCards = wrapper.findAll('.candidate-choice')
    expect(candidateCards).toHaveLength(2)
    expect(wrapper.findAllComponents({ name: 'ReviewCandidateThumbnail' })).toHaveLength(2)
    expect(wrapper.findAllComponents(ElButton).some(button => button.text() === '预览')).toBe(false)
    expect(wrapper.text()).toContain('播放并检查 V003_01')
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version').files).toEqual(candidates[0].files)

    await candidateCards[1].find('.el-radio').trigger('click')
    await flushPromises()

    expect(candidateCards[1].classes()).toContain('is-previewing')
    expect(wrapper.text()).toContain('播放并检查 V003_02')
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version').files).toEqual(candidates[1].files)
    expect(wrapper.find('.review-work-step').classes()).toContain('is-candidate-focus')
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
      annotations,
      referenceFileIds: []
    })
    wrapper.unmount()
  })

  it('上传本地参考资料并将受保护文件ID随问题草稿保存', async () => {
    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:note:list',
      'shotgrid:note:add',
      'shotgrid:file:download'
    ])
    const file = new File(['reference'], '灯光参考.pdf', { type: 'application/pdf' })
    const input = wrapper.find('.issue-reference-compose input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(wrapper.find('.issue-reference-pending-list').text()).toContain('灯光参考.pdf')
    await wrapper.find('.issue-compose textarea').setValue('请参考附件调整灯光层次')
    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('保存问题草稿')).trigger('click')
    await flushPromises()

    expect(uploadReviewReferenceFile).toHaveBeenCalledWith(file, expect.objectContaining({
      signal: expect.any(AbortSignal),
      onUploadProgress: expect.any(Function)
    }))
    expect(addVersionIssueDraft).toHaveBeenCalledWith(33, {
      content: '问题：请参考附件调整灯光层次',
      mediaTimeMs: null,
      annotations: null,
      referenceFileIds: ['11111111-1111-4111-8111-111111111111']
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
      referenceFiles: [{
        fileId: '22222222-2222-4222-8222-222222222222',
        originalName: '主体亮度参考.pdf',
        contentType: 'application/pdf',
        fileSize: 4096,
        downloadUrl: '/shot-grid/issue-drafts/502/reference-files/22222222-2222-4222-8222-222222222222/download'
      }],
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
    expect(draftCard.text()).toContain('主体亮度参考.pdf')
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
      referenceFileIds: ['22222222-2222-4222-8222-222222222222'],
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
    const rejectedCandidates = [
      { candidateId: 3301, candidateNo: 1, candidateNumber: 'V003_01', candidateNote: '问题对应候选', sortOrder: 0, isSelected: false, files: [{ fileId: 'candidate-01', role: 'review_media' }], mediaDerivationStatus: 'completed' },
      { candidateId: 3302, candidateNo: 2, candidateNumber: 'V003_02', candidateNote: '本轮最佳候选', sortOrder: 1, isSelected: true, files: [{ fileId: 'candidate-02', role: 'review_media' }], mediaDerivationStatus: 'completed' }
    ]
    const rejectedVersion = {
      ...version,
      versionStatus: 'rejected',
      candidateCount: 2,
      selectedCandidateId: 3302,
      candidates: rejectedCandidates
    }
    const publishedIssue = {
      issueId: 701,
      originVersionId: 33,
      originCandidateId: 3301,
      reviewerUserId: 1,
      reviewerName: '管理员',
      content: '问题：主体边缘抖动\n修改目标：稳定主体边缘',
      createTime: '2026-08-12T10:20:00'
    }
    getReviewListDetail.mockResolvedValueOnce({ data: { ...review, reviewStatus: 'completed', version: rejectedVersion } })
    getVersionDetail.mockResolvedValueOnce({ data: rejectedVersion })
    getVersionReviewContext.mockResolvedValueOnce({
      data: {
        currentVersion: rejectedVersion,
        candidates: rejectedVersion.candidates,
        carriedIssues: [],
        currentVersionIssues: [publishedIssue],
        currentVersionDrafts: []
      }
    })
    const { wrapper, router } = await mountDetail()

    expect(wrapper.text()).toContain('已发布修改要求 #1')
    expect(wrapper.text()).toContain('主体边缘抖动')
    expect(wrapper.text()).toContain('本轮已发布 1 条修改要求')
    expect(wrapper.text()).not.toContain('旧版已提前发布')
    expect(wrapper.text()).not.toContain('退回时将发送')
    expect(wrapper.text()).toContain('播放并检查 V003_02')

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '查看对应作品').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('播放并检查 V003_01')
    expect(wrapper.findComponent({ name: 'ReviewMediaWorkspace' }).props('version').files).toEqual(rejectedCandidates[0].files)
    expect(wrapper.findAll('.candidate-choice')[0].classes()).toContain('is-previewing')

    await wrapper.findAll('button').find(button => button.text().includes('查看制作任务')).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/tasks/21#version-workspace')
    wrapper.unmount()
  })

  it('最终交付成功时分开展示状态、完整 NAS 路径和清单说明', async () => {
    const finalNasRelativePath = 'VIDEO\\EP01\\001_S001\\FINAL\\TSXK_EP001_001_S001_PXL_V003_02_1787813976090.mp4'
    const finalVersion = {
      ...version,
      versionStatus: 'final',
      finalDelivery: { deliveryStatus: 'published', finalNasRelativePath }
    }
    getReviewListDetail.mockResolvedValue({ data: { ...review, reviewStatus: 'completed', version: finalVersion } })
    getVersionDetail.mockResolvedValue({ data: finalVersion })
    getVersionReviewContext.mockResolvedValue({
      data: { currentVersion: finalVersion, candidates: finalVersion.candidates, carriedIssues: [], currentVersionIssues: [], currentVersionDrafts: [] }
    })
    const { wrapper } = await mountDetail()
    const alert = wrapper.findComponent('.final-delivery-alert')

    expect(alert.props()).toMatchObject({ type: 'success', title: '最终版本已发布到 NAS', closable: false, showIcon: true })
    expect(alert.get('.final-delivery-path').text()).toBe(finalNasRelativePath)
    expect(alert.get('.final-delivery-note').text()).toBe('同目录 FINAL.json 记录最终候选和文件摘要。')
    expect(alert.get('.final-delivery-note').text()).not.toContain(finalNasRelativePath)
    expect(wrapper.findAllComponents(ElButton).some(button => button.text() === '重新发布最终版本')).toBe(false)
    wrapper.unmount()
  })

  it('最终交付失败时明确展示 NAS 状态并允许有权限用户重试', async () => {
    const failedDelivery = {
      finalDeliveryId: 701,
      versionId: 33,
      candidateId: 3301,
      businessFileName: 'LCFR_V003_01.mov',
      finalNasRelativePath: 'VIDEO\\EP01\\001_S001\\FINAL\\LCFR_V003_01.mov',
      manifestNasRelativePath: 'VIDEO\\EP01\\001_S001\\FINAL\\FINAL.json',
      deliveryStatus: 'failed',
      attemptCount: 5,
      lastErrorKey: 'SG_STORAGE_ROOT_UNAVAILABLE',
      lastErrorMessage: 'NAS 目标目录暂时不可访问',
      approvedTime: '2026-08-26T18:30:00',
      publishedTime: null
    }
    const finalVersion = { ...version, versionStatus: 'final', finalDelivery: failedDelivery }
    getReviewListDetail.mockResolvedValue({ data: { ...review, reviewStatus: 'completed', version: finalVersion } })
    getVersionDetail.mockResolvedValue({ data: finalVersion })
    getVersionReviewContext.mockResolvedValue({
      data: {
        currentVersion: { ...finalVersion, finalDelivery: failedDelivery },
        candidates: finalVersion.candidates,
        carriedIssues: [],
        currentVersionIssues: [],
        currentVersionDrafts: []
      }
    })
    const { wrapper } = await mountDetail([
      'shotgrid:reviewList:query',
      'shotgrid:version:query',
      'shotgrid:version:review',
      'shotgrid:version:retry',
      'shotgrid:note:list'
    ])

    expect(wrapper.text()).toContain('审核已通过，但最终版本发布失败')
    expect(wrapper.text()).toContain('NAS 目标目录暂时不可访问')
    const retryButton = wrapper.findAllComponents(ElButton).find(button => button.text() === '重新发布最终版本')
    await retryButton.trigger('click')
    await flushPromises()

    expect(retryFinalDelivery).toHaveBeenCalledWith(33)
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
