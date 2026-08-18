import { describe, expect, it } from 'vitest'

import { tagTypeFromTone } from '@/utils/tag'

describe('Element Plus Tag 展示映射', () => {
  it.each([
    ['accent', 'warning'],
    ['success', 'success'],
    ['warning', 'warning'],
    ['danger', 'danger'],
    ['info', 'primary'],
    ['neutral', 'info'],
    ['muted', 'info'],
    ['character', 'warning'],
    ['environment', 'primary'],
    ['prop', 'success'],
    ['purple', 'primary'],
    ['primary', 'primary'],
    ['unknown', 'info'],
    ['constructor', 'info'],
    ['toString', 'info'],
    ['__proto__', 'info']
  ])('将 %s 映射为合法 ElTag 类型 %s', (tone, expected) => {
    expect(tagTypeFromTone(tone)).toBe(expected)
  })

  it('任何输入都只返回 Element Plus 支持的 Tag 类型', () => {
    const allowedTypes = new Set(['primary', 'success', 'info', 'warning', 'danger'])
    const tones = ['accent', 'success', 'warning', 'danger', 'info', 'neutral', 'muted', 'constructor', '__proto__', null, undefined]

    tones.forEach(tone => expect(allowedTypes.has(tagTypeFromTone(tone))).toBe(true))
  })
})
