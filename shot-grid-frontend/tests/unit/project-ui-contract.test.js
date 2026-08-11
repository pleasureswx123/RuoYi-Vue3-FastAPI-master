import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

test('项目创建使用幂等键并阻止重复点击', async () => {
  const [api, view] = await Promise.all([read('src/api/shot-grid/projects.js'), read('src/views/project/index.vue')])
  assert.match(api, /X-Idempotency-Key/)
  assert.match(view, /submitting\.value/)
  assert.match(view, /:disabled="submitting \|\|/)
})

test('项目创建加载可用根目录、后端路径预览和可搜索多选用户', async () => {
  const [api, view] = await Promise.all([read('src/api/shot-grid/projectCreation.js'), read('src/views/project/index.vue')])
  for (const endpoint of ['storage-roots', 'path-preview', '/users']) assert.match(api, new RegExp(endpoint))
  assert.match(view, /listProjectStorageRoots/)
  assert.match(view, /multiple filterable remote/)
  assert.match(view, /pathPreview\.finalPath/)
  assert.doesNotMatch(view, /NAS 根目录 #/)
})

test('项目列表覆盖权限、失败、重试、空态和分页', async () => {
  const view = await read('src/views/project/index.vue')
  for (const marker of ['forbidden', 'loadError', 'loadProjects', 'EmptyState', 'el-pagination']) assert.match(view, new RegExp(marker))
})

test('成员按钮服从接口权限且刷新后重新请求', async () => {
  const view = await read('src/views/project/ProjectMembersView.vue')
  for (const permission of ['shotgrid:member:add', 'shotgrid:member:edit', 'shotgrid:member:remove']) assert.match(view, new RegExp(permission))
  assert.match(view, /onMounted\(loadMembers\)/)
})

test('概览直接请求聚合端点且存储未就绪禁用写入', async () => {
  const [api, overview, layout] = await Promise.all([read('src/api/shot-grid/projects.js'), read('src/views/project/ProjectOverviewView.vue'), read('src/views/project/ProjectDetailLayout.vue')])
  assert.match(api, /\/overview/)
  assert.doesNotMatch(overview, /listShots|listAssets/)
  assert.match(layout, /:disabled="!writeEnabled"/)
})
