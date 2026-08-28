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
import * as icons from '@element-plus/icons-vue'

const require = createRequire(import.meta.url)
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const flush = () => new Promise(resolve => setImmediate(resolve))

// 使用项目现有编译器和真实 Element Plus，验证业务交给组件的数据和状态。
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
  const localRequire = name => {
    if (name in dependencies) return dependencies[name]
    if (name.endsWith('.vue')) {
      return compileComponent(resolve(dirname(filename), name), dependencies)
    }
    return require(name)
  }
  const autoImports = ['ref', 'computed', 'reactive', 'watch', 'watchEffect', 'onMounted', 'onBeforeUnmount', 'onUnmounted', 'nextTick', 'getCurrentInstance', 'toRefs']
  new Function('require', 'module', 'exports', ...autoImports, output)(
    localRequire, module, module.exports, ...autoImports.map(name => Vue[name])
  )
  return module.exports.default
}

async function createPage(relativePath, dependencies, props = {}, settle = true) {
  const compiled = compileComponent(relativePath, dependencies)
  let state
  const page = {
    async render(wait = true) {
      const tables = []
      const columns = []
      const component = {
        ...compiled,
        setup(componentProps, context) {
          state ??= compiled.setup(componentProps, context)
          if (wait) Vue.onServerPrefetch(flush)
          return state
        }
      }
      const app = Vue.createSSRApp(component, props)
      app.use(ElementPlus)
      app.provide(ID_INJECTION_KEY, { prefix: 1, current: 0 })
      app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
      for (const [name, icon] of Object.entries(icons)) app.component(name, icon)
      app.config.globalProperties.$modal = { loading() {}, closeLoading() {} }
      app.mixin({
        created() {
          if (this.$options.name === 'ElTable') tables.push(this.$props)
          if (this.$options.name === 'ElTableColumn') columns.push(this.$props)
        }
      })
      const html = await renderToString(app)
      return { html, tables, columns }
    },
    get state() { return state }
  }
  page.initial = await page.render(settle)
  return page
}

const serverData = {
  cpu: { cpuNum: 8, used: 12, sys: 5, free: 83 },
  mem: { total: '32G', used: '27G', free: '5G', usage: 84.38 },
  py: { total: '32G', used: '2G', free: '30G', usage: 6.25, name: 'CPython', version: '3.11.15', startTime: '2026-08-28 09:00:00', runTime: '2小时', home: '/usr/local/bin/python' },
  sys: { computerName: 'app-node', osName: 'Linux', computerIp: '127.0.0.1', osArch: 'x86_64', userDir: '/opt/ruoyi' },
  sysFiles: [{ dirName: '/', sysTypeName: 'ext4', typeName: 'root', total: '100G', free: '10G', used: '90G', usage: 90 }]
}

test('服务监控将内存比较和磁盘交给真实表格，并保留指标单位及稳定行键', async () => {
  const page = await createPage('src/views/monitor/server/index.vue', {
    '@/api/monitor/server': { getServer: async () => ({ data: serverData }) }
  })
  const { html, tables, columns } = page.initial
  assert.equal(tables.length, 2)
  const memory = tables.find(table => table.rowKey === 'key')
  const disk = tables.find(table => table.rowKey === 'dirName')
  assert.deepEqual(memory.data.map(row => [row.label, row.memory, row.python]), [
    ['总内存', '32G', '32G'], ['已用内存', '27G', '2G'], ['剩余内存', '5G', '30G'], ['使用率', '84.38%', '6.25%']
  ])
  assert.equal(disk.data[0].dirName, '/')
  assert.equal(disk.data[0].usage, 90)
  assert.ok(columns.some(column => column.prop === 'usage'))
  assert.match(html, /el-descriptions/)
  assert.match(html, /CPython/)
  assert.match(html, /12%/)
  assert.ok(!html.includes('NaN'), '描述单元格必须具有合法跨度')
})

