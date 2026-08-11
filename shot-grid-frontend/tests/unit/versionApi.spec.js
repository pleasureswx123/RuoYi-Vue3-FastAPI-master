import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  createVersionSubmission,
  downloadProtectedVersionFile,
  getCurrentTaskVersionSubmission,
  getTaskVersions,
  getVersionDetail,
  getVersionSubmissionStatus,
  preflightVersionSubmission,
  retryVersionSubmission,
  uploadProtectedVersionFile
} from '@/api/shot-grid/versions'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('版本 API 真实契约', () => {
  beforeEach(() => request.mockClear())

  it('先通过平台受保护接口上传私有文件并允许取消与进度回调', () => {
    const file = new File(['media'], '镜头.mov', { type: 'video/quicktime' })
    const signal = new AbortController().signal
    const onUploadProgress = vi.fn()
    uploadProtectedVersionFile(file, { signal, onUploadProgress })

    const config = request.mock.calls[0][0]
    expect(config).toMatchObject({
      url: '/common/files/upload',
      method: 'post',
      timeout: 120_000,
      signal,
      silentError: true,
      headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
      onUploadProgress
    })
    expect(config.data).toBeInstanceOf(FormData)
    expect(config.data.get('file')).toMatchObject({ name: file.name, size: file.size, type: file.type })
    expect(() => uploadProtectedVersionFile({ name: '伪文件.mov' })).toThrow('请选择需要提交的版本文件')
  })

  it('创建提交携带稳定幂等键且不把 HTTP 202 当作文件上传配置', () => {
    const payload = {
      fileId: '550e8400-e29b-41d4-a716-446655440000',
      changelog: '修正运动节奏',
      aiParams: null
    }
    const signal = new AbortController().signal
    createVersionSubmission(31, payload, 'version-31:key-1', { signal })
    expect(request).toHaveBeenCalledWith({
      url: '/shot-grid/tasks/31/version-submissions',
      method: 'post',
      data: payload,
      headers: { 'X-Idempotency-Key': 'version-31:key-1', repeatSubmit: false },
      signal,
      timeout: 120_000,
      silentError: true
    })
    expect(() => createVersionSubmission(31, payload, ' ')).toThrow('幂等键长度')
  })

  it('私有上传前预检使用无副作用端点且禁用统一重复提交缓存', () => {
    const payload = {
      fileName: '镜头.mov',
      fileSize: 5,
      changelog: '修正运动节奏',
      aiParams: null
    }
    const signal = new AbortController().signal
    preflightVersionSubmission(31, payload, { signal })

    expect(request).toHaveBeenCalledWith({
      url: '/shot-grid/tasks/31/version-submissions/preflight',
      method: 'post',
      data: payload,
      headers: { repeatSubmit: false },
      signal,
      silentError: true
    })
  })

  it('恢复当前提交、查询状态和人工重试使用独立真实端点', () => {
    const signal = new AbortController().signal
    getCurrentTaskVersionSubmission(31, { signal })
    getVersionSubmissionStatus(91, { signal })
    retryVersionSubmission(91, { signal })

    expect(request.mock.calls.map(([config]) => [config.method, config.url])).toEqual([
      ['get', '/shot-grid/tasks/31/version-submissions/current'],
      ['get', '/shot-grid/version-submissions/91'],
      ['post', '/shot-grid/version-submissions/91/retry']
    ])
    expect(request.mock.calls[2][0]).toMatchObject({ headers: { repeatSubmit: false }, signal, timeout: 120_000 })
  })

  it('分页历史、详情和专用授权下载均校验正整数与 UUID', () => {
    const signal = new AbortController().signal
    getTaskVersions(31, { pageNum: 2, pageSize: 10 }, { signal })
    getVersionDetail(7, { signal })
    downloadProtectedVersionFile(7, '550e8400-e29b-41d4-a716-446655440000', { signal, range: 'bytes=0-99' })

    expect(request.mock.calls[0][0]).toMatchObject({
      url: '/shot-grid/tasks/31/versions',
      method: 'get',
      params: { pageNum: 2, pageSize: 10 },
      signal
    })
    expect(request.mock.calls[1][0]).toMatchObject({ url: '/shot-grid/versions/7', method: 'get', signal })
    expect(request.mock.calls[2][0]).toMatchObject({
      url: '/shot-grid/versions/7/files/550e8400-e29b-41d4-a716-446655440000/download',
      method: 'get',
      responseType: 'blob',
      headers: { Range: 'bytes=0-99' },
      signal
    })
    expect(() => getTaskVersions('../31')).toThrow('任务 ID 必须为正整数')
    expect(() => downloadProtectedVersionFile(7, '../secret')).toThrow('文件 ID 必须是有效 UUID')
  })
})
