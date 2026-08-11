<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Lock, Plus, Refresh, UserFilled } from '@element-plus/icons-vue'

import { getAssetDetail, listAssetAssignees } from '@/api/shot-grid/assets'
import { assertPositiveId, getProjectDetail } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import AssetArchiveDialog from '@/views/asset/components/AssetArchiveDialog.vue'
import AssetAssignDialog from '@/views/asset/components/AssetAssignDialog.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetItemFormDialog from '@/views/asset/components/AssetItemFormDialog.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import { assetDirectoryStatusMeta, assetErrorState, assetStatusMeta, assetTypeMeta, formatAssetDateTime, memberLabel, resolveAssetThumbnail } from '@/views/asset/assetPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const asset = ref(null)
const project = ref(null)
const members = ref([])
const loading = ref(false)
const errorState = ref(null)
const editAssetContext = ref(null)
const itemFormContext = ref(null)
const assignContext = ref(null)
const archiveContext = ref(null)
let controller = null
let disposed = false
let operationGeneration = 0

const projectId = computed(() => {
  try {
    return assertPositiveId(route.params.projectId, '项目')
  } catch {
    return null
  }
})
const assetId = computed(() => {
  try {
    return assertPositiveId(route.params.assetId, '资产')
  } catch {
    return null
  }
})
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const assetAllowedActions = computed(() => new Set(asset.value?.allowedActions || []))
const canEditAsset = computed(() => assetAllowedActions.value.has('asset.edit') && hasPermission('shotgrid:asset:edit'))
const canArchiveAsset = computed(() => assetAllowedActions.value.has('asset.archive') && hasPermission('shotgrid:asset:archive'))
const canAddItem = computed(() => assetAllowedActions.value.has('assetItem.add') && hasPermission('shotgrid:asset:add'))

async function fetchAllMembers(targetProjectId, signal) {
  const rows = []
  let pageNum = 1
  let hasMore = true
  while (hasMore) {
    const response = await listAssetAssignees(targetProjectId, { pageNum, pageSize: 100 }, { signal })
    rows.push(...(Array.isArray(response.rows) ? response.rows : []))
    hasMore = Boolean(response.hasNext) && pageNum < 100
    pageNum += 1
  }
  return rows
}

function closeDialogs() {
  editAssetContext.value = null
  itemFormContext.value = null
  assignContext.value = null
  archiveContext.value = null
}

async function loadDetail() {
  controller?.abort()
  closeDialogs()
  asset.value = null
  project.value = null
  members.value = []
  errorState.value = null
  const targetProjectId = projectId.value
  const targetAssetId = assetId.value
  if (!targetProjectId || !targetAssetId) {
    errorState.value = assetErrorState({ httpStatus: 404, message: '资产详情地址无效' })
    return
  }
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  try {
    const [assetResponse, projectResponse, memberRows] = await Promise.all([
      getAssetDetail(targetProjectId, targetAssetId, { signal: requestController.signal }),
      getProjectDetail(targetProjectId, { signal: requestController.signal }),
      fetchAllMembers(targetProjectId, requestController.signal)
    ])
    if (controller !== requestController || requestController.signal.aborted || projectId.value !== targetProjectId || assetId.value !== targetAssetId) return
    asset.value = assetResponse.data
    project.value = projectResponse.data
    members.value = memberRows
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !requestController.signal.aborted) {
      errorState.value = assetErrorState(error, '资产详情加载失败')
    }
  } finally {
    if (controller === requestController) loading.value = false
  }
}

function newContext(item = null) {
  return Object.freeze({
    projectId: projectId.value,
    assetId: assetId.value,
    assetItemId: item?.assetItemId ? Number(item.assetItemId) : null,
    operationGeneration: ++operationGeneration,
    item
  })
}

function openEditAsset() {
  editAssetContext.value = newContext()
}

function openItemForm(item = null) {
  itemFormContext.value = newContext(item)
}

function openAssign(item) {
  assignContext.value = newContext(item)
}

function openArchive(item = null) {
  archiveContext.value = newContext(item)
}

function contextMatches(active, operationContext) {
  return active?.projectId === Number(operationContext?.projectId) &&
    active?.assetId === Number(operationContext?.assetId) &&
    (active?.assetItemId ?? null) === (operationContext?.assetItemId == null ? null : Number(operationContext.assetItemId)) &&
    active?.operationGeneration === Number(operationContext?.operationGeneration)
}

