import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const roots = ['src', 'tests', 'scripts']
const extensions = new Set(['.js', '.mjs', '.vue', '.scss'])
const failures = []

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name)
    if (entry.isDirectory()) await visit(file)
    else if (extensions.has(path.extname(file))) {
      const source = await readFile(file, 'utf8')
      if (/\r/.test(source)) failures.push(`${file}: 使用了 CRLF`)
      if (/[ \t]+$/m.test(source)) failures.push(`${file}: 存在行尾空白`)
      if (!source.endsWith('\n')) failures.push(`${file}: 文件末尾缺少换行`)
      if (/\.\.\/ruoyi-fastapi-frontend\/src/.test(source)) failures.push(`${file}: 禁止导入兄弟工程源码`)
    }
  }
}

await Promise.all(roots.map(visit))
if (failures.length) {
  console.error(failures.join('\n'))
  process.exitCode = 1
} else {
  console.log('源码基础规范与独立工程边界检查通过。')
}
