import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  archiveShot,
  assertProtectedVersionDownloadUrl,
  assignShotTask,
  commitShotImport,
  downloadShotImportTemplate,
  downloadProtectedThumbnail,
  getEpisodePage,
  getScenePage,
  getShotDetail,
  getShotPage,
  listShotAssignees,
  previewShotImport,
  updateShot
} from '@/api/shot-grid/shots'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('镜头 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('集、场次、镜头分页使用真实项目层级路径和取消信号', () => {
    const signal = new AbortController().signal
    getEpisodePage(8, { pageNum: 1, pageSize: 100 }, { signal })
    getScenePage(8, 21, { pageNum: 1, pageSize: 100 }, { signal })
    getShotPage(8, { episodeId: 21, sceneId: 31, keyword: 'S001' }, { signal })

    expect(request.mock.calls.map(([config]) => config.url)).toEqual([
      '/shot-grid/projects/8/episodes',
      '/shot-grid/projects/8/episodes/21/scenes',
      '/shot-grid/projects/8/shots'
    ])
    expect(request.mock.calls[2][0]).toMatchObject({
      params: { episodeId: 21, sceneId: 31, keyword: 'S001' },
      signal
    })
  })

  it('详情、编辑、归档和任务分配均拒绝非法 ID 并使用受控动作路径', () => {
    expect(() => getShotDetail(8, '../1')).toThrow('镜头 ID 必须为正整数')
    updateShot(8, 41, { description: '推进镜头', lockVersion: 2, assetIds: [] })
    archiveShot(8, 41, { lockVersion: 3 })
    assignShotTask(8, 41, { assigneeUserId: 7 })

    expect(request.mock.calls.map(([config]) => [config.method, config.url])).toEqual([
      ['put', '/shot-grid/projects/8/shots/41'],
      ['post', '/shot-grid/projects/8/shots/41/archive'],
      ['post', '/shot-grid/projects/8/shots/41/assign']
    ])
  })

  it('制作人下拉只调用项目内专用安全选项接口', () => {
    const signal = new AbortController().signal
    listShotAssignees(8, { pageNum: 1, pageSize: 100, keyword: '杨' }, { signal })
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/shot-grid/projects/8/shot-assignee-options',
      method: 'get',
      params: { pageNum: 1, pageSize: 100, keyword: '杨' },
      signal
    }))
  })

  it('模板通过鉴权请求层按 blob 下载，预检使用 multipart', () => {
    const signal = new AbortController().signal
    downloadShotImportTemplate({ signal })
    const file = new File(['xlsx'], '镜头.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    previewShotImport(8, file, { signal })

    expect(request.mock.calls[0][0]).toMatchObject({
      url: '/shot-grid/imports/shots/template',
      method: 'get',
      responseType: 'blob',
      signal
    })
    expect(request.mock.calls[1][0]).toMatchObject({
      url: '/shot-grid/projects/8/shots/import/preview',
      method: 'post',
      timeout: 60_000,
      headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
    })
    expect(request.mock.calls[1][0].data).toBeInstanceOf(FormData)
  })

  it('受保护缩略图只接受后端版本文件相对路径并通过 blob 下载', () => {
    const signal = new AbortController().signal
    const url = '/shot-grid/versions/31/files/550e8400-e29b-41d4-a716-446655440000/download'
    downloadProtectedThumbnail(url, { signal })
    expect(request).toHaveBeenCalledWith({
      url,
      method: 'get',
      responseType: 'blob',
      signal,
      silentError: true
    })
    expect(() => assertProtectedVersionDownloadUrl('https://example.com/secret.jpg')).toThrow('受保护版本文件路径')
    expect(() => assertProtectedVersionDownloadUrl('/shot-grid/versions/1/files/../download')).toThrow('受保护版本文件路径')
  })

  it('正式导入保留跨 Sheet 选择并携带稳定幂等键', () => {
    const payload = {
      importToken: 'token-1',
      selectedRows: [
        { sheetName: 'EP001', rowNumber: 2 },
        { sheetName: 'EP002', rowNumber: 2 }
      ]
    }
    commitShotImport(8, payload, 'shot-import:key-1')

    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/shot-grid/projects/8/shots/import/commit',
      method: 'post',
      data: payload,
      headers: { 'X-Idempotency-Key': 'shot-import:key-1', repeatSubmit: false }
    }))
  })
})
