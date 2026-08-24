<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Lock, Plus, Refresh, UserFilled } from '@element-plus/icons-vue'

import { getAssetDetail, listAssetAssignees } from '@/api/shot-grid/assets'
import { assertPositiveId, getProjectDetail } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProductionHistoryPanel from '@/components/production-history/ProductionHistoryPanel.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import AssetArchiveDialog from '@/views/asset/components/AssetArchiveDialog.vue'
import AssetAssignDialog from '@/views/asset/components/AssetAssignDialog.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetItemFormDialog from '@/views/asset/components/AssetItemFormDialog.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import { assetDirectoryStatusMeta, assetErrorState, assetStatusMeta, assetTypeMeta, formatAssetDateTime, memberUserName } from '@/views/asset/assetPresentation'
import { taskPriorityMeta, taskStatusMeta, taskVersionStatusMeta } from '@/views/task/taskPresentation'

const props = defineProps({
  targetProjectId: { type: [Number, String], default: null },
  targetAssetId: { type: [Number, String], default: null },
  embedded: { type: Boolean, default: false }
})
const emit = defineEmits(['changed', 'deleted'])
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
const historyRefreshKey = ref(0)

function taskAssigneeName(task) {
  if (!task) return '未分配'
  const member = members.value.find(item => Number(item.userId) === Number(task.assigneeUserId))
  return memberUserName(member || { userId: task.assigneeUserId, nickName: task.assigneeName })
}
let controller = null
let disposed = false
let operationGeneration = 0

