import { ElButton, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElRadioButton, ElRadioGroup, ElTag, ElUpload } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createVersionSubmission,
  getCurrentTaskVersionSubmission,
  getVersionSubmissionStatus,
  preflightVersionSubmission,
  retryVersionSubmission,
  uploadProtectedVersionFile
} from '@/api/shot-grid/versions'
import VersionSubmissionPanel from '@/components/version/VersionSubmissionPanel.vue'

vi.mock('@/api/shot-grid/versions', () => ({
  createVersionSubmission: vi.fn(),
  getCurrentTaskVersionSubmission: vi.fn(),
  getVersionSubmissionStatus: vi.fn(),
  preflightVersionSubmission: vi.fn(),
  retryVersionSubmission: vi.fn(),
  uploadProtectedVersionFile: vi.fn()
}))

const fileId = '550e8400-e29b-41d4-a716-446655440000'
const mountOptions = {
  global: { components: { ElButton, ElForm, ElFormItem, ElIcon, ElImage, ElInput, ElRadioButton, ElRadioGroup, ElTag, ElUpload } }
}
const revisionIssue = {
  issueId: 51,
  originVersionId: 1,
  originVersionNumber: 'V001',
  pendingVersionId: 1,
  pendingVersionNumber: 'V001',
  status: 'open',
  content: '这里有点模糊',
  annotations: { items: [{ type: 'rectangle' }] },
  referenceFiles: [{
    fileId: '11111111-1111-4111-8111-111111111111',
    originalName: '灯光效果参考.pdf',
    contentType: 'application/pdf',
    fileSize: 2048,
    downloadUrl: '/shot-grid/issues/51/reference-files/11111111-1111-4111-8111-111111111111/download'
  }],
  responses: [],
  verifications: []
}

function accepted(overrides = {}) {
  return {
    data: {
      submissionId: 91,
      submissionStatus: 'pending',
      reservedVersionNumber: 'V001',
      candidateCount: 1,
      candidates: [{
        candidateNumber: 'V001_01',
        sourceFileId: fileId,
        businessFileName: 'WGZR_EP001_001_S001_YJF_V001_01_1.mov',
        publishStatus: 'pending'
      }],
      businessFileName: 'WGZR_EP001_001_S001_YJF_V001_01_1.mov',
      taskStatus: 'in_progress',
      replayed: false,
      ...overrides
    }
  }
}

function status(submissionStatus, overrides = {}) {
  return {
    data: {
      submissionId: 91,
      taskId: 31,
      submissionStatus,
      reservedVersionNumber: 'V001',
      candidateCount: 1,
      candidates: [{
        candidateNumber: 'V001_01',
        sourceFileId: fileId,
        businessFileName: 'WGZR_EP001_001_S001_YJF_V001_01_1.mov',
        publishStatus: submissionStatus === 'committed' ? 'published' : submissionStatus
      }],
      businessFileName: 'WGZR_EP001_001_S001_YJF_V001_01_1.mov',
      attemptCount: 1,
      taskStatus: submissionStatus === 'committed' ? 'pending_review' : 'in_progress',
      ...overrides
    }
  }
}

async function chooseValidFileAndSubmit(wrapper) {
  const input = wrapper.find('input[type="file"]')
  const file = new File(['mov-data'], '结果.mov', { type: 'video/quicktime' })
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change')
  await wrapper.find('.changelog-field textarea').setValue('调整镜头节奏')
  await clickSubmissionButton(wrapper)
  await flushPromises()
  return file
}

async function clickSubmissionButton(wrapper) {
  await wrapper.get('.submission-form footer .el-button--primary').trigger('click')
}

