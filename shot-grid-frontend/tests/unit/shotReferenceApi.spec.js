import { describe, it, expect, vi } from 'vitest'
import request from '@/utils/request'
import { downloadReviewReferenceFile } from '@/api/shot-grid/reviews'
vi.mock('@/utils/request', () => ({ default: vi.fn() }))
const fileId = '12345678-1234-1234-1234-123456789abc'
describe('镜头参考文件下载地址', () => {
  it.each(['/shot-grid/projects/13/shots/31', '/shot-grid/tasks/41/shot'])('接受鉴权镜头路径 %s', prefix => {
    const downloadUrl = `${prefix}/reference-files/${fileId}/download`
    downloadReviewReferenceFile({ downloadUrl })
    expect(request).toHaveBeenLastCalledWith(expect.objectContaining({ url: downloadUrl, responseType: 'blob' }))
  })
  it.each(['https://example.com', '/shot-grid/projects/13/shots/../31', '/shot-grid/tasks/41/other'])('拒绝外部或非契约路径 %s', prefix => {
    expect(() => downloadReviewReferenceFile({ downloadUrl: `${prefix}/reference-files/${fileId}/download` })).toThrow('参考文件下载地址无效')
  })
})