const projectId = computed(() => {
  try {
    return assertPositiveId(props.targetProjectId ?? route.params.projectId, '项目')
  } catch {
    return null
  }
})
const assetId = computed(() => {
  try {
    return assertPositiveId(props.targetAssetId ?? route.params.assetId, '资产')
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

const activeThumbnailItems = computed(() => [...(asset.value?.items || [])]
  .filter(item => item.lifecycleStatus === 'active')
  .sort((left, right) => Number(left.sortOrder || 0) - Number(right.sortOrder || 0)
    || Number(left.assetItemId || 0) - Number(right.assetItemId || 0)))

function assetItemVersionLabel(item) {
  if (!item?.latestVersion) return '尚未提交版本'
  const versionNo = String(item.latestVersion.versionNo).padStart(3, '0')
  return `V${versionNo} · ${taskVersionStatusMeta(item.latestVersion.versionStatus).label}`
}
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
    historyRefreshKey.value += 1
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
  if (!String(item?.productionItem || '').trim()) {
    ElMessage.warning('请先补齐制作分项，再分配或改派任务')
    if (itemCanEdit(item)) openItemForm(item)
    return
  }
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
  ElMessage.success('操作已完成；请返回对应资产查看最新结果。')
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
  emit('changed', { projectId: projectId.value, assetId: assetId.value })
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
  emit('changed', { projectId: projectId.value, assetId: assetId.value })
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
  emit('changed', { projectId: projectId.value, assetId: assetId.value })
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
    emit('changed', { projectId: projectId.value, assetId: assetId.value })
  } else {
    ElMessage.success('资产已归档')
    if (props.embedded) emit('deleted', { projectId: operationContext.projectId, assetId: operationContext.assetId })
    else await router.replace({ path: '/assets', query: { projectId: String(operationContext.projectId) } })
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

watch(
  () => [props.targetProjectId, props.targetAssetId, route.params.projectId, route.params.assetId],
  loadDetail,
  { immediate: true }
)
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  closeDialogs()
})
</script>

<template>
  <section class="sg-page asset-detail-page" :class="{ 'asset-detail-page--embedded': embedded }">
    <el-button v-if="!embedded" class="back-link" link :icon="ArrowLeft" @click="router.push({ path: '/assets', query: { projectId: String(projectId || '') } })">返回资产库</el-button>

    <el-card v-if="loading" class="detail-loading" shadow="never" aria-busy="true">
      <span class="detail-loading__label">正在加载资产详情</span>
      <el-skeleton :rows="8" animated />
    </el-card>
    <ProjectStatePanel v-else-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadDetail" />

    <template v-else-if="asset">
      <el-card class="asset-hero" shadow="never">
        <div class="asset-hero__gallery" aria-label="制作分项缩略图">
          <article v-for="item in activeThumbnailItems" :key="item.assetItemId" class="asset-hero__item">
            <ProtectedAssetThumbnail class="asset-hero__item-thumbnail" :thumbnail="item.thumbnail" :alt="`${item.productionItem || '未命名制作分项'} 缩略图`" />
            <div class="asset-hero__item-meta">
              <strong :title="item.productionItem || '未命名制作分项'">{{ item.productionItem || '未命名制作分项' }}</strong>
              <span>{{ assetItemVersionLabel(item) }}</span>
            </div>
          </article>
          <el-empty v-if="!activeThumbnailItems.length" class="asset-hero__empty" :image-size="36" description="暂无活动制作分项" />
        </div>
        <div class="asset-hero__main"><p class="sg-eyebrow">{{ project?.projectCode }} · ASSET {{ asset.assetId }}</p><div><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(asset.assetType).tone)">{{ assetTypeMeta(asset.assetType).label }}</el-tag><h2>{{ asset.assetName }}</h2><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetStatusMeta(asset.assetStatus).tone)">{{ assetStatusMeta(asset.assetStatus).label }}</el-tag></div><p>{{ asset.description || '暂无资产说明' }}</p><div class="asset-hero__summary"><small>{{ asset.itemCount }} 个制作分项 · {{ asset.usageShotCount }} 个使用镜头</small><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetDirectoryStatusMeta(asset.directoryStatus).tone)">{{ assetDirectoryStatusMeta(asset.directoryStatus).label }}</el-tag></div></div>
        <div class="asset-hero__actions"><el-button :icon="Refresh" :loading="loading" @click="loadDetail">刷新</el-button><el-button v-if="canAddItem" :icon="Plus" @click="openItemForm()">新增制作分项</el-button><el-button v-if="canEditAsset" :icon="Edit" @click="openEditAsset">编辑资产</el-button><el-button v-if="canArchiveAsset" type="danger" plain :icon="Lock" @click="openArchive()">归档资产</el-button></div>
      </el-card>

      <ProductionHistoryPanel
        :project-id="projectId"
        :subject-id="assetId"
        subject-type="asset"
        :refresh-key="historyRefreshKey"
      />

      <section class="detail-grid">
        <el-card class="detail-card" shadow="never"><template #header><h3>资产信息与目录</h3></template><el-descriptions :column="2" border><el-descriptions-item label="资产类型"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(asset.assetType).tone)">{{ assetTypeMeta(asset.assetType).label }}</el-tag></el-descriptions-item><el-descriptions-item label="存储目录名">{{ asset.storageDirName }}</el-descriptions-item><el-descriptions-item label="目录状态"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetDirectoryStatusMeta(asset.directoryStatus).tone)">{{ assetDirectoryStatusMeta(asset.directoryStatus).label }}</el-tag></el-descriptions-item><el-descriptions-item label="使用状态"><el-tag size="small" effect="plain" round :type="asset.lifecycleStatus === 'active' ? 'success' : 'info'">{{ asset.lifecycleStatus === 'active' ? '活动' : '已归档' }}</el-tag></el-descriptions-item></el-descriptions></el-card>
        <el-card class="detail-card" shadow="never"><template #header><h3>审计与说明</h3></template><el-descriptions :column="2" border><el-descriptions-item label="创建人">{{ asset.createBy }}</el-descriptions-item><el-descriptions-item label="创建时间">{{ formatAssetDateTime(asset.createTime) }}</el-descriptions-item><el-descriptions-item label="更新人">{{ asset.updateBy }}</el-descriptions-item><el-descriptions-item label="更新时间">{{ formatAssetDateTime(asset.updateTime) }}</el-descriptions-item><el-descriptions-item label="备注" :span="2">{{ asset.remark || '暂无备注' }}</el-descriptions-item></el-descriptions></el-card>
      </section>

      <el-card class="item-section" shadow="never">
        <template #header><header><div><p class="sg-eyebrow">PRODUCTION ITEMS</p><h3>制作分项</h3></div><el-tag size="small" type="info" effect="plain" round>{{ asset.items?.length || 0 }} 个</el-tag></header></template>
        <el-empty v-if="!asset.items?.length" :image-size="72" description="当前资产尚无制作分项" />
        <div v-else class="item-list">
          <el-card v-for="item in asset.items" :key="item.assetItemId" class="item-card" :class="{ 'is-archived': item.lifecycleStatus === 'archived' }" shadow="never">
            <ProtectedAssetThumbnail class="item-card__thumbnail" :thumbnail="item.thumbnail" :alt="`${item.productionItem || '未命名制作分项'} 缩略图`" />
            <div class="item-card__body"><header><div><span class="item-card__id">分项 #{{ item.assetItemId }}</span><h4>{{ item.productionItem || '未命名制作分项' }}</h4></div><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetStatusMeta(item.assetStatus).tone)">{{ assetStatusMeta(item.assetStatus).label }}</el-tag></header><p>{{ item.description || '暂无分项说明' }}</p><el-descriptions class="item-card__details" :column="4" border><el-descriptions-item label="负责人">{{ taskAssigneeName(item.task) }}</el-descriptions-item><el-descriptions-item label="任务"><span v-if="item.task" class="detail-tag-group"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskStatusMeta(item.task.taskStatus).tone)">{{ taskStatusMeta(item.task.taskStatus).label }}</el-tag><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskPriorityMeta(item.task.priority).tone)">{{ taskPriorityMeta(item.task.priority).label }}优先级</el-tag></span><el-tag v-else type="info" size="small" effect="plain" round>未分配</el-tag></el-descriptions-item><el-descriptions-item label="最新版本"><span v-if="item.latestVersion" class="detail-tag-group"><span>V{{ String(item.latestVersion.versionNo).padStart(3, '0') }}</span><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.latestVersion.versionStatus).tone)">{{ taskVersionStatusMeta(item.latestVersion.versionStatus).label }}</el-tag></span><span v-else>—</span></el-descriptions-item><el-descriptions-item label="最终版本"><span v-if="item.finalVersion" class="detail-tag-group"><span>V{{ String(item.finalVersion.versionNo).padStart(3, '0') }}</span><el-tag size="small" effect="plain" round :type="tagTypeFromTone(taskVersionStatusMeta(item.finalVersion.versionStatus).tone)">{{ taskVersionStatusMeta(item.finalVersion.versionStatus).label }}</el-tag></span><span v-else>—</span></el-descriptions-item></el-descriptions><small>{{ item.remark || '无备注' }} · 更新于 {{ formatAssetDateTime(item.updateTime) }}</small></div>
            <div class="item-card__actions"><el-button v-if="itemCanAssign(item)" text type="primary" :icon="UserFilled" @click="openAssign(item)">{{ item.task ? '改派任务' : '分配任务' }}</el-button><el-button v-if="itemCanEdit(item)" text :type="item.productionItem ? 'default' : 'warning'" :icon="Edit" @click="openItemForm(item)">{{ item.productionItem ? '编辑分项' : '补齐制作分项' }}</el-button><el-button v-if="itemCanArchive(item)" text type="danger" :icon="Lock" @click="openArchive(item)">归档分项</el-button></div>
          </el-card>
        </div>
      </el-card>

      <AssetFormDialog v-if="editAssetContext" :project-id="editAssetContext.projectId" :operation-generation="editAssetContext.operationGeneration" :asset="asset" @close="editAssetContext = null" @saved="handleAssetSaved" @refresh="loadDetail" />
      <AssetItemFormDialog v-if="itemFormContext" :project-id="itemFormContext.projectId" :operation-generation="itemFormContext.operationGeneration" :asset="asset" :item="itemFormContext.item" @close="itemFormContext = null" @saved="handleItemSaved" @refresh="loadDetail" />
      <AssetAssignDialog v-if="assignContext" :project-id="assignContext.projectId" :operation-generation="assignContext.operationGeneration" :asset="asset" :item="assignContext.item" :members="members" @close="assignContext = null" @assigned="handleAssigned" @refresh="loadDetail" />
      <AssetArchiveDialog v-if="archiveContext" :project-id="archiveContext.projectId" :operation-generation="archiveContext.operationGeneration" :asset="asset" :item="archiveContext.item" @close="archiveContext = null" @archived="handleArchived" @refresh="loadDetail" />
    </template>
  </section>
