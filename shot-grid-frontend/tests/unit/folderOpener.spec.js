import { describe, it, expect } from 'vitest'
import { candidateFolderPath, validNasFolder, folderProtocolUrl, localDemoFolderUrl, localLayoutFolderUrl } from '@/utils/folderOpener'

describe('NAS 文件夹打开协议', () => {
  it('本地模拟只编码安全实体编号，不能传入磁盘路径或遍历参数', () => {
    expect(localDemoFolderUrl(1, 2, 3, 4)).toBe('shotgrid-folder://demo/1/2/3/4')
    expect(localDemoFolderUrl(1, 2, 3)).toBe('shotgrid-folder://demo/1/2/3/0')
    for (const id of ['../Windows', 'C:\\Windows', '1', -1, 1.5, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
      expect(localDemoFolderUrl(id, 2, 3, 4)).toBe('')
      expect(localDemoFolderUrl(1, 2, 3, id)).toBe('')
    }
    expect(localDemoFolderUrl(1, 0, 3, 4)).toBe('')
    expect(localDemoFolderUrl(1, 7, 3, 4, 2)).toBe('shotgrid-folder://demo-asset/1/2/7/3/4')
    expect(localDemoFolderUrl(1, 7, 3, 4, '../other')).toBe('')
    expect(localDemoFolderUrl(1, 7, 3, 4, -2)).toBe('')
  })
  it('中文、空格与符号编码往返一致，只选原文件目录', () => {
    const folder = String.raw`\\192.168.10.64\制作\项目 A&镜头`
    const path = candidateFolderPath([
      { role: 'proxy_media', nasPath: String.raw`\\192.168.10.64\缓存\proxy.mp4` },
      { role: 'review_media', nasPath: folder + '\\clip.mp4' }
    ])
    expect(path).toBe(folder)
    const token = folderProtocolUrl(path).split('/').at(-1).replace(/-/g, '+').replace(/_/g, '/')
    expect(new TextDecoder().decode(Uint8Array.from(atob(token), char => char.charCodeAt(0)))).toBe(folder)
    expect(candidateFolderPath([{ role: 'thumbnail', nasPath: folder + '\\thumb.jpg' }])).toBe('')
  })
  it.each([
    'C:\\Windows', String.raw`\\other\share`, String.raw`\\192.168.10.64.evil\share`,
    String.raw`\\?\UNC\192.168.10.64\share`, String.raw`\\192.168.10.64\share\..\secret`,
    String.raw`\\192.168.10.64\share\CON`, String.raw`\\192.168.10.64\share\file:stream`,
    String.raw`\\192.168.10.64\share\bad" & calc`, String.raw`\\192.168.10.64\share\trailing.`,
    '\\\\192.168.10.64\\share\\bad\nname', '', null
  ])('拒绝越界、非 UNC 或危险路径 %s', value => {
    expect(validNasFolder(value)).toBe(false)
    expect(folderProtocolUrl(value)).toBe('')
  })
})


describe('按版本映射本地目录', () => {
  it('镜头和分项使用冻结的项目名称与版本目录，不再增加候选层', () => {
    for (const path of [String.raw`项目A\SHOT\EP001\001\0001\V001`, String.raw`项目A\ASSET\Prop\宝剑\正面__7\V002`]) {
      const url = localLayoutFolderUrl(path)
      expect(url).toMatch(/^shotgrid-folder:\/\/demo-layout\//)
      const token = url.split('/').at(-1).replace(/-/g, '+').replace(/_/g, '/')
      expect(new TextDecoder().decode(Uint8Array.from(atob(token), char => char.charCodeAt(0)))).toBe(path)
    }
  })
  it.each([String.raw`C:\Windows`, String.raw`项目\SHOT\EP001\..\0001\V001`, String.raw`项目\ASSET\Prop\A\CON\V001`, String.raw`项目\SHOT\EP001\001`, String.raw`项目\ASSET\Prop\A\正面\V001`])('拒绝非法目录 %s', path => {
    expect(localLayoutFolderUrl(path)).toBe('')
  })
})
