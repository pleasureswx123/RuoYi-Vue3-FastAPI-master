import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/utils/request'
import {
  addProjectMember,
  assertPositiveId,
  createProject,
  getMemberCandidatePage,
  getProjectMemberCandidatePage,
  getProjectMemberRoleOptions,
  getProjectDetail,
  getProjectMembers,
  getProjectPage,
  getProjectRoleOptions,
  getStorageRootOptions,
  previewProjectPath,
  purgeProject,
  retryProjectStorage,
  updateProject
} from '@/api/shot-grid/projects'

vi.mock('@/utils/request', () => ({ default: vi.fn(() => Promise.resolve({ code: 200 })) }))

describe('项目 API 契约', () => {
  beforeEach(() => request.mockClear())

  it('在拼接路径前拒绝非正整数资源 ID', () => {
    expect(() => assertPositiveId('../1', '项目')).toThrow('项目 ID 必须为正整数')
    expect(() => getProjectDetail(0)).toThrow('项目 ID 必须为正整数')
    expect(assertPositiveId('18', '项目')).toBe(18)
  })

  it('项目列表保持 camelCase 查询参数和取消信号', () => {
    const signal = new AbortController().signal
    getProjectPage({ pageNum: 2, pageSize: 12, projectStatus: 'active' }, { signal })

    expect(request).toHaveBeenCalledWith({
      url: '/shot-grid/projects',
      method: 'get',
      params: { pageNum: 2, pageSize: 12, projectStatus: 'active' },
      signal,
      silentError: true
    })
  })

  it('创建与目录重试显式携带幂等键并关闭客户端重复提交拦截', () => {
    createProject({ projectCode: 'LCFR' }, 'project-create:key-1')
    retryProjectStorage(7, { reason: '网络恢复', lockVersion: 3 }, 'storage-retry:key-1')

    expect(request.mock.calls[0][0]).toMatchObject({
      url: '/shot-grid/projects',
      method: 'post',
      headers: { 'X-Idempotency-Key': 'project-create:key-1', repeatSubmit: false }
    })
    expect(request.mock.calls[1][0]).toMatchObject({
      url: '/shot-grid/projects/7/storage/retry',
      headers: { 'X-Idempotency-Key': 'storage-retry:key-1', repeatSubmit: false }
    })
  })

  it('项目编辑与成员写入使用后端真实路径和完整请求体', () => {
    const update = { projectName: '新名称', lockVersion: 4 }
    updateProject(9, update)
    addProjectMember(9, { userId: 31, projectRole: 'creator' })

    expect(request.mock.calls[0][0]).toMatchObject({ url: '/shot-grid/projects/9', method: 'put', data: update })
    expect(request.mock.calls[1][0]).toMatchObject({ url: '/shot-grid/projects/9/members', method: 'post' })
  })

  it('项目永久删除使用独立受保护路径并发送二次确认数据', () => {
    const payload = { projectName: '测试项目', reason: '演示测试数据', lockVersion: 4 }
    purgeProject(9, payload)

    expect(request).toHaveBeenCalledWith({
      url: '/shot-grid/projects/9/purge',
      method: 'post',
      data: payload,
      silentError: true
    })
  })

  it('项目选项使用 Shot Grid 专用只读接口', () => {
    getStorageRootOptions()
    getProjectRoleOptions()
    previewProjectPath(5, {
      projectType: 'ai_short_film',
      projectName: '罗刹夫人'
    })
    getMemberCandidatePage({ pageNum: 1, pageSize: 20, keyword: '杨' })
    getProjectMemberCandidatePage(9, { pageNum: 1, pageSize: 20, keyword: '杨' })
    getProjectMemberRoleOptions(9)

    expect(request.mock.calls.map(([config]) => config.url)).toEqual([
      '/shot-grid/storage-roots/options',
      '/shot-grid/project-role-options',
      '/shot-grid/storage-roots/5/project-path-preview',
      '/shot-grid/member-candidates',
      '/shot-grid/projects/9/member-candidates',
      '/shot-grid/projects/9/role-options'
    ])
    expect(request.mock.calls[2][0].headers).toEqual({ repeatSubmit: false })
  })

  it('项目成员列表支持可选项目角色过滤', () => {
    const signal = new AbortController().signal
    getProjectMembers(9, { projectRole: 'creator' }, { signal })

    expect(request).toHaveBeenCalledWith({
      url: '/shot-grid/projects/9/members',
      method: 'get',
      params: { projectRole: 'creator' },
      signal,
      silentError: true
    })
  })
})