</template>

<style scoped>
.asset-detail-page{display:grid;gap:18px}.back-link{width:max-content;color:var(--sg-text-muted)}.back-link:hover{color:var(--sg-text)}.detail-loading{min-height:360px;background:var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-lg)}.detail-loading:deep(.el-card__body){padding:30px}.asset-hero{background:linear-gradient(135deg,rgba(128,191,255,.07),transparent 38%),var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-lg)}.asset-hero:deep(.el-card__body){display:grid;grid-template-columns:210px minmax(0,1fr) auto;gap:22px;align-items:center;padding:22px}.asset-hero__thumbnail{overflow:hidden;height:148px;border-radius:12px}.asset-hero__main>div{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.asset-hero h2,.asset-hero p{margin:0}.asset-hero h2{font-size:27px}.asset-hero__main>p:not(.sg-eyebrow){margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.6}.asset-hero__main small{display:block;color:var(--sg-text-muted)}.asset-hero__summary{margin-top:8px}.asset-hero__actions{display:flex;max-width:330px;gap:8px;justify-content:flex-end;flex-wrap:wrap}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.detail-card,.item-section{background:var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-md)}.detail-card:deep(.el-card__header),.item-section:deep(.el-card__header){padding:16px 20px;border-bottom-color:var(--sg-border)}.detail-card:deep(.el-card__body),.item-section:deep(.el-card__body){padding:20px}.detail-card h3{margin:0}.detail-card :deep(.el-descriptions__body),.detail-card :deep(.el-descriptions__cell),.item-card__details:deep(.el-descriptions__body),.item-card__details:deep(.el-descriptions__cell){background:var(--sg-surface-raised)!important;border-color:var(--sg-border)!important}.detail-card :deep(.el-descriptions__label),.item-card__details:deep(.el-descriptions__label){color:var(--sg-text-muted);font-size:10px}.detail-card :deep(.el-descriptions__content),.item-card__details:deep(.el-descriptions__content){color:var(--sg-text-secondary);font-size:11px;overflow-wrap:anywhere}.item-section>header,.item-section :deep(.el-card__header)>header{display:flex;align-items:center;justify-content:space-between}.item-section h3,.item-section p{margin:0}.item-list{display:grid;gap:10px}.item-card{background:var(--sg-surface-raised);border-color:var(--sg-border);border-radius:11px}.item-card:deep(.el-card__body){display:grid;grid-template-columns:140px minmax(0,1fr) auto;gap:15px;align-items:stretch;padding:13px}.item-card.is-archived{opacity:.62}.item-card__thumbnail{height:110px;border-radius:8px}.item-card__body{min-width:0}.item-card__body>header{display:flex;align-items:flex-start;justify-content:space-between}.item-card__id{color:var(--sg-text-muted);font-size:9px}.item-card h4,.item-card p{margin:0}.item-card h4{margin-top:3px}.item-card__body>p{margin-top:6px;color:var(--sg-text-muted);font-size:11px}.item-card__details{margin-top:10px}.detail-tag-group{display:flex;gap:5px;align-items:center;flex-wrap:wrap}.item-card__body>small{display:block;margin-top:8px;color:var(--sg-text-muted);font-size:9px}.item-card__actions{display:flex;max-width:120px;align-content:center;justify-content:flex-end;flex-direction:column}@media(max-width:1050px){.asset-hero:deep(.el-card__body){grid-template-columns:170px 1fr}.asset-hero__actions{grid-column:1/-1;max-width:none;justify-content:flex-start}.item-card:deep(.el-card__body){grid-template-columns:110px 1fr}.item-card__actions{grid-column:1/-1;max-width:none;flex-direction:row;justify-content:flex-start}}@media(max-width:700px){.asset-hero:deep(.el-card__body),.detail-grid,.item-card:deep(.el-card__body){grid-template-columns:1fr}.asset-hero__thumbnail{max-width:280px}}
.detail-loading__label{display:block;margin-bottom:18px;color:var(--sg-text-secondary);font-size:13px}
.asset-hero:deep(.el-card__body){grid-template-columns:minmax(260px,420px) minmax(0,1fr) auto}
.asset-hero__gallery{display:grid;min-width:0;align-self:stretch;grid-auto-flow:column;grid-auto-columns:132px;gap:10px;overflow-x:auto;padding-bottom:4px;scrollbar-width:thin}
.asset-hero__item{display:grid;min-width:0;overflow:hidden;grid-template-rows:100px auto;border:1px solid var(--sg-border);border-radius:12px;background:var(--sg-surface-raised)}
.asset-hero__item-thumbnail{height:100px}
.asset-hero__item-meta{display:grid;gap:2px;padding:7px 8px}
.asset-hero__item-meta strong{overflow:hidden;color:var(--sg-text);font-size:11px;text-overflow:ellipsis;white-space:nowrap}
.asset-hero__item-meta span{color:var(--sg-text-muted);font-size:9px;white-space:nowrap}
.asset-hero__empty{width:132px;height:148px;border:1px dashed var(--sg-border);border-radius:12px}
@media(max-width:1050px){.asset-hero:deep(.el-card__body){grid-template-columns:minmax(240px,360px) minmax(0,1fr)}.asset-hero__actions{grid-column:1/-1}}
@media(max-width:700px){.asset-hero:deep(.el-card__body){grid-template-columns:1fr}.asset-hero__gallery{width:100%;grid-auto-columns:140px}}
</style>
