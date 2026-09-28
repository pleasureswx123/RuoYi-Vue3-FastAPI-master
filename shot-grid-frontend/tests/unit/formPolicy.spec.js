import { readdirSync, readFileSync } from 'node:fs'
import { extname, join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')

function formTags(source) {
  // 属性引号内的箭头函数不能被误判成标签结束符。
  return source.match(/<el-form(?=[\s>])(?:[^>"']|"[^"]*"|'[^']*')*>/giu) || []
}

const formRefPattern = /\s(?:ref|:ref|v-bind:ref)\s*=\s*["']/u

function collectVueFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const target = join(directory, entry.name)
    if (entry.isDirectory()) return collectVueFiles(target)
    return extname(entry.name) === '.vue' ? [target] : []
  })
}

describe('Element Plus 表单约束', () => {
  it('支持函数 ref 与引号内的箭头，同时继续拒绝缺少 ref 的表单', () => {
    const [form] = formTags('<el-form :ref="el => { formRef = el }" :model="draft"><el-form-item /></el-form>')
    expect(form).toMatch(formRefPattern)
    expect(form).toMatch(/\s:model\s*=/u)
    expect('<el-form :model="draft">').not.toMatch(formRefPattern)
  })

  it('业务源码不依赖原生 form submit，且每个 ElForm 都声明 ref 与 model', () => {
    collectVueFiles(sourceRoot).forEach(file => {
      const source = readFileSync(file, 'utf8')
      const displayPath = relative(sourceRoot, file).replaceAll('\\', '/')

      expect(source, `${displayPath} 不得使用原生 form`).not.toMatch(/<form(?:\s|>)/iu)
      expect(source, `${displayPath} 不得监听原生 submit`).not.toMatch(/@submit(?:\.|=)/u)
      expect(source, `${displayPath} 不得把 ElButton 设为 submit`).not.toMatch(/native-type\s*=\s*["']submit["']/iu)

      for (const formTag of formTags(source)) {
        expect(formTag, `${displayPath} 的 ElForm 必须声明 ref`).toMatch(formRefPattern)
        expect(formTag, `${displayPath} 的 ElForm 必须声明 model`).toMatch(/\s:model\s*=\s*["']/u)
      }
    })
  })
})