function stillOnTarget(operationContext) {
  return projectId.value === Number(operationContext?.projectId) && assetId.value === Number(operationContext?.assetId)
}

function notifyDetachedOperation() {
  ElMessage.success('操作已完成；当前资产详情未自动刷新。')
}

async function handleAssetSaved(_result, operationContext) {
  if (disposed) return
  if (!contextMatches(editAssetContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  editAssetContext.value = null
  if (!stillOnTarget(operationContext)) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success('资产已更新')
  await loadDetail()
}

async function handleItemSaved(_result, operationContext) {
  if (disposed) return
  if (!contextMatches(itemFormContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  itemFormContext.value = null
  if (!stillOnTarget(operationContext)) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success(operationContext.assetItemId ? '制作分项已更新' : '制作分项已新增')
  await loadDetail()
}

async function handleAssigned(_result, operationContext) {
  if (disposed) return
  if (!contextMatches(assignContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  assignContext.value = null
  if (!stillOnTarget(operationContext)) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success(operationContext.wasReassign ? '资产任务已改派' : '资产任务已分配')
  await loadDetail()
}

async function handleArchived(_result, operationContext) {
  if (disposed) return
  if (!contextMatches(archiveContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  archiveContext.value = null
  if (!stillOnTarget(operationContext)) {
    notifyDetachedOperation()
    return
  }
  if (operationContext.assetItemId) {
    ElMessage.success('制作分项已归档')
    await loadDetail()
  } else {
    ElMessage.success('资产已归档')
    await router.replace({ path: '/assets', query: { projectId: String(operationContext.projectId) } })
  }
}

function itemCanEdit(item) {
  return new Set(item.allowedActions || []).has('assetItem.edit') && hasPermission('shotgrid:asset:edit')
}

function itemCanArchive(item) {
  return new Set(item.allowedActions || []).has('assetItem.archive') && hasPermission('shotgrid:asset:archive')
}

function itemCanAssign(item) {
  return new Set(item.allowedActions || []).has('task.assign') && hasPermission('shotgrid:task:assign')
}

watch(() => [route.params.projectId, route.params.assetId], loadDetail, { immediate: true })
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  closeDialogs()
})
</script>

<template>
  <section class="sg-page asset-detail-page">
    <button class="back-link" type="button" @click="router.push({ path: '/assets', query: { projectId: String(projectId || '') } })"><el-icon><ArrowLeft /></el-icon>返回资产库</button>

    <div v-if="loading" class="detail-loading">正在加载资产详情…</div>
    <ProjectStatePanel v-else-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadDetail" />

    <template v-else-if="asset">
      <section class="asset-hero">
        <ProtectedAssetThumbnail class="asset-hero__thumbnail" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" />
        <div class="asset-hero__main"><p class="sg-eyebrow">{{ project?.projectCode }} · ASSET {{ asset.assetId }}</p><div><span class="type-chip" :data-tone="assetTypeMeta(asset.assetType).tone">{{ assetTypeMeta(asset.assetType).label }}</span><h2>{{ asset.assetName }}</h2><span class="status-chip" :data-tone="assetStatusMeta(asset.assetStatus).tone">{{ assetStatusMeta(asset.assetStatus).label }}</span></div><p>{{ asset.description || '暂无资产说明' }}</p><small>{{ asset.itemCount }} 个制作分项 · {{ asset.usageShotCount }} 个使用镜头 · {{ assetDirectoryStatusMeta(asset.directoryStatus).label }}</small></div>
        <div class="asset-hero__actions"><el-button :icon="Refresh" :loading="loading" @click="loadDetail">刷新</el-button><el-button v-if="canAddItem" :icon="Plus" @click="openItemForm()">新增制作分项</el-button><el-button v-if="canEditAsset" :icon="Edit" @click="openEditAsset">编辑资产</el-button><el-button v-if="canArchiveAsset" type="danger" plain :icon="Lock" @click="openArchive()">归档资产</el-button></div>
      </section>

      <section class="detail-grid">
        <article class="detail-card"><h3>稳定身份与目录</h3><dl class="detail-fields"><div><dt>资产类型</dt><dd>{{ assetTypeMeta(asset.assetType).label }}</dd></div><div><dt>存储目录名</dt><dd>{{ asset.storageDirName }}</dd></div><div><dt>目录状态</dt><dd :data-tone="assetDirectoryStatusMeta(asset.directoryStatus).tone">{{ assetDirectoryStatusMeta(asset.directoryStatus).label }}</dd></div><div><dt>生命周期</dt><dd>{{ asset.lifecycleStatus === 'active' ? '活动' : '已归档' }}</dd></div></dl></article>
        <article class="detail-card"><h3>审计与说明</h3><dl class="detail-fields"><div><dt>创建人</dt><dd>{{ asset.createBy }}</dd></div><div><dt>创建时间</dt><dd>{{ formatAssetDateTime(asset.createTime) }}</dd></div><div><dt>更新人</dt><dd>{{ asset.updateBy }}</dd></div><div><dt>更新时间</dt><dd>{{ formatAssetDateTime(asset.updateTime) }}</dd></div></dl><p class="detail-remark">{{ asset.remark || '暂无备注' }}</p></article>
      </section>

      <section class="item-section">
        <header><div><p class="sg-eyebrow">PRODUCTION ITEMS</p><h3>制作分项</h3></div><span>{{ asset.items?.length || 0 }} 个</span></header>
        <div v-if="!asset.items?.length" class="detail-empty">当前资产尚无制作分项。</div>
        <div v-else class="item-list">
          <article v-for="item in asset.items" :key="item.assetItemId" class="item-card" :data-archived="item.lifecycleStatus === 'archived'">
            <ProtectedAssetThumbnail class="item-card__thumbnail" :thumbnail="item.thumbnail" :alt="`${item.productionItem || '未命名制作分项'} 缩略图`" />
            <div class="item-card__body"><header><div><span>分项 #{{ item.assetItemId }}</span><h4>{{ item.productionItem || '未命名制作分项' }}</h4></div><span class="status-chip" :data-tone="assetStatusMeta(item.assetStatus).tone">{{ assetStatusMeta(item.assetStatus).label }}</span></header><p>{{ item.description || '暂无分项说明' }}</p><dl><div><dt>负责人</dt><dd>{{ item.task ? memberLabel({ userId: item.task.assigneeUserId, nickName: item.task.assigneeName, producerCode: item.task.producerCode }) : '未分配' }}</dd></div><div><dt>任务</dt><dd>{{ item.task ? `${item.task.taskStatus} · ${item.task.priority}` : '尚未创建' }}</dd></div><div><dt>最新版本</dt><dd>{{ item.latestVersion ? `V${String(item.latestVersion.versionNo).padStart(3, '0')} · ${item.latestVersion.versionStatus}` : '—' }}</dd></div><div><dt>最终版本</dt><dd>{{ item.finalVersion ? `V${String(item.finalVersion.versionNo).padStart(3, '0')}` : '—' }}</dd></div></dl><small>{{ item.remark || '无备注' }} · 更新于 {{ formatAssetDateTime(item.updateTime) }}</small></div>
            <div class="item-card__actions"><el-button v-if="itemCanAssign(item)" text type="primary" :icon="UserFilled" @click="openAssign(item)">{{ item.task ? '改派任务' : '分配任务' }}</el-button><el-button v-if="itemCanEdit(item)" text :icon="Edit" @click="openItemForm(item)">编辑分项</el-button><el-button v-if="itemCanArchive(item)" text type="danger" :icon="Lock" @click="openArchive(item)">归档分项</el-button></div>
          </article>
        </div>
      </section>

      <AssetFormDialog v-if="editAssetContext" :project-id="editAssetContext.projectId" :operation-generation="editAssetContext.operationGeneration" :asset="asset" :members="members" @close="editAssetContext = null" @saved="handleAssetSaved" @refresh="loadDetail" />
      <AssetItemFormDialog v-if="itemFormContext" :project-id="itemFormContext.projectId" :operation-generation="itemFormContext.operationGeneration" :asset="asset" :item="itemFormContext.item" :members="members" @close="itemFormContext = null" @saved="handleItemSaved" @refresh="loadDetail" />
      <AssetAssignDialog v-if="assignContext" :project-id="assignContext.projectId" :operation-generation="assignContext.operationGeneration" :asset="asset" :item="assignContext.item" :members="members" @close="assignContext = null" @assigned="handleAssigned" @refresh="loadDetail" />
      <AssetArchiveDialog v-if="archiveContext" :project-id="archiveContext.projectId" :operation-generation="archiveContext.operationGeneration" :asset="asset" :item="archiveContext.item" @close="archiveContext = null" @archived="handleArchived" @refresh="loadDetail" />
    </template>
  </section>
</template>

<style scoped>
.asset-detail-page{display:grid;gap:18px}.back-link{display:inline-flex;width:max-content;gap:7px;align-items:center;padding:0;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0}.back-link:hover{color:var(--sg-text)}.detail-loading{display:grid;min-height:360px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg);place-items:center}.asset-hero{display:grid;grid-template-columns:210px minmax(0,1fr) auto;gap:22px;align-items:center;padding:22px;background:linear-gradient(135deg,rgba(128,191,255,.07),transparent 38%),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg)}.asset-hero__thumbnail{overflow:hidden;height:148px;border-radius:12px}.asset-hero__main>div{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.asset-hero h2,.asset-hero p{margin:0}.asset-hero h2{font-size:27px}.asset-hero__main>p:not(.sg-eyebrow){margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.6}.asset-hero__main small{display:block;margin-top:8px;color:var(--sg-text-muted)}.asset-hero__actions{display:flex;max-width:330px;gap:8px;justify-content:flex-end;flex-wrap:wrap}.type-chip,.status-chip{display:inline-flex;width:max-content;padding:5px 8px;font-size:10px;border-radius:999px}.type-chip[data-tone=character]{color:var(--sg-accent);background:var(--sg-accent-soft)}.type-chip[data-tone=environment]{color:#80bfff;background:rgba(128,191,255,.08)}.type-chip[data-tone=prop]{color:#8dd8a9;background:rgba(98,212,155,.08)}.status-chip{color:var(--sg-text-muted);background:rgba(255,255,255,.05)}.status-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.detail-card,.item-section{padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.detail-card h3{margin:0 0 15px}.detail-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:0;overflow:hidden;background:var(--sg-border);border-radius:9px}.detail-fields div{padding:12px;background:#11151a}dt{color:var(--sg-text-muted);font-size:10px}dd{margin:5px 0 0;color:var(--sg-text-secondary);font-size:11px;overflow-wrap:anywhere}.detail-fields dd[data-tone=success]{color:var(--sg-success)}.detail-fields dd[data-tone=warning]{color:var(--sg-accent)}.detail-fields dd[data-tone=danger]{color:var(--sg-danger)}.detail-remark{margin:12px 0 0;color:var(--sg-text-muted);font-size:11px;white-space:pre-wrap}.item-section{display:grid;gap:14px}.item-section>header{display:flex;align-items:center;justify-content:space-between}.item-section h3,.item-section p{margin:0}.item-section>header>span{color:var(--sg-text-muted);font-size:11px}.item-list{display:grid;gap:10px}.item-card{display:grid;grid-template-columns:140px minmax(0,1fr) auto;gap:15px;align-items:stretch;padding:13px;background:rgba(255,255,255,.022);border:1px solid var(--sg-border);border-radius:11px}.item-card[data-archived=true]{opacity:.62}.item-card__thumbnail{height:110px;border-radius:8px}.item-card__body{min-width:0}.item-card__body>header{display:flex;align-items:flex-start;justify-content:space-between}.item-card__body header span:not(.status-chip){color:var(--sg-text-muted);font-size:9px}.item-card h4,.item-card p{margin:0}.item-card h4{margin-top:3px}.item-card__body>p{margin-top:6px;color:var(--sg-text-muted);font-size:11px}.item-card dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:10px 0 0;overflow:hidden;background:var(--sg-border);border-radius:7px}.item-card dl div{padding:8px;background:#11151a}.item-card__body>small{display:block;margin-top:8px;color:var(--sg-text-muted);font-size:9px}.item-card__actions{display:flex;max-width:120px;align-content:center;justify-content:flex-end;flex-direction:column}.detail-empty{padding:26px;color:var(--sg-text-muted);font-size:11px;text-align:center;background:rgba(255,255,255,.02);border:1px dashed var(--sg-border);border-radius:9px}@media(max-width:1050px){.asset-hero{grid-template-columns:170px 1fr}.asset-hero__actions{grid-column:1/-1;max-width:none;justify-content:flex-start}.item-card{grid-template-columns:110px 1fr}.item-card__actions{grid-column:1/-1;max-width:none;flex-direction:row;justify-content:flex-start}.item-card dl{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.asset-hero,.detail-grid,.item-card{grid-template-columns:1fr}.asset-hero__thumbnail{max-width:280px}.detail-fields,.item-card dl{grid-template-columns:1fr}}
</style>
