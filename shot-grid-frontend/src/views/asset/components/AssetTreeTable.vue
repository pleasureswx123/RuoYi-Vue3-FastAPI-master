<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { View } from '@element-plus/icons-vue'

import { getAssetItems } from '@/api/shot-grid/assets'
import { useCurrentTime } from '@/composables/useCurrentTime'
import { formatTaskDateTime, taskTimeReminder } from '@/views/task/taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'
import TableActionButton from '@/components/TableActionButton.vue'
import ProtectedAssetThumbnail from './ProtectedAssetThumbnail.vue'
import AssetDescriptionCell from './AssetDescriptionCell.vue'
import { assetAssigneeSummary, assetDirectoryStatusMeta, assetErrorState, assetItemStatusEntries, assetItemTimeEntries, assetStatusMeta, assetStatusTagClass, assetTypeMeta, memberUserName, resolveAssetThumbnail } from '../assetPresentation'

const props = defineProps({
  assets: { type: Array, required: true },
  projectId: { type: Number, required: true },
  contextKey: { type: String, required: true },
  members: { type: Array, default: () => [] },
  selectedAssetIds: { type: Set, required: true },
  selectable: { type: Function, required: true },
  canQuery: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  selectionDisabled: { type: Boolean, default: false },
  backgroundRefresh: { type: Boolean, default: false }
})
const emit = defineEmits(['selection-change', 'open-item'])
const table = ref(null)
const currentTime = useCurrentTime()
const tableGeneration = ref(0)
const errors = reactive(new Map())
const childrenCache = reactive(new Map())
const loadingKeys = reactive(new Set())
const expandedKeys = new Set()
const initializedKeys = new Set()
const pending = new Map()
const treeProps = { children: 'children', hasChildren: 'hasChildren', checkStrictly: true }
let generation = 0
let disposed = false
let restoringSelection = false
const assetById = computed(() => new Map(props.assets.map(asset => [Number(asset.assetId), asset])))
const timeEntriesByAssetId = computed(() => new Map(props.assets.map(asset => [
  Number(asset.assetId), assetItemTimeEntries(asset.itemTimeGroups, currentTime.value)
])))

const rows = computed(() => props.assets.map(asset => ({
  ...asset,
  rowKind: 'asset',
  rowKey: `asset:${props.projectId}:${asset.assetId}`,
  hasChildren: props.canQuery && Number(asset.itemCount) > 0
})))

function canSelect(row) {
  return row.rowKind === 'asset' && props.selectable(row)
}

function selectionChanged(selection) {
  if (!restoringSelection) emit('selection-change', selection.filter(canSelect))
}

function restoreSelection() {
  if (!table.value) return
  restoringSelection = true
  const currentRows = new Map(rows.value.map(row => [row.rowKey, row]))
  const selection = table.value.getSelectionRows()
  const selected = new Set(selection.map(row => row.rowKey))
  for (const row of selection) {
    const currentRow = currentRows.get(row.rowKey)
    if (!currentRow || !canSelect(currentRow) || !props.selectedAssetIds.has(Number(currentRow.assetId))) {
      table.value.toggleRowSelection(row, false, true)
      selected.delete(row.rowKey)
    }
  }
  for (const row of rows.value) {
    const shouldSelect = canSelect(row) && props.selectedAssetIds.has(Number(row.assetId))
    if (selected.has(row.rowKey) !== shouldSelect) table.value.toggleRowSelection(row, shouldSelect, false)
  }
  restoringSelection = false
}

function expansionChanged(row, expanded) {
  if (row.rowKind !== 'asset') return
  if (expanded) expandedKeys.add(row.rowKey)
  else expandedKeys.delete(row.rowKey)
}

function cancelRequests() {
  generation += 1
  for (const entry of pending.values()) entry.controller.abort()
  pending.clear()
  loadingKeys.clear()
}

