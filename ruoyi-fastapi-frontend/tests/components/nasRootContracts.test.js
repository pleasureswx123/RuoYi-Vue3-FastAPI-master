import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { transformSync } from 'esbuild'
import * as Vue from 'vue'
import ElementPlus, { ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } from 'element-plus'

const require = createRequire(import.meta.url)
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const flush = () => new Promise(resolve => setImmediate(resolve))
const nasPageSource = readFileSync(resolve(frontendRoot, 'src/views/system/nas/index.vue'), 'utf8')

function compileComponent(relativePath, dependencies = {}) {
  const filename = resolve(frontendRoot, relativePath)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const script = compileScript(descriptor, { id: filename })
  const template = compileTemplate({
    id: filename,
    filename,
    source: descriptor.template.content,
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(template.errors, [])
  const source = `${script.content.replace('export default', 'const component =')}
    ${template.code.replace('export function render', 'function render')}
    component.render = render
    export default component`
  const output = transformSync(source, { format: 'cjs', target: 'es2022' }).code
  const module = { exports: {} }
  const localRequire = name => dependencies[name] ?? require(name)
  const autoImports = ['ref', 'reactive', 'getCurrentInstance', 'toRefs', 'onServerPrefetch']
  new Function('require', 'module', 'exports', ...autoImports, output)(
    localRequire,
    module,
    module.exports,
    ...autoImports.map(name => Vue[name])
  )
  return module.exports.default
}

async function createPage(dependencies, modal) {
  const compiled = compileComponent('src/views/system/nas/index.vue', dependencies)
  let state
  const tables = []
  const component = {
    ...compiled,
    setup(props, context) {
      state ??= compiled.setup(props, context)
      Vue.onServerPrefetch(flush)
      return state
    }
  }
  const app = Vue.createSSRApp(component)
  app.use(ElementPlus)
  app.provide(ID_INJECTION_KEY, { prefix: 1, current: 0 })
  app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
  app.config.globalProperties.$modal = modal
  app.config.globalProperties.resetForm = () => {}
  app.config.globalProperties.parseTime = value => value ?? ''
  app.mixin({
    created() {
      if (this.$options.name === 'ElTable') tables.push(this.$props)
    }
  })
  const html = await renderToString(app)
  return { state, tables, html }
}

test('NAS 根目录仅允许删除已停用项，并提交锁版本后刷新列表', async () => {
  const roots = [
    {
      storageRootId: 1,
      rootName: '生产主存储',
      rootCode: 'PROD',
      uncRootPath: '\\\\192.168.10.64\\prod',
      rootStatus: 'enabled',
      lastProbeStatus: 'healthy',
      lockVersion: 4
    },
    {
      storageRootId: 2,
      rootName: '旧存储',
      rootCode: 'OLD',
      uncRootPath: '\\\\192.168.10.64\\old',
      rootStatus: 'disabled',
      lastProbeStatus: 'unknown',
      lockVersion: 7
    }
  ]
  let listCalls = 0
  let deleteArguments
  const messages = []
  const page = await createPage(
    {
      '@/api/shot-grid/storageRoot': {
        addStorageRoot: async () => ({}),
        deleteStorageRoot: async (...args) => { deleteArguments = args },
        getStorageRoot: async () => ({ data: roots[0] }),
        listStorageRoots: async () => {
          listCalls += 1
          return { rows: roots, total: roots.length }
        },
        probeStorageRoot: async () => ({}),
        updateStorageRoot: async () => ({})
      }
    },
    {
      confirm: async () => true,
      msgSuccess: message => messages.push(message)
    }
  )

  assert.equal(page.tables[0].rowKey, 'storageRootId')
  assert.match(nasPageSource, /v-if="scope\.row\.rootStatus === 'disabled'"[\s\S]*type="danger"[\s\S]*>删除<\/el-button>/)

  await page.state.handleDelete(roots[1])
  await flush()
  assert.deepEqual(deleteArguments, [2, { lockVersion: 7 }])
  assert.equal(listCalls, 2)
  assert.deepEqual(messages, ['删除成功'])
})
