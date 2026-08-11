import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

test('镜头查询 Store 集中维护全部查询条件并取消过期请求', async () => {
  const source = await read('src/store/modules/shotQuery.js')
  for (const field of ['projectId', 'episodeId', 'sceneId', 'assigneeUserId', 'status', 'keyword', 'orderBy', 'orderDirection', 'pageNum', 'pageSize']) assert.match(source, new RegExp(field))
  assert.match(source, /AbortController/)
  assert.match(source, /controller\?\.abort/)
})

test('表格、卡片和故事板只读取同一 Store 结果', async () => {
  const view = await read('src/views/shot/ShotListView.vue')
  assert.match(view, /:rows="store\.rows"/g)
  assert.equal((view.match(/:rows="store\.rows"/g) || []).length, 3)
  assert.doesNotMatch(view, /listShots/)
})

test('乐观锁写操作携带 lockVersion 并明确处理 409', async () => {
  const [episodes, scenes, view] = await Promise.all([read('src/api/shot-grid/episodes.js'), read('src/api/shot-grid/scenes.js'), read('src/views/project/ProjectSectionView.vue')])
  assert.match(episodes, /lockVersion/)
  assert.match(scenes, /lockVersion/)
  assert.match(view, /payload\.lockVersion = editing\.value\.lockVersion/)
  assert.match(view, /info\.status === 409/)
  assert.match(view, /刷新后比较最新数据/)
})

test('跨项目切换取消请求并清空旧结果', async () => {
  const source = await read('src/store/modules/shotQuery.js')
  assert.match(source, /this\.cancel\(\); this\.\$reset\(\)/)
  assert.match(source, /this\.query\.projectId = String/)
})

test('资产限定三种类型且详情以制作分项为最小单元', async () => {
  const [list, detail] = await Promise.all([read('src/views/asset/AssetListView.vue'), read('src/views/asset/AssetDetailView.vue')])
  for (const type of ['Character', 'Environment', 'Prop']) assert.match(list, new RegExp(type))
  assert.match(detail, /每个分项是分配制作任务、提交版本与审核的最小单元/)
  assert.match(detail, /listAssetItems/)
})