async function fetchChildren(row) {
  if (childrenCache.has(row.rowKey)) return childrenCache.get(row.rowKey)
  if (errors.has(row.rowKey)) return []
  if (pending.has(row.rowKey)) return pending.get(row.rowKey).promise
  const controller = new AbortController()
  const requestGeneration = generation
  const isCurrent = () => !disposed && !controller.signal.aborted && generation === requestGeneration
  loadingKeys.add(row.rowKey)
  const promise = (async () => {
    try {
      const response = await getAssetItems(props.projectId, row.assetId, { signal: controller.signal })
      if (!isCurrent()) return null
      if (!Array.isArray(response.data) || response.data.some(item =>
        Number(item.projectId) !== props.projectId || Number(item.assetId) !== Number(row.assetId))) {
        throw new Error('分项数据与当前资产不一致，请刷新后重试')
      }
      const children = response.data.filter(item => item.lifecycleStatus === 'active')
        .sort((left, right) => left.sortOrder - right.sortOrder || left.assetItemId - right.assetItemId)
        .map(item => ({ ...item, rowKind: 'item', rowKey: `item:${props.projectId}:${item.assetItemId}`, hasChildren: false }))
      childrenCache.set(row.rowKey, children)
      errors.delete(row.rowKey)
      return children
    } catch (error) {
      if (!isCurrent()) return null
      errors.set(row.rowKey, assetErrorState(error, '制作分项加载失败'))
      return []
    } finally {
      if (isCurrent()) {
        pending.delete(row.rowKey)
        loadingKeys.delete(row.rowKey)
      }
    }
  })()
  pending.set(row.rowKey, { controller, promise })
  return promise
}

async function load(row, _treeNode, resolve) {
  if (!props.canQuery || row.rowKind !== 'asset') {
    resolve([])
    return
  }
  expandedKeys.add(row.rowKey)
  const requestGeneration = generation
  const children = await fetchChildren(row)
  // 表格卸载或后台父响应移除分支后，不能调用已失效树节点的 resolve。
  const branchExists = rows.value.some(current => current.rowKey === row.rowKey && current.hasChildren)
  if (children !== null && !disposed && requestGeneration === generation && branchExists) {
    resolve(children)
    if (children.length) initializedKeys.add(row.rowKey)
  }
}

async function waitForLoads() {
  await Promise.all([...pending.values()].map(entry => entry.promise))
}

async function refreshLoadedChildren() {
  const requestGeneration = generation
  await waitForLoads()
  if (disposed || generation !== requestGeneration) return
  const validKeys = new Set(rows.value.filter(row => row.hasChildren).map(row => row.rowKey))
  for (const key of initializedKeys) {
    if (!validKeys.has(key)) table.value?.updateKeyChildren(key, [])
  }
  for (const cache of [childrenCache, errors, expandedKeys, initializedKeys]) {
    for (const key of cache.keys()) if (!validKeys.has(key)) cache.delete(key)
  }
  const loadedRows = rows.value.filter(row => childrenCache.has(row.rowKey) && !errors.has(row.rowKey))
  let needsRebuild = false
  await Promise.all(loadedRows.map(async row => {
    childrenCache.delete(row.rowKey)
    const children = await fetchChildren(row)
    if (children === null || disposed || generation !== requestGeneration) return
    if (initializedKeys.has(row.rowKey)) table.value?.updateKeyChildren(row.rowKey, children)
    // 首次 resolve([]) 不建立原生懒加载映射；只有空分支新增分项时才需要重建入口。
    else if (children.length) needsRebuild = true
  }))
  if (needsRebuild && !disposed && generation === requestGeneration) await rebuildTable(false)
}

async function rebuildTable(clearCache = true, clearExpansion = false) {
  const scrollElement = table.value?.$el?.querySelector('.el-scrollbar__wrap')
  const scrollTop = clearExpansion ? 0 : scrollElement?.scrollTop || 0
  const scrollLeft = clearExpansion ? 0 : scrollElement?.scrollLeft || 0
  cancelRequests()
  initializedKeys.clear()
  if (clearCache) {
    childrenCache.clear()
  }
  if (clearExpansion) {
    expandedKeys.clear()
    errors.clear()
  }
  const validKeys = new Set(rows.value.filter(row => row.hasChildren).map(row => row.rowKey))
  for (const key of expandedKeys) if (!validKeys.has(key)) expandedKeys.delete(key)
  for (const key of errors.keys()) if (!validKeys.has(key)) errors.delete(key)
  const requestGeneration = generation
  restoringSelection = true
  tableGeneration.value += 1
  await nextTick()
  if (disposed || generation !== requestGeneration) return
  restoreSelection()
  for (const row of rows.value) {
    if (expandedKeys.has(row.rowKey)) table.value?.toggleRowExpansion(row, true)
  }
  await Promise.all([...pending.values()].map(entry => entry.promise))
  await nextTick()
  if (disposed || generation !== requestGeneration) return
  table.value?.setScrollTop(scrollTop)
  table.value?.setScrollLeft(scrollLeft)
}

