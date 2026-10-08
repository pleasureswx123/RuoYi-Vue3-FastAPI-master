import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { copyTextToClipboard } from '../../src/utils/clipboard.js'

const originals = new Map(['navigator', 'document', 'HTMLElement'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
afterEach(() => {
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
})

function environment(clipboard, result = true) {
  const calls = []
  class Element { focus() { calls.push('focus') } }
  const textarea = Object.assign(new Element(), {
    style: {}, setAttribute() {}, select() { calls.push('select') },
    setSelectionRange() {}, remove() { calls.push('remove') }
  })
  const document = {
    activeElement: new Element(), body: { appendChild() { calls.push('append') } },
    createElement: () => textarea,
    execCommand(command) { assert.equal(command, 'copy'); calls.push('copy'); if (result instanceof Error) throw result; return result }
  }
  for (const [key, value] of Object.entries({ navigator: { clipboard }, document, HTMLElement: Element })) {
    Object.defineProperty(globalThis, key, { configurable: true, value })
  }
  return { calls, textarea }
}

test('现代复制成功时不创建临时输入框', async () => {
  const { calls } = environment({ async writeText(text) { assert.equal(text, '聊天内容') } })
  assert.equal(await copyTextToClipboard('聊天内容'), true)
  assert.deepEqual(calls, [])
})

test('HTTP 缺少剪贴板 API 时选择文本复制并恢复焦点', async () => {
  const { calls, textarea } = environment(undefined)
  assert.equal(await copyTextToClipboard('日志内容'), true)
  assert.equal(textarea.value, '日志内容')
  assert.deepEqual(calls, ['append', 'focus', 'select', 'copy', 'remove', 'focus'])
})

test('现代复制被拒绝后仍尝试兼容复制', async () => {
  const { calls } = environment({ async writeText() { throw new Error('拒绝访问') } })
  assert.equal(await copyTextToClipboard('命令'), true)
  assert.ok(calls.includes('copy'))
})

for (const result of [false, new Error('复制失败')]) {
  test(`兼容复制${result === false ? '返回失败' : '抛异常'}时不报告成功并清理临时元素`, async () => {
    const { calls } = environment(undefined, result)
    assert.equal(await copyTextToClipboard('内容'), false)
    assert.ok(calls.includes('remove'))
  })
}

test('读取剪贴板属性发生安全异常时仍可回退', async () => {
  environment(undefined)
  Object.defineProperty(globalThis.navigator, 'clipboard', { get() { throw new Error('安全限制') } })
  assert.equal(await copyTextToClipboard('内容'), true)
})

test('空内容或缺少复制能力时明确返回失败', async () => {
  const { calls } = environment(undefined)
  assert.equal(await copyTextToClipboard(''), false)
  globalThis.document.execCommand = undefined
  assert.equal(await copyTextToClipboard('内容'), false)
  assert.deepEqual(calls, [])
})
