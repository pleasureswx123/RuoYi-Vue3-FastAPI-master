import { ElButton, ElForm, ElFormItem, ElIcon, ElInput, ElTag, ElUpload } from 'element-plus'
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
  global: { components: { ElButton, ElForm, ElFormItem, ElIcon, ElInput, ElTag, ElUpload } }
}

function accepted(overrides = {}) {
  return {
    data: {
      submissionId: 91,
      submissionStatus: 'pending',
      reservedVersionNumber: 'V001',
      businessFileName: 'WGZR_EP001_001_S001_YJF_V001_1.mov',
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
      businessFileName: 'WGZR_EP001_001_S001_YJF_V001_1.mov',
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
  await wrapper.find('.field-label textarea').setValue('调整镜头节奏')
  await wrapper.findAllComponents(ElButton).find(button => button.text().includes('上传并提交版本')).trigger('click')
  await flushPromises()
  return file
}

describe('版本上传与发布面板', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    getCurrentTaskVersionSubmission.mockResolvedValue({ data: null })
    preflightVersionSubmission.mockResolvedValue({
      data: {
        ready: true,
        taskId: 31,
        taskKind: 'shot_video',
        taskStatus: 'in_progress',
        fileExtension: 'mov',
        allowedActions: ['version.add']
      }
    })
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
  })

  it('严格按预检、私有上传、创建提交执行，pending 明确不是版本成功', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 4 }
    })
    await flushPromises()
    const file = await chooseValidFileAndSubmit(wrapper)

    expect(preflightVersionSubmission).toHaveBeenCalledWith(
      31,
      { fileName: '结果.mov', fileSize: file.size, changelog: '调整镜头节奏', aiParams: null, issueResponses: [] },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(uploadProtectedVersionFile).toHaveBeenCalledWith(file, expect.objectContaining({ signal: expect.any(AbortSignal), onUploadProgress: expect.any(Function) }))
    expect(createVersionSubmission).toHaveBeenCalledWith(
      31,
      { fileId, changelog: '调整镜头节奏', aiParams: null, openIssueSnapshotHash: undefined, issueResponses: [] },
      expect.stringContaining('version-31:'),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(preflightVersionSubmission.mock.invocationCallOrder[0]).toBeLessThan(uploadProtectedVersionFile.mock.invocationCallOrder[0])
    expect(uploadProtectedVersionFile.mock.invocationCallOrder[0]).toBeLessThan(createVersionSubmission.mock.invocationCallOrder[0])
    expect(wrapper.text()).toContain('等待发布')
    expect(wrapper.find('.submission-status').findComponent(ElTag).text()).toBe('等待发布')
    expect(wrapper.find('.submission-status').findComponent(ElTag).text()).not.toBe('pending')
    expect(wrapper.text()).toContain('不能视为版本成功')
    expect(wrapper.emitted('committed')).toBeUndefined()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    wrapper.unmount()
  })

  it('创建请求失败后复用同一 fileId 和幂等键，不重复上传', async () => {
    createVersionSubmission.mockRejectedValueOnce({ httpStatus: 503, message: '提交服务暂不可用', errorKey: 'SG_SERVICE_UNAVAILABLE' })
      .mockResolvedValueOnce(accepted({ replayed: true }))
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    expect(wrapper.text()).toContain('平台私有文件已上传，但正式版本尚未形成')
    expect(wrapper.text()).toContain('提交服务暂不可用')
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.field-label textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.ai-params textarea').attributes('disabled')).toBeDefined()

    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('重试创建版本提交')).trigger('click')
    await flushPromises()
    expect(uploadProtectedVersionFile).toHaveBeenCalledTimes(1)
    expect(preflightVersionSubmission).toHaveBeenCalledTimes(1)
    expect(createVersionSubmission).toHaveBeenCalledTimes(2)
    expect(createVersionSubmission.mock.calls[1][1].fileId).toBe(fileId)
    expect(createVersionSubmission.mock.calls[1][2]).toBe(createVersionSubmission.mock.calls[0][2])
    expect(wrapper.text()).toContain('后端已按同一幂等键恢复原提交')
    wrapper.unmount()
  })

  it.each([
    [403, 'SG_PROJECT_ACCESS_DENIED', '无权访问版本'],
    [409, 'SG_PROJECT_NOT_READY', '版本状态发生冲突'],
    [422, 'SG_ASSET_PRODUCTION_ITEM_REQUIRED', '版本提交预检失败']
  ])('预检 HTTP %s 失败时绝不上传或创建提交', async (httpStatus, errorKey, expectedTitle) => {
    preflightVersionSubmission.mockRejectedValueOnce({
      httpStatus,
      message: `预检失败 ${httpStatus}`,
      errorKey
    })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)

    expect(wrapper.text()).toContain(expectedTitle)
    expect(wrapper.text()).toContain(errorKey)
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

    expect(wrapper.text()).toContain('提交权限或任务动作已发生变化')
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
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 9 }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('重试创建版本提交')).trigger('click')
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
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 8, pollInterval: 250 }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)

    for (const label of ['正在发布', '文件已发布', '正在落库']) {
      await vi.advanceTimersByTimeAsync(250)
      await flushPromises()
      expect(wrapper.text()).toContain(label)
      expect(wrapper.emitted('committed')).toBeUndefined()
    }
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect(wrapper.text()).toContain('版本已形成')
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
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: [], canQuery: true, canRetry: true }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('发布失败')
    expect(wrapper.text()).toContain('平台源文件暂不可读')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.findComponent(ElTag).props()).toMatchObject({
      type: 'danger', effect: 'dark', size: 'small', round: true
    })

    await wrapper.findAll('button').find(item => item.text().includes('人工重试')).trigger('click')
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
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: [], canQuery: true }
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('目标版本文件与现有文件摘要不一致')
    await wrapper.findAll('button').find(item => item.text().includes('刷新状态')).trigger('click')
    await flushPromises()

    expect(getVersionSubmissionStatus).toHaveBeenCalledWith(91, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('目标版本文件与现有文件摘要不一致')
    expect(wrapper.text()).toContain('SG_VERSION_TARGET_PATH_CONFLICT')
    wrapper.unmount()
  })

  it.each([
    [401, '会话已失效'],
    [403, '无权访问版本'],
    [404, '版本资源不存在'],
    [409, '版本状态发生冲突'],
    [413, '文件超过上传上限'],
    [503, '版本服务异常']
  ])('区分 HTTP %s 上传错误', async (httpStatus, title) => {
    uploadProtectedVersionFile.mockRejectedValueOnce({ httpStatus, message: `服务错误 ${httpStatus}`, errorKey: `E_${httpStatus}` })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    await chooseValidFileAndSubmit(wrapper)
    expect(wrapper.text()).toContain(title)
    expect(wrapper.text()).toContain(`E_${httpStatus}`)
    wrapper.unmount()
  })

  it('平台缺少 version:add 时即使后端动作镜像存在也不上传', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: false, canQuery: false }
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
        allowedActions: ['version.add'],
        hasUncommittedSubmission: true,
        hasAddPermission: true,
        canQuery: false
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('任务存在未完成版本提交')
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
        allowedActions: ['version.add'],
        hasUncommittedSubmission: true,
        hasAddPermission: true,
        canQuery: true
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('状态恢复服务不可用')
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').find(item => item.text().includes('重试检查')).trigger('click')
    await flushPromises()
    expect(getCurrentTaskVersionSubmission).toHaveBeenCalledTimes(2)
    expect(wrapper.find('input[type="file"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('修改说明含换行或控制字符时在私有文件上传前拒绝', async () => {
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true }
    })
    await flushPromises()
    const input = wrapper.find('input[type="file"]')
    const file = new File(['mov-data'], '结果.mov', { type: 'video/quicktime' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.find('.field-label textarea').setValue('第一行\n第二行')
    await wrapper.findAllComponents(ElButton).find(button => button.text().includes('上传并提交版本')).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('不能包含换行、Tab 或其他控制字符')
    expect(uploadProtectedVersionFile).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('连续状态刷新失败会退避并在三次后暂停，不形成请求风暴', async () => {
    getVersionSubmissionStatus.mockRejectedValue({ httpStatus: 503, message: '状态服务不可用' })
    const wrapper = mount(VersionSubmissionPanel, {
      ...mountOptions,
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, pollInterval: 250 }
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
      props: { taskId: 31, taskKind: 'shot_video', allowedActions: ['version.add'], hasAddPermission: true, canQuery: true, operationGeneration: 1, pollInterval: 250 }
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