function retry(row) {
  if (props.loading || loadingKeys.has(row.rowKey)) return
  errors.delete(row.rowKey)
  expandedKeys.add(row.rowKey)
  // 空结果 resolve 后组件不再调用 load；重建原生表格恢复懒加载入口，复用其他成功分支。
  rebuildTable(false)
}

function assigneeName(row) {
  if (row.rowKind === 'asset') return assetAssigneeSummary(row.assigneeUserIds, props.members)
  if (!row.task) return '未分配'
  const member = props.members.find(item => Number(item.userId) === Number(row.task.assigneeUserId))
  return memberUserName(member || { userId: row.task.assigneeUserId, nickName: row.task.assigneeName })
}

function statusEntries(row) {
  return row.rowKind === 'asset' ? assetItemStatusEntries(row.itemStatusCounts).filter(entry => entry.count > 0) : []
}

function itemTimeState(row) {
  return taskTimeReminder({ taskStatus: row.task?.taskStatus, expectedEndTime: row.task?.expectedEndTime }, currentTime.value)
}

watch([() => props.assets, () => props.contextKey, () => props.canQuery], (next, previous) => {
  if (props.backgroundRefresh && next[1] === previous[1] && next[2] === previous[2]) {
    const validKeys = new Set(rows.value.filter(row => row.hasChildren).map(row => row.rowKey))
    // 父查询发出后仍可展开；父响应失效的分支须单独取消，不能干扰其他慢请求。
    for (const [key, entry] of pending) {
      if (validKeys.has(key)) continue
      entry.controller.abort()
      pending.delete(key)
      loadingKeys.delete(key)
    }
    return
  }
  rebuildTable(true, next[1] !== previous[1] || !next[2])
})
watch(() => props.selectedAssetIds, restoreSelection, { flush: 'post' })
watch(() => props.loading, loading => {
  if (loading) {
    cancelRequests()
    // 人工刷新允许重新读取失败分支；背景轮询不反复请求已失败或失权的分项。
    errors.clear()
  }
})
onMounted(restoreSelection)
onBeforeUnmount(() => {
  disposed = true
  cancelRequests()
})
defineExpose({ waitForLoads, refreshLoadedChildren })
</script>

