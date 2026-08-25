function copyWithLegacySelection(text) {
  const documentRef = globalThis.document
  if (!documentRef?.body || typeof documentRef.execCommand !== 'function') return false

  const activeElement = documentRef.activeElement
  const textarea = documentRef.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.setAttribute('aria-hidden', 'true')
  Object.assign(textarea.style, {
    position: 'fixed',
    top: '0',
    left: '-9999px',
    opacity: '0',
    pointerEvents: 'none'
  })
  documentRef.body.appendChild(textarea)

  try {
    textarea.focus({ preventScroll: true })
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    return documentRef.execCommand('copy') === true
  } catch {
    return false
  } finally {
    textarea.remove()
    if (typeof globalThis.HTMLElement === 'function' && activeElement instanceof globalThis.HTMLElement) {
      activeElement.focus({ preventScroll: true })
    }
  }
}

export async function copyTextToClipboard(value) {
  const text = String(value ?? '')
  if (!text) return false

  try {
    const clipboard = globalThis.navigator?.clipboard
    if (typeof clipboard?.writeText === 'function') {
      try {
        await clipboard.writeText(text)
        return true
      } catch {
        // 普通 HTTP 内网页面可能拒绝 Clipboard API，此时继续使用用户点击触发的兼容复制。
      }
    }
  } catch {
    // 部分浏览器会在读取 clipboard 属性时直接抛出安全异常。
  }

  return copyWithLegacySelection(text)
}
