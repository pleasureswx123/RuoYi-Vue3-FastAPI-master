import { describe, expect, it } from 'vitest'

import {
  canRetryDynamicStorageOperation,
  formatDuration,
  normalizeProjectRoleOptions,
  phaseLabel,
  projectErrorState,
  projectRoleOptionLabel,
  statusMeta,
  storageMeta
} from '@/views/project/projectPresentation'

describe('项目展示状态', () => {
  it.each([
    [403, '没有项目访问权限', false],
    [404, '项目或资源不存在', false],
    [409, '数据状态已发生变化', true],
    [422, '提交内容未通过校验', false],
    [503, '项目数据加载失败', true]
  ])('区分 HTTP %s 错误', (status, title, retryable) => {
    expect(projectErrorState({ httpStatus: status, message: '后端消息' })).toMatchObject({
      status,
      title,
      retryable,
      message: '后端消息'
    })
  })

  it('映射状态、阶段和计划时长', () => {
    expect(statusMeta('active').label).toBe('进行中')
    expect(storageMeta('failed').tone).toBe('danger')
    expect(phaseLabel('asset_production')).toBe('资产制作')
    expect(formatDuration(5_700_000)).toBe('1 小时 35 分')
    expect(formatDuration(null)).toBe('未设置')
  })

  it('只接受已绑定有效平台角色的项目角色选项', () => {
    const options = normalizeProjectRoleOptions([
      {
        projectRole: 'creator',
        projectRoleLabel: '制作人员',
        systemRoleId: 12,
        systemRoleKey: 'shotgrid_creator',
        systemRoleName: 'Shot Grid 制作人员'
      },
      { projectRole: 'director', systemRoleId: 0, systemRoleKey: '', systemRoleName: '' },
      {
        projectRole: 'director',
        systemRoleId: 13,
        systemRoleKey: 'shotgrid_creator',
        systemRoleName: '错误映射'
      }
    ])

    expect(options).toHaveLength(1)
    expect(projectRoleOptionLabel(options[0])).toBe('制作人员')
    expect(projectRoleOptionLabel({
      projectRole: 'director',
      projectRoleLabel: '项目总监',
      systemRoleName: 'Shot Grid 项目管理员'
    })).toBe('项目管理人')
  })

  it('项目级对账失败只能走项目存储重试接口', () => {
    expect(
      canRetryDynamicStorageOperation({
        operationStatus: 'failed',
        operationType: 'reconcile_directory',
        aggregateType: 'project'
      })
    ).toBe(false)
    expect(
      canRetryDynamicStorageOperation({
        operationStatus: 'failed',
        operationType: 'ensure_shot_directory',
        aggregateType: 'shot'
      })
    ).toBe(true)
  })
})