<template>
  <div class="asset-table-wrap">
    <el-table ref="table" :key="tableGeneration" class="asset-data-table" :data="rows"
              row-key="rowKey" lazy :load="load" :tree-props="treeProps" :indent="20"
              max-height="620" v-loading="loading" empty-text="当前筛选没有资产"
              @selection-change="selectionChanged" @expand-change="expansionChanged">
      <el-table-column type="selection" width="48" fixed="left" :selectable="row => !selectionDisabled && canSelect(row)" :reserve-selection="true" />
      <el-table-column label="资产 / 制作分项" min-width="240" fixed="left">
        <template #default="{ row }">
          <div class="asset-identity">
            <div class="asset-identity-meta">
              <el-tag v-if="row.rowKind === 'asset'" size="small" effect="light" round :type="tagTypeFromTone(assetTypeMeta(row.assetType).tone)">{{ assetTypeMeta(row.assetType).label }}</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">制作分项</el-tag>
              <small v-if="row.rowKind === 'asset'">{{ row.itemCount }} 个分项</small>
            </div>
            <strong>{{ row.rowKind === 'asset' ? row.assetName : (row.productionItem || '未命名制作分项') }}</strong>
            <div v-if="errors.has(row.rowKey)" class="asset-items-error" role="alert">
              <span>{{ errors.get(row.rowKey).message }}</span>
              <el-button v-if="errors.get(row.rowKey).retryable" link type="primary" :loading="loadingKeys.has(row.rowKey)" :disabled="loading" @click="retry(row)">重试分项</el-button>
            </div>
            <small v-else-if="childrenCache.has(row.rowKey) && !childrenCache.get(row.rowKey).length">暂无活动分项</small>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="缩略图" width="104">
        <template #default="{ row }">
          <div class="asset-thumbnail-cell">
            <ProtectedAssetThumbnail class="asset-thumb--small" :thumbnail="resolveAssetThumbnail(row)" :alt="`${row.assetName || row.productionItem || '未命名制作分项'} 缩略图`" />
            <small v-if="row.rowKind === 'item'">{{ row.latestVersion ? `V${String(row.latestVersion.versionNo).padStart(3, '0')}` : '暂无版本' }}</small>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="300">
        <template #default="{ row }">
          <AssetDescriptionCell :common-description="row.rowKind === 'asset' ? row.description : assetById.get(Number(row.assetId))?.description"
                                :show-common-description="row.rowKind === 'asset'"
                                :item-description="row.rowKind === 'item' ? row.description : ''" :is-item="row.rowKind === 'item'" />
        </template>
      </el-table-column>
      <el-table-column prop="task.expectedStartTime" label="开始时间" width="150" class-name="task-expected-start">
        <template #default="{ row }"><span class="task-date-cell">{{ formatTaskDateTime(row.rowKind === 'item' ? row.task?.expectedStartTime : null) }}</span></template>
      </el-table-column>
      <el-table-column prop="task.expectedEndTime" label="结束时间" width="150" class-name="task-expected-end">
        <template #default="{ row }"><span class="task-date-cell">{{ formatTaskDateTime(row.rowKind === 'item' ? row.task?.expectedEndTime : null) }}</span></template>
      </el-table-column>
      <el-table-column label="时间状态" fixed="right" width="200" class-name="task-time-state">
        <template #default="{ row }">
          <el-tag v-if="row.rowKind === 'item'" :type="tagTypeFromTone(itemTimeState(row).tone)" size="small" effect="light" round>{{ itemTimeState(row).label }}</el-tag>
          <div v-else-if="timeEntriesByAssetId.get(Number(row.assetId))?.length" class="asset-time-summary">
            <el-tag v-for="entry in timeEntriesByAssetId.get(Number(row.assetId))" :key="entry.state" :type="tagTypeFromTone(entry.tone)" size="small" effect="light" round>{{ entry.label }} {{ entry.count }}</el-tag>
          </div>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="制作人" fixed="right" width="112">
        <template #default="{ row }"><span class="asset-assignee sg-table-assignee" :class="{ 'is-unassigned': row.rowKind === 'asset' ? !row.assigneeUserIds?.length : !row.task?.assigneeUserId }">{{ assigneeName(row) }}</span></template>
      </el-table-column>
      <el-table-column label="状态" fixed="right" width="200">
        <template #default="{ row }">
          <div class="asset-status">
            <template v-if="statusEntries(row).length">
              <el-tag v-for="entry in statusEntries(row)" :key="entry.status" class="asset-status-tag" :class="assetStatusTagClass(entry.status)" size="small" effect="light" round :type="tagTypeFromTone(assetStatusMeta(entry.status).tone)">{{ entry.label }} {{ entry.count }}</el-tag>
            </template>
            <el-tag v-else class="asset-status-tag" :class="assetStatusTagClass(row.assetStatus)" :type="tagTypeFromTone(assetStatusMeta(row.assetStatus).tone)" size="small" effect="light" round>{{ assetStatusMeta(row.assetStatus).label }}</el-tag>
            <el-tag v-if="row.rowKind === 'asset' && row.directoryStatus === 'failed'" class="asset-status-tag asset-status-tag--directory-failed" type="danger" size="small" effect="light" round>{{ assetDirectoryStatusMeta(row.directoryStatus).label }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="480">
        <template #default="{ row }">
          <slot v-if="row.rowKind === 'asset'" name="asset-actions" :row="row" />
          <slot v-else-if="row.rowKind === 'item'" name="item-actions" :row="row" :asset="assetById.get(Number(row.assetId))">
            <TableActionButton label="分项详情" :icon="View" @click="emit('open-item', row)" />
          </slot>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.asset-table-wrap { overflow: hidden; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.asset-data-table { width: 100%; --el-table-text-color: var(--sg-text-secondary); --el-table-header-text-color: var(--sg-text-muted); --el-table-border-color: var(--sg-border); }
.asset-data-table :deep(.el-table__cell) { padding: 11px 0; font-size: 12px; }
.asset-identity { display: inline-flex; max-width: calc(100% - 26px); vertical-align: middle; flex-direction: column; align-items: flex-start; gap: 6px; }
.asset-identity-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.asset-identity small, .asset-thumbnail-cell small { color: var(--sg-text-muted); }
.asset-identity strong, .asset-assignee, .asset-items-error { white-space: normal; overflow-wrap: anywhere; }
.asset-thumbnail-cell { display: grid; justify-items: center; gap: 4px; }
.asset-thumb--small { width: 78px; height: 52px; border-radius: 7px; }
.asset-status { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.asset-time-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.asset-items-error { display: grid; gap: 4px; margin-top: 6px; color: var(--el-color-danger); }
.asset-items-error .el-button { justify-self: start; }
.asset-data-table :deep(.el-table__row--level-1) { --el-table-tr-bg-color: var(--sg-surface-raised, var(--sg-surface)); }
.task-date-cell { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