describe('版本上传与发布面板', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    let previewIndex = 0
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => `blob:candidate-${++previewIndex}`) })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    getCurrentTaskVersionSubmission.mockResolvedValue({ data: null })
    preflightVersionSubmission.mockImplementation((taskId, payload) => Promise.resolve({
      data: {
        ready: true,
        taskId,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        candidates: payload.candidates.map((candidate, index) => ({
          clientFileKey: candidate.clientFileKey,
          candidateNo: index + 1,
          candidateNumber: `V001_${String(index + 1).padStart(2, '0')}`,
          fileExtension: candidate.fileName.split('.').pop().toLowerCase()
        })),
        openIssueSnapshotHash: 'a'.repeat(64),
        allowedActions: ['version.add']
      }
    }))
    uploadProtectedVersionFile.mockResolvedValue({
      code: 200,
      fileId,
      accessType: 'private',
      originalFilename: '结果.mov',
      downloadUrl: `/common/files/${fileId}/download/结果.mov`
    })
    createVersionSubmission.mockResolvedValue(accepted())
    getVersionSubmissionStatus.mockResolvedValue(status('pending'))
    retryVersionSubmission.mockResolvedValue(accepted())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    delete URL.createObjectURL
    delete URL.revokeObjectURL
  })

  it('首次交付与返修送审使用不同的行动文案并提示下一版本号', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        versionCount: 0,
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    expect(wrapper.get('.panel-heading').text()).toContain('提交首版成果')
    expect(wrapper.get('.panel-heading').text()).toContain('将生成 V001 并进入审核')
    expect(wrapper.get('.submission-form').attributes('aria-label')).toBe('提交首版成果')
    expect(wrapper.text()).toContain('选择首版候选成果')
    expect(wrapper.text()).toContain('首版交付说明')
    expect(wrapper.get('.submission-form footer').text()).toContain('提交首版并进入审核')

    await wrapper.setProps({ taskStatus: 'revision', versionCount: 1, openIssues: [revisionIssue] })
    await flushPromises()

    expect(wrapper.get('.panel-heading').text()).toContain('提交修改成果')
    expect(wrapper.get('.panel-heading').text()).toContain('将生成 V002 并重新进入审核')
    expect(wrapper.get('.submission-form').attributes('aria-label')).toBe('提交修改成果')
    expect(wrapper.text()).toContain('选择修改后的候选成果')
    expect(wrapper.text()).toContain('逐条说明修改情况')
    expect(wrapper.find('.review-reference-files').exists()).toBe(false)
    await wrapper.get('.issue-source-link').trigger('click')
    expect(wrapper.emitted('focus-issue').at(-1)).toEqual([revisionIssue])
    expect(wrapper.text()).toContain('说明会随 V002 永久保存')
    expect(wrapper.get('.submission-form footer').text()).toContain('提交修改成果并重新送审')
    wrapper.unmount()
  })

  it('使用 Element Plus 拖拽上传并保留文件类型限制', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()

    const upload = wrapper.findComponent(ElUpload)
    expect(upload.props('drag')).toBe(true)
    expect(upload.props('accept')).toBe('.mp4,.mov')
    expect(wrapper.text()).toContain('拖拽或选择')
    const dropZone = wrapper.find('.el-upload-dragger')
    const file = new File(['mov-data'], '拖拽结果.mov', { type: 'video/quicktime' })
    await dropZone.trigger('drop', { dataTransfer: { files: [file] } })
    await flushPromises()

    expect(wrapper.text()).toContain('拖拽结果.mov')
    expect(wrapper.text()).toContain('继续添加')
    expect(wrapper.text()).toContain('移除')
    const preview = wrapper.get('video.candidate-local-preview__media')
    expect(preview.attributes()).toMatchObject({
      src: 'blob:candidate-1',
      controls: '',
      playsinline: '',
      preload: 'metadata'
    })
    expect(URL.createObjectURL).toHaveBeenCalledWith(file)
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:candidate-1')
  })

  it('资产候选文件使用可放大的图片预览，并在移除时释放临时地址', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 32, taskKind: 'asset_image', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()

    const input = wrapper.find('input[type="file"]')
    const file = new File(['png-data'], '角色方案.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')

    const preview = wrapper.getComponent(ElImage)
    expect(preview.props()).toMatchObject({
      src: 'blob:candidate-1',
      previewSrcList: ['blob:candidate-1'],
      fit: 'contain'
    })
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '移除').trigger('click')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:candidate-1')
    expect(wrapper.find('.candidate-upload-item').exists()).toBe(false)
    wrapper.unmount()
  })

  it('一次提交多个候选文件并保持批次内顺序与稳定文件键', async () => {
    const secondFileId = '550e8400-e29b-41d4-a716-446655440001'
    uploadProtectedVersionFile
      .mockResolvedValueOnce({
        code: 200,
        fileId,
        accessType: 'private',
        originalFilename: '候选甲.mov'
      })
      .mockResolvedValueOnce({
        code: 200,
        fileId: secondFileId,
        accessType: 'private',
        originalFilename: '候选乙.mov'
      })
    createVersionSubmission.mockResolvedValueOnce(accepted({
      candidateCount: 2,
      candidates: [
        { candidateNumber: 'V001_01', sourceFileId: fileId, businessFileName: 'V001_01.mov', publishStatus: 'pending' },
        { candidateNumber: 'V001_02', sourceFileId: secondFileId, businessFileName: 'V001_02.mov', publishStatus: 'pending' }
      ]
    }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()

    const input = wrapper.find('input[type="file"]')
    const files = [
      new File(['candidate-a'], '候选甲.mov', { type: 'video/quicktime' }),
      new File(['candidate-b'], '候选乙.mov', { type: 'video/quicktime' })
    ]
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })
    await input.trigger('change')
    await wrapper.find('.changelog-field textarea').setValue('同时提交两个备选效果')
    await clickSubmissionButton(wrapper)
    await flushPromises()

    expect(uploadProtectedVersionFile.mock.calls.map(call => call[0])).toEqual(files)
    const preflightCandidates = preflightVersionSubmission.mock.calls[0][1].candidates
    expect(preflightCandidates).toMatchObject([
      { fileName: '候选甲.mov', sortOrder: 0 },
      { fileName: '候选乙.mov', sortOrder: 1 }
    ])
    expect(preflightCandidates[0].clientFileKey).not.toBe(preflightCandidates[1].clientFileKey)
    expect(createVersionSubmission.mock.calls[0][1].candidates).toEqual([
      { clientFileKey: preflightCandidates[0].clientFileKey, fileId, sortOrder: 0, candidateNote: null },
      { clientFileKey: preflightCandidates[1].clientFileKey, fileId: secondFileId, sortOrder: 1, candidateNote: null }
    ])
    expect(wrapper.text()).toContain('候选文件2 个')
    wrapper.unmount()
  })

  it('严格按预检、私有上传、创建提交执行，pending 明确不是版本成功', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 4 }
    })
    await flushPromises()
    const file = await chooseValidFileAndSubmit(wrapper)

    expect(preflightVersionSubmission).toHaveBeenCalledWith(
      31,
      {
        candidates: [{
          clientFileKey: expect.any(String),
          fileName: '结果.mov',
          fileSize: file.size,
          sortOrder: 0,
          candidateNote: null
        }],
        changelog: '调整镜头节奏',
        issueResponses: []
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(uploadProtectedVersionFile).toHaveBeenCalledWith(file, expect.objectContaining({ signal: expect.any(AbortSignal), onUploadProgress: expect.any(Function) }))
    expect(createVersionSubmission).toHaveBeenCalledWith(
      31,
      {
        candidates: [{
          clientFileKey: expect.any(String),
          fileId,
          sortOrder: 0,
          candidateNote: null
        }],
        changelog: '调整镜头节奏',
        openIssueSnapshotHash: 'a'.repeat(64),
        issueResponses: []
      },
      expect.stringContaining('version-31:'),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(preflightVersionSubmission.mock.invocationCallOrder[0]).toBeLessThan(uploadProtectedVersionFile.mock.invocationCallOrder[0])
    expect(uploadProtectedVersionFile.mock.invocationCallOrder[0]).toBeLessThan(createVersionSubmission.mock.invocationCallOrder[0])
    expect(wrapper.text()).toContain('等待发布')
    expect(wrapper.find('.submission-status').findComponent(ElTag).text()).toBe('等待发布')
    expect(wrapper.find('.submission-status').findComponent(ElTag).text()).not.toBe('pending')
    expect(wrapper.text()).toContain('正式版本生成前请勿重复提交')
    expect(wrapper.text()).not.toContain('AI 生成参数')
    expect(wrapper.find('.ai-params').exists()).toBe(false)
    expect(wrapper.emitted('committed')).toBeUndefined()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    wrapper.unmount()
  })

  it('返修问题默认使用已处理，并通过现有 ElForm 提交标准处理说明', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'revision',
        openIssues: [revisionIssue],
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    expect(wrapper.findAllComponents(ElForm)).toHaveLength(1)
    const handlingGroup = wrapper.findComponent(ElRadioGroup)
    expect(handlingGroup.props()).toMatchObject({ modelValue: 'handled', size: 'small' })
    expect(wrapper.findAllComponents(ElRadioButton).map(button => button.props('value'))).toEqual(['handled', 'unhandled'])
    expect(wrapper.find('.issue-unhandled-reason').exists()).toBe(false)

    const file = await chooseValidFileAndSubmit(wrapper)
    expect(preflightVersionSubmission).toHaveBeenCalledWith(
      31,
      {
        candidates: [expect.objectContaining({ fileName: '结果.mov', fileSize: file.size })],
        changelog: '调整镜头节奏',
        issueResponses: [{ issueId: 51, responseText: '已处理' }]
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    wrapper.unmount()
  })

  it('选择未处理后显示原因输入框，未填写时阻止提交，填写后保存未处理说明', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'revision',
        openIssues: [revisionIssue],
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', 'unhandled')
    await flushPromises()
    expect(wrapper.find('.issue-unhandled-reason').exists()).toBe(true)

    const file = await chooseValidFileAndSubmit(wrapper)
    expect(preflightVersionSubmission).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请说明该问题本轮未处理的原因')

    await wrapper.find('.issue-unhandled-reason textarea').setValue('等待外部素材确认后再修改')
    await clickSubmissionButton(wrapper)
    await flushPromises()
    expect(preflightVersionSubmission).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        candidates: [expect.objectContaining({ fileSize: file.size })],
        issueResponses: [{ issueId: 51, responseText: '未处理：等待外部素材确认后再修改' }]
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    wrapper.unmount()
  })

  it('首次提交使用制作内容作为占位提示，后续版本切换为返修改动提示', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        versionCount: 0,
        productionDescription: '稍带斜角度拍门上贴纸：“禁止入内”“内有恶犬”',
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    const changelogInput = wrapper.find('.field-label textarea')
    expect(changelogInput.attributes('placeholder')).toContain('稍带斜角度拍门上贴纸')
    expect(changelogInput.element.value).toBe('')

    await wrapper.setProps({ versionCount: 1 })
    expect(changelogInput.attributes('placeholder')).toBe('概括本轮针对审核意见完成的修改，以及仍需审核人关注的内容。')
    wrapper.unmount()
  })

  it('创建请求失败后复用同一 fileId 和幂等键，不重复上传', async () => {
    createVersionSubmission.mockRejectedValueOnce({ httpStatus: 503, message: '提交服务暂不可用', errorKey: 'SG_SERVICE_UNAVAILABLE' })
      .mockResolvedValueOnce(accepted({ replayed: true }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    expect(wrapper.text()).toContain('文件已上传，正式版本尚未生成')
    expect(wrapper.text()).toContain('提交服务暂不可用')
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.field-label textarea').attributes('disabled')).toBeDefined()

    await clickSubmissionButton(wrapper)
    await flushPromises()
    expect(uploadProtectedVersionFile).toHaveBeenCalledTimes(1)
    expect(preflightVersionSubmission).toHaveBeenCalledTimes(1)
    expect(createVersionSubmission).toHaveBeenCalledTimes(2)
    expect(createVersionSubmission.mock.calls[1][1].candidates[0].fileId).toBe(fileId)
    expect(createVersionSubmission.mock.calls[1][2]).toBe(createVersionSubmission.mock.calls[0][2])
    expect(wrapper.text()).toContain('已恢复原提交')
    wrapper.unmount()
  })

  it.each([
    [403, 'SG_PROJECT_ACCESS_DENIED', '无权访问版本'],
    [409, 'SG_PROJECT_NOT_READY', '版本状态发生冲突'],
    [422, 'SG_ASSET_PRODUCTION_ITEM_REQUIRED', '提交前检查未通过']
  ])('预检 HTTP %s 失败时绝不上传或创建提交', async (httpStatus, errorKey, expectedTitle) => {
    preflightVersionSubmission.mockRejectedValueOnce({
      httpStatus,
      message: `预检失败 ${httpStatus}`,
      errorKey
    })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)

    expect(wrapper.text()).toContain(expectedTitle)
    expect(wrapper.text()).toContain(`预检失败 ${httpStatus}`)
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    expect(createVersionSubmission).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('预检等待期间权限被撤销时复验双门禁且不上传', async () => {
    let resolvePreflight
    preflightVersionSubmission.mockImplementationOnce(() => new Promise(resolve => {
      resolvePreflight = resolve
    }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    await wrapper.setProps({ allowedActions: [] })
    resolvePreflight({
      data: {
        ready: true,
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        fileExtension: 'mov',
        allowedActions: ['version.add']
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('提交权限或任务状态已发生变化')
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    expect(createVersionSubmission).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('任务 A→B→A 会取消旧预检，迟到成功响应也不得开始上传', async () => {
    let resolveOldPreflight
    preflightVersionSubmission.mockImplementationOnce((_taskId, _payload, options) => new Promise(resolve => {
      resolveOldPreflight = resolve
      expect(options.signal.aborted).toBe(false)
    }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        allowedActions: ['version.add'],
        hasAddPermission: true,
        canQuery: true,
        operationGeneration: 1
      }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    const oldSignal = preflightVersionSubmission.mock.calls[0][2].signal

    await wrapper.setProps({ taskId: 32, operationGeneration: 2 })
    await flushPromises()
    await wrapper.setProps({ taskId: 31, operationGeneration: 3 })
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    resolveOldPreflight({
      data: {
        ready: true,
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        fileExtension: 'mov',
        allowedActions: ['version.add']
      }
    })
    await flushPromises()

    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    expect(createVersionSubmission).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('超时后重放若已 committed，立即发出完成事件而不再轮询', async () => {
    createVersionSubmission
      .mockRejectedValueOnce({ httpStatus: 503, message: '首次响应超时' })
      .mockResolvedValueOnce(accepted({ submissionStatus: 'committed', replayed: true }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 9 }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    await clickSubmissionButton(wrapper)
    await flushPromises()

    expect(wrapper.emitted('committed')).toHaveLength(1)
    expect(wrapper.emitted('committed')[0][0]).toMatchObject({ submissionStatus: 'committed', replayed: true })
    expect(wrapper.emitted('committed')[0][1]).toEqual({ taskId: 31, operationGeneration: 9 })
    expect(getVersionSubmissionStatus).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('轮询展示中间态且仅 committed 发出完成事件', async () => {
    getVersionSubmissionStatus.mockResolvedValueOnce(status('publishing'))
      .mockResolvedValueOnce(status('published'))
      .mockResolvedValueOnce(status('committing'))
      .mockResolvedValueOnce(status('committed', { versionId: 71, reviewListId: 81 }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 8, pollInterval: 250 }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)

    for (const label of ['正在发布', '文件已保存', '正在生成版本']) {
      await vi.advanceTimersByTimeAsync(250)
      await flushPromises()
      expect(wrapper.text()).toContain(label)
      expect(wrapper.emitted('committed')).toBeUndefined()
    }
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect(wrapper.text()).toContain('版本已生成')
    expect(wrapper.emitted('committed')).toHaveLength(1)
    expect(wrapper.emitted('committed')[0][0]).toMatchObject({ submissionStatus: 'committed', versionId: 71 })
    expect(wrapper.emitted('committed')[0][1]).toEqual({ taskId: 31, operationGeneration: 8 })
    wrapper.unmount()
  })

  it('刷新恢复 failed 提交并按独立 retry 权限重试，不开放新上传', async () => {
    getCurrentTaskVersionSubmission.mockResolvedValue(status('failed', {
      lastErrorKey: 'SG_VERSION_SOURCE_FILE_UNAVAILABLE',
      lastErrorMessage: '平台源文件暂不可读'
    }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: [], canQuery: true, canRetry: true }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('发布失败')
    expect(wrapper.text()).toContain('平台源文件暂不可读')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.findComponent(ElTag).props()).toMatchObject({
      type: 'danger', effect: 'dark', size: 'small', round: true
    })

    await wrapper.findAll('button').find(item => item.text().includes('重试当前提交')).trigger('click')
    await flushPromises()
    expect(retryVersionSubmission).toHaveBeenCalledWith(91, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('等待发布')
    wrapper.unmount()
  })

  it('failed 终态可手动刷新并补齐后端失败诊断', async () => {
    getCurrentTaskVersionSubmission.mockResolvedValue(status('failed'))
    getVersionSubmissionStatus.mockResolvedValue(status('failed', {
      lastErrorKey: 'SG_VERSION_TARGET_PATH_CONFLICT',
      lastErrorMessage: '目标版本文件与现有文件摘要不一致'
    }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: [], canQuery: true }
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('目标版本文件与现有文件摘要不一致')
    await wrapper.findAll('button').find(item => item.text().includes('刷新状态')).trigger('click')
    await flushPromises()

    expect(getVersionSubmissionStatus).toHaveBeenCalledWith(91, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('目标版本文件与现有文件摘要不一致')
    expect(wrapper.text()).toContain('版本发布失败')
    wrapper.unmount()
  })

  it.each([
    [401, '会话已失效'],
    [403, '无权访问版本'],
    [404, '版本资源不存在'],
    [409, '版本状态发生冲突'],
    [413, '文件超过上传上限'],
    [503, '版本处理异常']
  ])('区分 HTTP %s 上传错误', async (httpStatus, title) => {
    uploadProtectedVersionFile.mockRejectedValueOnce({ httpStatus, message: `服务错误 ${httpStatus}`, errorKey: `E_${httpStatus}` })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    expect(wrapper.text()).toContain(title)
    expect(wrapper.text()).toContain(`服务错误 ${httpStatus}`)
    wrapper.unmount()
  })

  it('平台缺少 version:add 时即使后端动作镜像存在也不上传', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: false, canQuery: false }
    })
    await flushPromises()

    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(getCurrentTaskVersionSubmission).not.toHaveBeenCalled()
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('任务标记存在未完成提交但无 query 权限时失败关闭', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        allowedActions: ['version.add'],
        hasUncommittedSubmission: true,
        hasAddPermission: true,
        canQuery: false
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('任务有正在处理的版本提交，但当前账号无法查看进度')
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(getCurrentTaskVersionSubmission).not.toHaveBeenCalled()
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('当前提交恢复失败时不允许上传，手动重试成功后才解锁', async () => {
    getCurrentTaskVersionSubmission
      .mockRejectedValueOnce({ httpStatus: 503, message: '状态恢复服务不可用' })
      .mockResolvedValueOnce({ data: null })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: {
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        allowedActions: ['version.add'],
        hasUncommittedSubmission: true,
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('状态恢复服务不可用')
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').find(item => item.text().includes('重新检查')).trigger('click')
    await flushPromises()
    expect(getCurrentTaskVersionSubmission).toHaveBeenCalledTimes(2)
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('修改说明含换行或控制字符时在私有文件上传前拒绝', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    const input = wrapper.find('input[type="file"]')
    const file = new File(['mov-data'], '结果.mov', { type: 'video/quicktime' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.find('.field-label textarea').setValue('第一行\n第二行')
    await clickSubmissionButton(wrapper)
    await flushPromises()

    expect(wrapper.text()).toContain('修改说明不能换行或包含不可见字符')
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('连续状态刷新失败会退避并在三次后暂停，不形成请求风暴', async () => {
    getVersionSubmissionStatus.mockRejectedValue({ httpStatus: 503, message: '状态服务不可用' })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, pollInterval: 250 }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)

    await vi.advanceTimersByTimeAsync(250)
    await vi.advanceTimersByTimeAsync(500)
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(getVersionSubmissionStatus).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).toContain('自动刷新已暂停')
    expect(wrapper.text()).toContain('连续 3 次刷新失败')

    await vi.advanceTimersByTimeAsync(60_000)
    expect(getVersionSubmissionStatus).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('任务 A→B→A 和卸载会取消旧恢复/轮询，迟到响应不能污染当前上下文', async () => {
    let resolveTaskA
    getCurrentTaskVersionSubmission.mockImplementationOnce((_taskId, options) => new Promise(resolve => {
      resolveTaskA = resolve
      expect(options.signal.aborted).toBe(false)
    })).mockResolvedValueOnce({ data: null }).mockResolvedValueOnce({ data: null })

    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', taskStatus: 'in_progress', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 1, pollInterval: 250 }
    })
    await flushPromises()
    const firstSignal = getCurrentTaskVersionSubmission.mock.calls[0][1].signal
    await wrapper.setProps({ taskId: 32, operationGeneration: 2 })
    await flushPromises()
    expect(firstSignal.aborted).toBe(true)
    await wrapper.setProps({ taskId: 31, operationGeneration: 3 })
    await flushPromises()
    resolveTaskA(status('failed', { businessFileName: '迟到旧文件.mov' }))
    await flushPromises()
    expect(wrapper.text()).not.toContain('迟到旧文件.mov')

    getVersionSubmissionStatus.mockImplementationOnce((_id, options) => new Promise(() => {
      expect(options.signal.aborted).toBe(false)
    }))
    createVersionSubmission.mockResolvedValueOnce(accepted())
    await chooseValidFileAndSubmit(wrapper)
    await vi.advanceTimersByTimeAsync(250)
    const pollSignal = getVersionSubmissionStatus.mock.calls.at(-1)[1].signal
    wrapper.unmount()
    expect(pollSignal.aborted).toBe(true)
  })
})