test('服务监控失败会结束加载并显示重试，成功重试可恢复空磁盘状态', async () => {
  let rejectRequest
  let request = new Promise((resolve, reject) => { rejectRequest = reject })
  const page = await createPage('src/views/monitor/server/index.vue', {
    '@/api/monitor/server': { getServer: () => request }
  }, {}, false)
  assert.equal(Vue.unref(page.state.loading), true)
  rejectRequest(new Error('连接失败'))
  await flush()
  assert.equal(Vue.unref(page.state.loading), false)
  assert.match((await page.render()).html, /加载失败/)
  request = Promise.resolve({ data: { ...serverData, sysFiles: [] } })
  await page.state.getList()
  const refreshed = await page.render()
  assert.doesNotMatch(refreshed.html, /加载失败/)
  assert.deepEqual(refreshed.tables.find(table => table.rowKey === 'dirName').data, [])
  assert.equal(refreshed.tables.find(table => table.rowKey === 'dirName').emptyText, '暂无磁盘数据')
})

test('缓存键值信息使用描述组件，零 Key 仍可见且保留单位和开关含义', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { addEventListener() {}, removeEventListener() {} }
  try {
    const page = await createPage('src/views/monitor/cache/index.vue', {
      '@/api/monitor/cache': { getCache: async () => ({ data: {
        info: { redis_version: '7.4', redis_mode: 'standalone', tcp_port: 6379, connected_clients: 2, uptime_in_days: 0, used_memory_human: '4.5M', used_cpu_user_children: 0, maxmemory_human: '0B', aof_enabled: 0, rdb_last_bgsave_status: 'ok', instantaneous_input_kbps: 0, instantaneous_output_kbps: 0 },
        dbSize: 0, commandStats: []
      } }) },
      echarts: { init: () => ({ setOption() {}, resize() {}, dispose() {} }) }
    })
    assert.ok(page.initial.html.includes('el-descriptions'), '缓存信息应由描述组件渲染')
    assert.match(page.initial.html, /单机/)
    assert.match(page.initial.html, /4.5M/)
    assert.match(page.initial.html, /0\.00/)
    assert.match(page.initial.html, /Key数量/)
    assert.equal(Vue.unref(page.state.cache).dbSize, 0)
    assert.ok(!/NaN|undefined/.test(page.initial.html), '描述信息不应产生无效数值或单元格跨度')
  } finally {
    globalThis.window = previousWindow
  }
})

test('缓存加载失败可结束加载，重试后仍为图表提供命令和内存数据', async () => {
  let rejectRequest
  let request = new Promise((resolve, reject) => { rejectRequest = reject })
  const options = []
  const page = await createPage('src/views/monitor/cache/index.vue', {
    '@/api/monitor/cache': { getCache: () => request },
    echarts: { init: () => ({ setOption: option => options.push(option), resize() {}, dispose() {} }) }
  }, {}, false)
  assert.equal(Vue.unref(page.state.loading), true)
  rejectRequest(new Error('连接失败'))
  await flush()
  assert.equal(Vue.unref(page.state.loading), false)
  assert.ok((await page.render()).html.includes('加载失败'))
  request = Promise.resolve({ data: { info: { used_memory_human: '4.5M' }, dbSize: 0, commandStats: [{ name: 'get', value: 12 }] } })
  page.state.commandstats.value = {}
  page.state.usedmemory.value = {}
  await page.state.getList()
  assert.equal(Vue.unref(page.state.loadError), false)
  assert.deepEqual(options[0].series[0].data, [{ name: 'get', value: 12 }])
  assert.equal(options[1].series[0].detail.formatter, '4.5M')
  assert.equal(options[1].series[0].data[0].value, 4.5)
})

test('Cron 表格随字段编辑与重置更新，确定仍提交完整表达式', async () => {
  const fills = []
  const page = await createPage('src/components/Crontab/index.vue', {}, { onFill: value => fills.push(value) })
  assert.equal(page.initial.tables.length, 1)
  assert.equal(page.initial.tables[0].rowKey, 'id')
  page.state.updateCrontabValue('second', '0,10,20,30,40,50')
  page.state.updateCrontabValue('min', '*/5')
  const edited = await page.render()
  assert.equal(edited.tables[0].data[0].second, '0,10,20,30,40,50')
  assert.equal(edited.tables[0].data[0].expression, '0,10,20,30,40,50 */5 * * * ?')
  assert.ok(edited.columns.every(column => column.showOverflowTooltip))
  page.state.submitFill()
  assert.deepEqual(fills, ['0,10,20,30,40,50 */5 * * * ?'])
  page.state.clearCron()
  assert.equal((await page.render()).tables[0].data[0].expression, '* * * * * ?')
})
