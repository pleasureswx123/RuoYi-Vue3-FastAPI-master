import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyTextToClipboard } from '@/utils/clipboard'

const originalClipboardDescriptor = Object.getOwnPropertyDescriptor(globalThis.navigator, 'clipboard')
const originalExecCommand = document.execCommand

function setClipboard(value) {
  Object.defineProperty(globalThis.navigator, 'clipboard', {
    configurable: true,
    value
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  if (originalClipboardDescriptor) {
    Object.defineProperty(globalThis.navigator, 'clipboard', originalClipboardDescriptor)
  } else {
    delete globalThis.navigator.clipboard
  }
  if (originalExecCommand) document.execCommand = originalExecCommand
  else delete document.execCommand
  document.body.innerHTML = ''
})

describe('剪贴板兼容工具', () => {
  it('安全上下文优先使用 Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    const execCommand = vi.fn(() => true)
    setClipboard({ writeText })
    document.execCommand = execCommand

    await expect(copyTextToClipboard('NAS/项目/文件.png')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('NAS/项目/文件.png')
    expect(execCommand).not.toHaveBeenCalled()
  })

  it('普通 HTTP 页面缺少 Clipboard API 时使用选择复制回退', async () => {
    setClipboard(undefined)
    document.execCommand = vi.fn(() => {
      expect(document.querySelector('textarea')?.value).toBe('ASSET/Environment/动力舱')
      return true
    })

    await expect(copyTextToClipboard('ASSET/Environment/动力舱')).resolves.toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('Clipboard API 被拒绝时继续尝试兼容复制', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new DOMException('Not allowed', 'NotAllowedError')) })
    document.execCommand = vi.fn(() => true)

    await expect(copyTextToClipboard('EP01/SHOT/S001/file.mp4')).resolves.toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
  })

  it('两种复制方式均不可用时明确返回失败', async () => {
    setClipboard(undefined)
    document.execCommand = vi.fn(() => false)

    await expect(copyTextToClipboard('EP01/SHOT/S001/file.mp4')).resolves.toBe(false)
  })
})
