import { readdirSync, readFileSync } from 'node:fs'
import { extname, join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const sourceExtensions = new Set(['.vue', '.css', '.scss'])
const vueStructuralElements = new Set([
  'component',
  'keep-alive',
  'slot',
  'teleport',
  'template',
  'transition',
  'transition-group'
])
const forbiddenRawClassToken = /(?:^|[-_])(?:tag|chip|pill|badge)$/iu
const forbiddenCustomStyleToken = /(?:^|[-_])(?:chip|pill|badge)$/iu
const tagAppearanceDeclaration = /(?:^|[;\s])(?:background(?:-color)?|border(?:-(?:color|radius|style|width))?|box-shadow|color|font-size|font-weight|height|line-height|min-height|padding)\s*:/iu
const legacyTagClasses = new Set([
  'file-state',
  'preview-type',
  'review-state',
  'sg-boundary-panel__dot',
  'sg-boundary-panel__meta',
  'task-row__kind',
  'version-state',
  'workbench-hero__label'
])

function collectSourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const target = join(directory, entry.name)
    if (entry.isDirectory()) return collectSourceFiles(target)
    return sourceExtensions.has(extname(entry.name)) ? [target] : []
  })
}

function classTokens(value) {
  return value.match(/[a-z0-9_-]+/giu) || []
}

function boundClassValues(attributes) {
  const values = []
  const classAttributePattern = /(?:^|\s)class\s*=\s*(["'])([\s\S]*?)\1/gu
  const boundClassPattern = /(?:^|\s)(?::class|v-bind:class)\s*=\s*(["'])([\s\S]*?)\1/gu

  for (const match of attributes.matchAll(classAttributePattern)) values.push(match[2])
  for (const match of attributes.matchAll(boundClassPattern)) values.push(match[2])
  return values
}

function isNativeElement(tagName) {
  return !tagName.includes('-') && !vueStructuralElements.has(tagName)
}

function isForbiddenRawClass(token) {
  return forbiddenRawClassToken.test(token) || legacyTagClasses.has(token)
}

function rawTagLikeClasses(source) {
  const templateStart = source.search(/<template\b[^>]*>/iu)
  const templateOpenEnd = templateStart >= 0 ? source.indexOf('>', templateStart) : -1
  const templateCloseStart = source.lastIndexOf('</template>')
  const template = templateOpenEnd >= 0 && templateCloseStart > templateOpenEnd
    ? source.slice(templateOpenEnd + 1, templateCloseStart)
    : source
  const violations = []
  const elementPattern = /<([a-z][a-z0-9-]*)\b([^>]*)>/giu

  for (const match of template.matchAll(elementPattern)) {
    const tagName = match[1].toLowerCase()
    if (!isNativeElement(tagName)) continue

    const tokens = boundClassValues(match[2]).flatMap(classTokens)
    violations.push(...tokens.filter(isForbiddenRawClass))
  }
  return violations
}

function styleSources(source, extension) {
  if (extension !== '.vue') return [source]
  return [...source.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/giu)].map(match => match[1])
}

function customTagStyleSelectors(source, extension = '.vue') {
  const violations = []
  const rulePattern = /([^{}]+)\{([^{}]*)\}/gu
  const classPattern = /\.([_a-z][\w-]*)/giu

  for (const style of styleSources(source, extension)) {
    for (const rule of style.matchAll(rulePattern)) {
      const declarations = rule[2]
      for (const selector of rule[1].split(',')) {
        const classes = [...selector.matchAll(classPattern)].map(match => match[1])
        const targetsElementPlusTag = classes.includes('el-tag')

        for (const className of classes) {
          const isLegacy = legacyTagClasses.has(className)
          const isCustomChip = forbiddenCustomStyleToken.test(className)
          const isCustomTagAppearance = /(?:^|[-_])tag$/iu.test(className)
            && !className.startsWith('el-')
            && !targetsElementPlusTag
            && tagAppearanceDeclaration.test(declarations)

          if (isLegacy || isCustomChip || isCustomTagAppearance) violations.push(`.${className}`)
        }
      }
    }
  }
  return violations
}

describe('Element Plus Tag 约束', () => {
  it('扫描全部原生节点的静态与动态类名，同时允许 ElTag 和标签容器', () => {
    const invalidSource = `<template>
      <em class="version-state">已通过</em>
      <p :class="{ 'status-tag': active }">处理中</p>
      <strong v-bind:class="'priority-pill'">紧急</strong>
    </template>`
    const validSource = '<template><div class="tag-list"><el-tag class="status-tag">已通过</el-tag></div></template>'

    expect(rawTagLikeClasses(invalidSource)).toEqual(['version-state', 'status-tag', 'priority-pill'])
    expect(rawTagLikeClasses(validSource)).toEqual([])
  })

  it('扫描组件与外部样式中的自制标签外观，同时允许 ElTag 的布局类', () => {
    const invalidStyle = `.status-chip { display: inline-flex; }
      :deep(.priority-pill) { color: red; }
      .version-state { border-radius: 999px; }
      .status-tag { padding: 4px 8px; }`
    const validStyle = `.tag-list { display: flex; }
      .task-kind-tag { justify-self: start; }
      :deep(.el-tag) { justify-self: start; }
      .status-tag.el-tag { --el-tag-text-color: red; color: var(--el-tag-text-color); }`

    expect(customTagStyleSelectors(invalidStyle, '.scss')).toEqual([
      '.status-chip',
      '.priority-pill',
      '.version-state',
      '.status-tag'
    ])
    expect(customTagStyleSelectors(validStyle, '.css')).toEqual([])
  })

  it('业务源码不使用原生元素或 CSS 模拟标签', () => {
    collectSourceFiles(sourceRoot).forEach(file => {
      const source = readFileSync(file, 'utf8')
      const extension = extname(file)
      const displayPath = relative(sourceRoot, file).replaceAll('\\', '/')

      if (extension === '.vue') {
        expect(rawTagLikeClasses(source), `${displayPath} 应使用 ElTag 表达标记`).toEqual([])
      }
      expect(customTagStyleSelectors(source, extension), `${displayPath} 不得保留自制标签外观`).toEqual([])
    })
  })
})
