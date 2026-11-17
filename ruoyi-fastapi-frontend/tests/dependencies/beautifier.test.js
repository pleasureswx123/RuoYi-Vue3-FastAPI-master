import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const require = createRequire(import.meta.url)
const beautify = require('js-beautify')
const fromBeautify = createRequire(require.resolve('js-beautify'))
const editorconfig = fromBeautify('editorconfig')

test('格式化 Vue 模板保留中文、表达式和脚本，重复格式化稳定', () => {
  const source = '<template><el-form :model="form"><el-input v-model="form.name" placeholder="镜头名称" /></el-form></template><script setup>const form={name:"镜头001"};</script><style>.shot{color:red;}</style>'
  const result = beautify.html(source, { indent_size: 2 })
  assert.match(result, /placeholder="镜头名称"/)
  assert.match(result, /v-model="form.name"/)
  assert.match(result, /镜头001/)
  assert.match(result, /color: red/)
  assert.equal(beautify.html(result, { indent_size: 2 }), result)
})

test('真实 CLI 使用升级后的 glob 与 EditorConfig 匹配并格式化嵌套文件', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'shotgrid-beautifier-'))
  try {
    mkdirSync(path.join(directory, 'src', 'nested'), { recursive: true })
    writeFileSync(path.join(directory, '.editorconfig'), 'root = true\n\n[**/*.js]\nindent_style = space\nindent_size = 4\n')
    const target = path.join(directory, 'src', 'nested', 'example.js')
    writeFileSync(target, 'function example(){return "中文测试";}')
    assert.equal(editorconfig.parseSync(target).indent_size, 4)
    const cli = path.join(path.dirname(require.resolve('js-beautify/package.json')), 'js', 'bin', 'js-beautify.js')
    execFileSync(process.execPath, [cli, '--editorconfig', '-f', 'src/**/*.js', '-r'], { cwd: directory })
    assert.match(readFileSync(target, 'utf8'), /\n {4}return "中文测试";/)
  } finally {
    // 仅清理本测试在系统临时目录下创建的专属目录。
    assert.equal(path.dirname(directory), path.resolve(tmpdir()))
    assert.ok(path.basename(directory).startsWith('shotgrid-beautifier-'))
    rmSync(directory, { recursive: true, force: true })
  }
})
