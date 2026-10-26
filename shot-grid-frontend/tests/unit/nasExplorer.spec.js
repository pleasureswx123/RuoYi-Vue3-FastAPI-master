import { describe, expect, it } from 'vitest'
import { validateNasFolder, versionNasFolders } from '@/utils/nasExplorer'

const folder = '\\\\192.168.10.64\\影视共享\\项目 A\\V001'
describe('NAS 路径安全边界', () => {
  it('保留合法中文目录', () => expect(validateNasFolder(folder)).toBe(folder))
  it.each([
    'C:\\Windows', '\\\\evil\\share\\folder', '\\\\192.168.10.640\\share\\folder',
    '\\\\?\\UNC\\192.168.10.64\\share\\folder', '\\\\192.168.10.64\\C$\\Windows',
    '\\\\192.168.10.64\\share', folder + '\\..', folder + '\\.', folder + '\\bad ',
    folder + '\\x:stream', folder + '\\x" /select', folder + '\\a/b', folder + '\\a\nb',
    folder + '\\%2e%2e', folder + '\\NUL.txt', folder + '\\\\child', folder + '\\a*',
    folder + '\\' + 'a'.repeat(2000)
  ])('拒绝非法路径 %s', path => expect(() => validateNasFolder(path)).toThrow())
  it('去重目录并排除派生文件，不能跨项目或跨任务取路径', () => {
    const target = { projectId: 7, taskId: 2, versionId: 3 }
    const version = { ...target, files: [{ nasPath: folder + '\\a.jpg' }, { nasPath: folder + '\\b.jpg' }, { nasPath: folder + '\\proxy\\c.jpg', role: 'thumbnail' }] }
    expect(versionNasFolders(version, target)).toEqual([folder])
    for (const key of ['projectId', 'taskId', 'versionId']) expect(() => versionNasFolders({ ...version, [key]: 99 }, target)).toThrow()
    expect(() => versionNasFolders({ ...version, files: [{ nasPath: folder + '\\evil:stream' }] }, target)).toThrow()
  })
})
