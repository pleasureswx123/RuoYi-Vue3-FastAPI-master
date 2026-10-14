import { beforeEach, describe, it, expect, vi } from 'vitest'
import request from '@/utils/request'
import { downloadReviewReferenceFile } from '@/api/shot-grid/reviews'
vi.mock('@/utils/request', () => ({ default: vi.fn().mockResolvedValue(new Blob(['file'])) }))
const fileId = '12345678-1234-1234-1234-123456789abc'
beforeEach(() => request.mockResolvedValue(new Blob(['file'])))
describe('镜头参考文件下载地址', () => {
  it('拒绝伪装为成功下载的 JSON 错误响应', async () => {
    request.mockResolvedValueOnce(new Blob(['{"code":500}'], { type: 'application/json' }))
    await expect(downloadReviewReferenceFile({ downloadUrl: `/shot-grid/tasks/41/shot/reference-files/${fileId}/download` })).rejects.toThrow('参考文件读取失败')
  })
  it.each(['/shot-grid/projects/13/shots/31', '/shot-grid/tasks/41/shot'])('接受鉴权镜头路径 %s', prefix => {
    const downloadUrl = `${prefix}/reference-files/${fileId}/download`
    downloadReviewReferenceFile({ downloadUrl })
    expect(request).toHaveBeenLastCalledWith(expect.objectContaining({ url: downloadUrl, responseType: 'blob' }))
  })
  it.each(['https://example.com', '/shot-grid/projects/13/shots/../31', '/shot-grid/tasks/41/other'])('拒绝外部或非契约路径 %s', prefix => {
    expect(() => downloadReviewReferenceFile({ downloadUrl: `${prefix}/reference-files/${fileId}/download` })).toThrow('参考文件下载地址无效')
  })
})
