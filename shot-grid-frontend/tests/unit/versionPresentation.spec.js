import { describe, expect, it } from 'vitest'

import {
  acceptedToSubmissionStatus,
  formatFileSize,
  isSubmissionTerminal,
  submissionStatusMeta,
  submissionStatusOrder,
  versionErrorState,
  versionStatusMeta
} from '@/components/version/versionPresentation'

describe('版本展示契约', () => {
  it('完整映射六种提交状态且只把 committed/failed 视为终态', () => {
    expect(submissionStatusOrder).toEqual(['pending', 'publishing', 'published', 'committing', 'committed'])
    expect(['pending', 'publishing', 'published', 'committing', 'committed', 'failed'].map(status => submissionStatusMeta(status).label)).toEqual([
      '等待发布', '正在发布', '文件已发布', '正在落库', '版本已形成', '发布失败'
    ])
    expect(isSubmissionTerminal('pending')).toBe(false)
    expect(isSubmissionTerminal('committed')).toBe(true)
    expect(isSubmissionTerminal('failed')).toBe(true)
  })

  it('区分 401/403/404/409/413/416/5xx 且保留稳定 errorKey', () => {
    const cases = [
      [401, '会话已失效'],
      [403, '无权访问版本'],
      [404, '版本资源不存在'],
      [409, '版本状态发生冲突'],
      [413, '文件超过上传上限'],
      [416, '文件读取范围无效'],
      [503, '版本服务异常']
    ]
    cases.forEach(([httpStatus, title]) => {
      expect(versionErrorState({ httpStatus, errorKey: `E_${httpStatus}`, message: `错误 ${httpStatus}` })).toMatchObject({
        httpStatus,
        title,
        errorKey: `E_${httpStatus}`,
        message: `错误 ${httpStatus}`
      })
    })
  })

  it('保留后端分配版本号、重放标记和文件大小语义', () => {
    expect(acceptedToSubmissionStatus({
      submissionId: 9,
      submissionStatus: 'pending',
      reservedVersionNumber: 'V003',
      businessFileName: 'P_EP001_001_S001_A_V003_1.mov',
      taskStatus: 'in_progress',
      replayed: true
    })).toMatchObject({ submissionId: 9, reservedVersionNumber: 'V003', replayed: true })
    expect(versionStatusMeta('final').label).toBe('最终版本')
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MiB')
  })
})
