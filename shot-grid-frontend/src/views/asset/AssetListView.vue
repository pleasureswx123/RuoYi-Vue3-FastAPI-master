<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Box, Collection, Delete, Edit, Grid, List, Link, Plus, Refresh, RefreshLeft, Search, Upload } from '@element-plus/icons-vue'

import { archiveAsset, batchAssignAssetItemTasks, batchDeleteAssets, getAssetDetail, getAssetPage, listAssetAssignees } from '@/api/shot-grid/assets'
import { assertPositiveId, getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'
import AssetRequirementDialog from '@/views/asset/components/AssetRequirementDialog.vue'
import AssetDetailView from '@/views/asset/AssetDetailView.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import { assetAssigneeSummary, assetDirectoryStatusMeta, assetErrorState, assetStatusMeta, assetTypeMeta, memberLabel, resolveAssetThumbnail } from '@/views/asset/assetPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const project = ref(null)
const members = ref([])
const assets = ref([])
const selectedAssetIds = ref(new Set())
const total = ref(0)
const projectsLoading = ref(false)
const assetsLoading = ref(false)
const projectsError = ref(null)
const assetsError = ref(null)
const selectedProjectId = ref('')
const scope = ref('')
const viewMode = ref('table')
const showCreate = ref(false)
const showImport = ref(false)
const showRequirements = ref(false)
const showEdit = ref(false)
const editingAsset = ref(null)
const editContext = ref(null)
const editingAssetId = ref(null)
const deleting = ref(false)
const assigning = ref(false)
const showBatchAssign = ref(false)
const batchAssigneeUserId = ref('')
const showDetail = ref(false)
const detailAssetId = ref(null)
const createContext = ref(null)
const importContext = ref(null)
const assetFilterForm = ref(null)
const query = reactive({
  keyword: '',
  assetType: '',
  assetStatus: '',
  assigneeUserId: '',
  pageNum: 1,
  pageSize: 20,
  orderByColumn: 'sortOrder',
  isAsc: 'ascending'
})
let projectController = null
let assetController = null
let disposed = false
let operationGeneration = 0

const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canViewAll = computed(() => hasPermission('shotgrid:project:all'))
const projectAllowedActions = computed(() => new Set(project.value?.allowedActions || []))
const canCreate = computed(() => projectAllowedActions.value.has('asset.create') && hasPermission('shotgrid:asset:add'))
const canImport = computed(() => projectAllowedActions.value.has('asset.import') && hasPermission('shotgrid:asset:import'))
const isDirector = computed(() => project.value?.myProjectRole === 'director' || wildcard.value || canViewAll.value)
const projectAllowsWrites = computed(() => project.value && !['completed', 'archived'].includes(project.value.projectStatus) && project.value.storageStatus === 'ready')
const canEdit = computed(() => isDirector.value && hasPermission('shotgrid:asset:edit') && projectAllowsWrites.value)
const canDelete = computed(() => isDirector.value && hasPermission('shotgrid:asset:archive') && projectAllowsWrites.value)
const canAssign = computed(() => isDirector.value && hasPermission('shotgrid:task:assign') && projectAllowsWrites.value)
const canListRequirements = computed(() => hasPermission('shotgrid:assetRequirement:list'))
const canResolveRequirements = computed(() => hasPermission('shotgrid:assetRequirement:resolve'))
const canIgnoreRequirements = computed(() => hasPermission('shotgrid:assetRequirement:ignore'))
const canRematchRequirements = computed(() => hasPermission('shotgrid:assetRequirement:rematch'))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const currentProjectId = computed(() => {
  try {
    return assertPositiveId(selectedProjectId.value, '项目')
  } catch {
    return null
  }
})
const groupedAssets = computed(() => ['Character', 'Environment', 'Prop'].map(type => ({
  type,
  assets: assets.value.filter(asset => asset.assetType === type)
})))
const creatorMembers = computed(() => members.value.filter(member => member.projectRole === 'creator'))
const selectedAssets = computed(() => assets.value.filter(asset => selectedAssetIds.value.has(Number(asset.assetId))))
const hasAssignedSelection = computed(() => selectedAssets.value.some(asset => (asset.assigneeUserIds || []).length))
const batchAssignLabel = computed(() => hasAssignedSelection.value ? '批量重新分配' : '批量分配')
const detailAsset = computed(() => assets.value.find(asset => Number(asset.assetId) === detailAssetId.value) || null)
const detailDrawerTitle = computed(() => detailAsset.value ? `资产详情 · ${detailAsset.value.assetName}` : '资产详情')
const selectableAssets = computed(() => assets.value.filter(asset => canSelectAsset(asset)))
const allSelectableSelected = computed(() => Boolean(selectableAssets.value.length) && selectableAssets.value.every(asset => selectedAssetIds.value.has(Number(asset.assetId))))
const canDeleteSelection = computed(() => Boolean(selectedAssets.value.length) && selectedAssets.value.every(asset => canDeleteAsset(asset)))

function canEditAsset(asset) {
  return canEdit.value && (asset?.allowedActions || []).includes('asset.edit')
}

function canDeleteAsset(asset) {
  return canDelete.value && (asset?.allowedActions || []).includes('asset.archive')
}

function canAssignAsset(asset) {
  return canAssign.value && (asset?.allowedActions || []).includes('task.assign')
}

function canSelectAsset(asset) {
  return canAssignAsset(asset) || canDeleteAsset(asset)
}

async function fetchAllPages(loader, baseParams, signal) {
  const rows = []
  let pageNum = 1
  let hasMore = true
  while (hasMore) {
    const response = await loader({ ...baseParams, pageNum, pageSize: 100 }, { signal })
    rows.push(...(Array.isArray(response.rows) ? response.rows : []))
    hasMore = Boolean(response.hasNext) && pageNum < 100
    pageNum += 1
  }
  return rows
}

async function loadProjects(preferredId = null) {
  projectController?.abort()
  const controller = new AbortController()
  projectController = controller
  projectsLoading.value = true
  projectsError.value = null
  try {
    const rows = await fetchAllPages(
      (params, options) => getProjectPage(params, options),
      { scope: scope.value || undefined, orderByColumn: 'projectName', isAsc: 'ascending' },
      controller.signal
    )
    if (projectController !== controller || controller.signal.aborted) return
    projects.value = rows
    const routeId = preferredId || route.query.projectId
    const candidate = rows.find(item => String(item.projectId) === String(routeId)) || rows[0]
    selectedProjectId.value = candidate ? String(candidate.projectId) : ''
  } catch (error) {
    if (projectController === controller && !controller.signal.aborted && error?.code !== 'ERR_CANCELED') {
      projects.value = []
      selectedProjectId.value = ''
      projectsError.value = assetErrorState(error, '项目范围加载失败')
    }
  } finally {
    if (projectController === controller) projectsLoading.value = false
  }
}

async function loadProjectContext() {
  const projectId = currentProjectId.value
  assetController?.abort()
  project.value = null
  members.value = []
  assets.value = []
  selectedAssetIds.value = new Set()
  total.value = 0
  assetsError.value = null
  if (!projectId) return
  const controller = new AbortController()
  assetController = controller
  assetsLoading.value = true
  try {
    await router.replace({ query: { ...route.query, projectId: String(projectId) } })
    if (assetController !== controller || controller.signal.aborted || currentProjectId.value !== projectId) return
    const [detailResponse, memberRows] = await Promise.all([
      getProjectDetail(projectId, { signal: controller.signal }),
      fetchAllPages(
        (params, options) => listAssetAssignees(projectId, params, options),
        {},
        controller.signal
      )
    ])
    if (assetController !== controller || controller.signal.aborted || currentProjectId.value !== projectId) return
    project.value = detailResponse.data
    members.value = memberRows
    await loadAssets(controller)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') assetsError.value = assetErrorState(error, '资产项目上下文加载失败')
  } finally {
    if (assetController === controller) assetsLoading.value = false
  }
}

async function loadAssets(existingController = null) {
  const projectId = currentProjectId.value
  if (!projectId) return
  if (!existingController) assetController?.abort()
  const controller = existingController || new AbortController()
  assetController = controller
  assetsLoading.value = true
  assetsError.value = null
  try {
    const response = await getAssetPage(projectId, {
      keyword: query.keyword.trim() || undefined,
      assetType: query.assetType || undefined,
      assetStatus: query.assetStatus || undefined,
      assigneeUserId: query.assigneeUserId || undefined,
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: query.orderByColumn,
      isAsc: query.isAsc
    }, { signal: controller.signal })
    if (assetController !== controller || controller.signal.aborted || currentProjectId.value !== projectId) return
    assets.value = Array.isArray(response.rows) ? response.rows : []
    selectedAssetIds.value = new Set()
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      assets.value = []
      selectedAssetIds.value = new Set()
      total.value = 0
      assetsError.value = assetErrorState(error, '资产列表加载失败')
    }
  } finally {
    if (assetController === controller) assetsLoading.value = false
  }
}

function submitFilters() {
  query.pageNum = 1
  loadAssets()
}

function resetFilters() {
  assetFilterForm.value?.resetFields()
  query.pageNum = 1
  loadAssets()
}

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum) return
  query.pageNum = page
  loadAssets()
}

function openAsset(asset) {
  const targetAssetId = Number(asset?.assetId)
  if (!currentProjectId.value || !Number.isSafeInteger(targetAssetId) || targetAssetId <= 0) return
  detailAssetId.value = targetAssetId
  showDetail.value = true
}

function closeDetailDrawer() {
  showDetail.value = false
}

function clearDetailDrawer() {
  detailAssetId.value = null
}

async function handleDetailChanged(operationContext) {
  if (
    currentProjectId.value !== Number(operationContext?.projectId) ||
    detailAssetId.value !== Number(operationContext?.assetId)
  ) return
  await loadAssets()
}

async function handleDetailDeleted(operationContext) {
  if (currentProjectId.value !== Number(operationContext?.projectId)) return
  closeDetailDrawer()
  await loadAssets()
}

function toggleAssetSelection(asset) {
  if (!canSelectAsset(asset)) return
  const assetId = Number(asset.assetId)
  const next = new Set(selectedAssetIds.value)
  if (next.has(assetId)) next.delete(assetId)
  else next.add(assetId)
  selectedAssetIds.value = next
}

function toggleAllSelectable() {
  selectedAssetIds.value = allSelectableSelected.value
    ? new Set()
    : new Set(selectableAssets.value.map(asset => Number(asset.assetId)))
}

function openBatchAssignDialog() {
  if (!selectedAssets.value.length || assigning.value || deleting.value) return
  batchAssigneeUserId.value = ''
  showBatchAssign.value = true
}

function closeBatchAssignDialog() {
  if (assigning.value) return
  showBatchAssign.value = false
  batchAssigneeUserId.value = ''
}

async function confirmBatchAssign() {
  if (assigning.value || !selectedAssets.value.length) return
  const assigneeUserId = Number(batchAssigneeUserId.value)
  const member = creatorMembers.value.find(item => Number(item.userId) === assigneeUserId)
  if (!member) {
    ElMessage.warning('请先选择要分配的新制作人')
    return
  }
  const targetProjectId = currentProjectId.value
  const targetAssets = [...selectedAssets.value]
  assigning.value = true
  try {
    const responses = await Promise.all(targetAssets.map(asset => getAssetDetail(targetProjectId, asset.assetId)))
    if (currentProjectId.value !== targetProjectId) return
    const details = responses.map(response => response.data)
    const activeItems = details.flatMap(detail => (detail.items || []).filter(item => item.lifecycleStatus === 'active'))
    const unnamedItem = activeItems.find(item => !String(item.productionItem || '').trim())
    if (unnamedItem) {
      const parent = details.find(detail => (detail.items || []).some(item => Number(item.assetItemId) === Number(unnamedItem.assetItemId)))
      ElMessage.warning(`${parent?.assetName || '所选资产'}存在未填写制作分项的记录，请先编辑补齐后再分配`)
      return
    }
    const blockedItem = activeItems.find(item => !(item.allowedActions || []).includes('task.assign'))
    if (blockedItem) {
      ElMessage.warning(`${blockedItem.productionItem || '待补制作分项'} 已完成或存在待处理提交，不能改派`)
      return
    }
    if (!activeItems.length) {
      ElMessage.warning('所选资产没有可分配的制作分项')
      return
    }
    if (activeItems.length > 200) {
      ElMessage.warning('单次最多分配 200 个制作分项，请减少所选资产')
      return
    }
    const items = activeItems.map(item => ({
      assetItemId: item.assetItemId,
      taskLockVersion: item.task?.lockVersion ?? null
    }))
    await batchAssignAssetItemTasks(targetProjectId, assigneeUserId, items)
    ElMessage.success(`已将 ${targetAssets.length} 个资产的 ${items.length} 个制作分项分配给 ${member.nickName || member.userName}`)
    if (currentProjectId.value === targetProjectId) {
      showBatchAssign.value = false
      batchAssigneeUserId.value = ''
      selectedAssetIds.value = new Set()
      await loadAssets()
    }
  } catch (error) {
    const state = assetErrorState(error, '资产批量分配失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409 && currentProjectId.value === targetProjectId) await loadAssets()
  } finally {
    assigning.value = false
  }
}

async function openEditDialog(asset) {
  if (!canEditAsset(asset) || deleting.value || editingAssetId.value) return
  const targetProjectId = currentProjectId.value
  const targetAssetId = Number(asset.assetId)
  const generation = ++operationGeneration
  editingAssetId.value = targetAssetId
  try {
    const response = await getAssetDetail(targetProjectId, targetAssetId)
    if (currentProjectId.value !== targetProjectId || generation !== operationGeneration) return
    editingAsset.value = response.data
    editContext.value = Object.freeze({ projectId: targetProjectId, assetId: targetAssetId, operationGeneration: generation })
    showEdit.value = true
  } catch (error) {
    const state = assetErrorState(error, '资产编辑数据加载失败')
    ElMessage.error(`${state.title}：${state.message}`)
  } finally {
    if (editingAssetId.value === targetAssetId) editingAssetId.value = null
  }
}

function closeEditDialog() {
  showEdit.value = false
  editingAsset.value = null
  editContext.value = null
}

async function deleteAsset(asset) {
  if (!canDeleteAsset(asset) || deleting.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除资产“${asset.assetName}”及其尚未开始的制作分项任务吗？`,
      '删除资产',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  const targetProjectId = currentProjectId.value
  deleting.value = true
  try {
    await archiveAsset(targetProjectId, asset.assetId, {
      lockVersion: asset.lockVersion,
      reason: '资产列表删除'
    })
    ElMessage.success('资产已删除')
    if (currentProjectId.value === targetProjectId) {
      if (detailAssetId.value === Number(asset.assetId)) closeDetailDrawer()
      await loadAssets()
    }
  } catch (error) {
    const state = assetErrorState(error, '资产删除失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409 && currentProjectId.value === targetProjectId) await loadAssets()
  } finally {
    deleting.value = false
  }
}

async function deleteSelectedAssets() {
  if (!canDeleteSelection.value || deleting.value) return
  const targets = [...selectedAssets.value]
  try {
    await ElMessageBox.confirm(
      `确认批量删除所选 ${targets.length} 个资产及其尚未开始的制作分项任务吗？`,
      '批量删除资产',
      { type: 'warning', confirmButtonText: '批量删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  const targetProjectId = currentProjectId.value
  deleting.value = true
  try {
    await batchDeleteAssets(targetProjectId, targets.map(asset => ({
      assetId: asset.assetId,
      lockVersion: asset.lockVersion
    })))
    ElMessage.success(`已删除 ${targets.length} 个资产`)
    if (currentProjectId.value === targetProjectId) {
      if (targets.some(asset => Number(asset.assetId) === detailAssetId.value)) closeDetailDrawer()
      selectedAssetIds.value = new Set()
      await loadAssets()
    }
  } catch (error) {
    const state = assetErrorState(error, '资产批量删除失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409 && currentProjectId.value === targetProjectId) await loadAssets()
  } finally {
    deleting.value = false
  }
}

function openCreateDialog() {
  if (!currentProjectId.value) return
  createContext.value = Object.freeze({ projectId: currentProjectId.value, operationGeneration: ++operationGeneration })
  showCreate.value = true
}

function openImportDialog() {
  if (!currentProjectId.value) return
  importContext.value = Object.freeze({ projectId: currentProjectId.value, operationGeneration: ++operationGeneration })
  showImport.value = true
}

function openRequirementDialog() {
  if (!currentProjectId.value) return
  showRequirements.value = true
}

function closeCreateDialog() {
  showCreate.value = false
  createContext.value = null
}

function closeImportDialog() {
  showImport.value = false
  importContext.value = null
}

function closeRequirementDialog() {
  showRequirements.value = false
}

function contextMatches(active, operationContext) {
  return active?.projectId === Number(operationContext?.projectId) && active?.operationGeneration === Number(operationContext?.operationGeneration)
}

function notifyDetachedOperation() {
  ElMessage.success('操作已完成；当前项目未自动刷新。')
}

async function handleSaved(_result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!contextMatches(createContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeCreateDialog()
  if (currentProjectId.value !== targetProjectId) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success('资产已创建')
  await loadAssets()
}

async function handleEdited(_result, operationContext) {
  if (disposed) return
  if (
    editContext.value?.projectId !== Number(operationContext?.projectId) ||
    editContext.value?.assetId !== Number(operationContext?.assetId) ||
    editContext.value?.operationGeneration !== Number(operationContext?.operationGeneration)
  ) {
    notifyDetachedOperation()
    return
  }
  const targetProjectId = editContext.value.projectId
  closeEditDialog()
  if (currentProjectId.value !== targetProjectId) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success('资产已更新')
  await loadAssets()
}

async function handleImported(result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!contextMatches(importContext.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeImportDialog()
  if (currentProjectId.value !== targetProjectId) {
    notifyDetachedOperation()
    return
  }
  ElMessage.success(`资产导入完成：新增 ${Object.values(result.createdAssetsByType || {}).reduce((sum, count) => sum + Number(count || 0), 0)} 个资产`)
  query.pageNum = 1
  await loadAssets()
}

watch(selectedProjectId, (next, previous) => {
  if (next === previous) return
  closeCreateDialog()
  closeImportDialog()
  closeRequirementDialog()
  closeEditDialog()
  closeDetailDrawer()
  clearDetailDrawer()
  showBatchAssign.value = false
  batchAssigneeUserId.value = ''
  selectedAssetIds.value = new Set()
  query.pageNum = 1
  query.assigneeUserId = ''
  loadProjectContext()
})
watch(scope, () => loadProjects())
watch(() => route.query.projectId, next => {
  if (next && String(next) !== selectedProjectId.value && projects.value.some(item => String(item.projectId) === String(next))) {
    selectedProjectId.value = String(next)
  }
})
onMounted(() => loadProjects(route.query.projectId))
onBeforeUnmount(() => {
  disposed = true
  projectController?.abort()
  assetController?.abort()
})
</script>

<template>
  <section class="sg-page asset-page">
    <header class="sg-page-heading asset-heading">
      <div><p class="sg-eyebrow">ASSETS</p><h2 class="sg-page-title">资产库管理</h2><p class="sg-page-description">在项目范围内管理角色、场景、道具及其制作分项；状态、制作人和缩略图均来自后端聚合。</p></div>
      <div class="asset-heading__actions"><el-button v-if="canListRequirements" :icon="Link" @click="openRequirementDialog">待匹配需求</el-button><el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建资产</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form class="project-context" inline label-position="top" aria-label="项目上下文">
        <el-form-item label="当前项目"><el-select v-model="selectedProjectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :disabled="projectsLoading"><el-option :label="projectsLoading ? '正在加载项目…' : '请选择项目'" value="" /><el-option v-for="item in projects" :key="item.projectId" :label="`${item.projectCode} · ${item.projectName}`" :value="String(item.projectId)" /></el-select></el-form-item>
        <el-form-item v-if="canViewAll" label="项目范围"><el-select v-model="scope" class="sg-select" placeholder="我的项目"><el-option label="我的项目" value="" /><el-option label="全部项目" value="all" /></el-select></el-form-item>
        <div v-if="project" class="project-context__meta"><el-tag size="small" effect="plain">{{ project.projectTypeName }}</el-tag><el-tag size="small" effect="plain">{{ project.aspectRatio }}</el-tag><el-tag size="small" effect="plain">{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</el-tag><el-tag size="small" effect="plain" :type="project.storageStatus === 'ready' ? 'success' : project.storageStatus === 'failed' ? 'danger' : 'warning'">存储：{{ project.storageStatus === 'ready' ? '就绪' : project.storageStatus === 'failed' ? '失败' : '初始化中' }}</el-tag></div>
      </el-form>

      <section v-if="!selectedProjectId && !projectsLoading" class="asset-empty"><el-icon><Collection /></el-icon><h3>当前范围暂无可选项目</h3><p>请先创建项目或加入项目成员范围。</p></section>

      <template v-else-if="selectedProjectId">
        <el-form ref="assetFilterForm" :model="query" class="asset-filters" aria-label="资产筛选" @submit.prevent="submitFilters">
          <el-form-item class="asset-filter-item asset-filter-item--keyword" prop="keyword">
            <el-input v-model="query.keyword" class="asset-search sg-input" :prefix-icon="Search" maxlength="200" clearable placeholder="资产名称或描述" aria-label="按资产名称或描述搜索" />
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assetType">
            <el-select v-model="query.assetType" class="sg-select" placeholder="全部类型" aria-label="按资产类型筛选" @change="submitFilters"><el-option label="全部类型" value="" /><el-option label="角色" value="Character" /><el-option label="场景" value="Environment" /><el-option label="道具" value="Prop" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assetStatus">
            <el-select v-model="query.assetStatus" class="sg-select" placeholder="全部状态" aria-label="按资产状态筛选" @change="submitFilters"><el-option label="全部状态" value="" /><el-option label="未分配" value="unassigned" /><el-option label="未开始" value="not_started" /><el-option label="制作中" value="in_progress" /><el-option label="待审核" value="reviewing" /><el-option label="修改中" value="revision" /><el-option label="已完成" value="completed" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assigneeUserId">
            <el-select v-model="query.assigneeUserId" class="sg-select" placeholder="全部制作人" aria-label="按制作人筛选" @change="submitFilters"><el-option label="全部制作人" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-actions">
            <el-button type="primary" native-type="submit" :icon="Search" :loading="assetsLoading">查询</el-button>
            <el-button :icon="RefreshLeft" :disabled="assetsLoading" @click="resetFilters">重置</el-button>
            <el-button :icon="Refresh" :disabled="assetsLoading" @click="loadProjectContext">刷新</el-button>
          </el-form-item>
        </el-form>

        <section class="asset-toolbar"><div class="asset-toolbar__summary"><strong>{{ total }}</strong><span>个资产</span><template v-if="selectedAssets.length"><el-button v-if="canAssign" text type="primary" :loading="assigning" @click="openBatchAssignDialog">{{ batchAssignLabel }}（{{ selectedAssets.length }}）</el-button><el-button v-if="canDelete" text type="danger" :icon="Delete" :loading="deleting" :disabled="!canDeleteSelection" @click="deleteSelectedAssets">批量删除（{{ selectedAssets.length }}）</el-button></template></div><el-radio-group v-model="viewMode" class="view-switch" size="small" aria-label="资产视图"><el-radio-button value="table"><el-icon><List /></el-icon>表格</el-radio-button><el-radio-button value="card"><el-icon><Grid /></el-icon>卡片</el-radio-button><el-radio-button value="type"><el-icon><Box /></el-icon>类型看板</el-radio-button></el-radio-group></section>

        <ProjectStatePanel v-if="assetsError" :title="assetsError.title" :message="assetsError.message" :retryable="assetsError.retryable" @retry="loadProjectContext" />
        <section v-else-if="!assetsLoading && !assets.length" class="asset-empty"><el-icon><Box /></el-icon><h3>当前筛选没有资产</h3><p>调整筛选条件，或在存储就绪的活动项目中新建/导入资产。</p></section>

        <div v-else-if="viewMode === 'table'" class="asset-table-wrap" :class="{ 'is-refreshing': assetsLoading }"><el-table class="asset-data-table" :data="assets" row-key="assetId" max-height="620"><el-table-column width="52" fixed="left" align="center"><template #header><el-checkbox :model-value="allSelectableSelected" :indeterminate="selectedAssets.length > 0 && !allSelectableSelected" :disabled="!selectableAssets.length" aria-label="选择当前页全部可操作资产" @change="toggleAllSelectable" /></template><template #default="scope"><el-checkbox v-if="scope?.row" :model-value="selectedAssetIds.has(Number(scope.row.assetId))" :disabled="!canSelectAsset(scope.row)" :aria-label="`选择资产 ${scope.row.assetName}`" @change="toggleAssetSelection(scope.row)" /></template></el-table-column><el-table-column label="缩略图" width="112"><template #default="scope"><ProtectedAssetThumbnail v-if="scope?.row" class="asset-thumb asset-thumb--small" :thumbnail="resolveAssetThumbnail(scope.row)" :alt="`${scope.row.assetName} 缩略图`" /></template></el-table-column><el-table-column label="类型 / 名称" width="170"><template #default="scope"><div v-if="scope?.row" class="asset-identity"><span class="type-chip" :data-tone="assetTypeMeta(scope.row.assetType).tone">{{ assetTypeMeta(scope.row.assetType).label }}</span><strong>{{ scope.row.assetName }}</strong><small>排序 {{ scope.row.sortOrder }}</small></div></template></el-table-column><el-table-column label="说明" min-width="220"><template #default="scope"><div v-if="scope?.row" class="asset-description">{{ scope.row.description || '—' }}</div></template></el-table-column><el-table-column label="制作分项" width="90" align="center" prop="itemCount" /><el-table-column label="制作人" width="130"><template #default="scope">{{ scope?.row ? assetAssigneeSummary(scope.row.assigneeUserIds, members) : '—' }}</template></el-table-column><el-table-column label="镜头使用" width="90" align="center" prop="usageShotCount" /><el-table-column label="状态 / 目录" width="120"><template #default="scope"><div v-if="scope?.row" class="asset-status"><span class="status-chip" :data-tone="assetStatusMeta(scope.row.assetStatus).tone">{{ assetStatusMeta(scope.row.assetStatus).label }}</span><small :data-tone="assetDirectoryStatusMeta(scope.row.directoryStatus).tone">{{ assetDirectoryStatusMeta(scope.row.directoryStatus).label }}</small></div></template></el-table-column><el-table-column label="操作" fixed="right" width="250"><template #default="scope"><div v-if="scope?.row" class="asset-row-actions"><el-button text type="primary" @click="openAsset(scope.row)">详情</el-button><el-button v-if="canEditAsset(scope.row)" text type="warning" :icon="Edit" :loading="editingAssetId === Number(scope.row.assetId)" @click="openEditDialog(scope.row)">编辑</el-button><el-button v-if="canDeleteAsset(scope.row)" text type="danger" :icon="Delete" :loading="deleting" @click="deleteAsset(scope.row)">删除</el-button></div></template></el-table-column></el-table></div>

        <div v-else-if="viewMode === 'card'" class="asset-grid" :class="{ 'is-refreshing': assetsLoading }"><el-card v-for="asset in assets" :key="asset.assetId" class="asset-card" shadow="hover" tabindex="0" @click="openAsset(asset)" @keydown.enter="openAsset(asset)"><ProtectedAssetThumbnail class="asset-thumb" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /><header><span class="type-chip" :data-tone="assetTypeMeta(asset.assetType).tone">{{ assetTypeMeta(asset.assetType).label }}</span><span class="status-chip" :data-tone="assetStatusMeta(asset.assetStatus).tone">{{ assetStatusMeta(asset.assetStatus).label }}</span></header><h3>{{ asset.assetName }}</h3><p>{{ asset.description || '暂无资产说明' }}</p><footer><span>{{ asset.itemCount }} 个制作分项</span><span>{{ asset.usageShotCount }} 个使用镜头</span></footer></el-card></div>

        <div v-else class="type-board" :class="{ 'is-refreshing': assetsLoading }"><el-card v-for="group in groupedAssets" :key="group.type" class="type-board__column" shadow="never"><header><div><span class="type-chip" :data-tone="assetTypeMeta(group.type).tone">{{ assetTypeMeta(group.type).label }}</span><strong>{{ group.assets.length }}</strong></div><small>当前分页结果</small></header><div v-if="group.assets.length" class="type-board__items"><el-button v-for="asset in group.assets" :key="asset.assetId" text class="type-board__asset" @click="openAsset(asset)"><ProtectedAssetThumbnail class="asset-thumb asset-thumb--board" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /><span><strong>{{ asset.assetName }}</strong><small>{{ asset.itemCount }} 分项 · {{ assetStatusMeta(asset.assetStatus).label }}</small></span></el-button></div><el-empty v-else :image-size="48" :description="`本页暂无${assetTypeMeta(group.type).label}资产`" /></el-card></div>

        <el-pagination v-if="total" class="asset-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="assetsLoading" aria-label="资产分页" @current-change="changePage" />
      </template>
    </template>

    <AssetFormDialog v-if="showCreate && createContext" :project-id="createContext.projectId" :operation-generation="createContext.operationGeneration" :members="members" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <AssetFormDialog v-if="showEdit && editContext && editingAsset" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :asset="editingAsset" :members="members" @close="closeEditDialog" @saved="handleEdited" @refresh="loadProjectContext" />
    <AssetImportDialog v-if="showImport && importContext" :project-id="importContext.projectId" :operation-generation="importContext.operationGeneration" :project-name="project?.projectName" :members="members" @close="closeImportDialog" @imported="handleImported" />
    <AssetRequirementDialog v-if="showRequirements && currentProjectId" :project-id="currentProjectId" :can-resolve="canResolveRequirements" :can-ignore="canIgnoreRequirements" :can-rematch="canRematchRequirements" @close="closeRequirementDialog" @updated="loadProjectContext" />

    <el-dialog v-model="showBatchAssign" :title="`${batchAssignLabel}资产制作人`" width="480px" :close-on-click-modal="!assigning" :close-on-press-escape="!assigning" :show-close="!assigning" @closed="batchAssigneeUserId = ''">
      <div class="asset-batch-assign-dialog"><p>将所选 {{ selectedAssets.length }} 个资产的全部活动制作分项分配给同一位制作人；已有任务会执行改派。</p><label><span>制作人</span><el-select v-model="batchAssigneeUserId" class="sg-select" placeholder="请选择制作人" :disabled="assigning"><el-option v-for="member in creatorMembers" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></label></div>
      <template #footer><el-button :disabled="assigning" @click="closeBatchAssignDialog">取消</el-button><el-button type="primary" :loading="assigning" :disabled="!batchAssigneeUserId" @click="confirmBatchAssign">确认{{ batchAssignLabel }}</el-button></template>
    </el-dialog>
    <el-drawer v-model="showDetail" class="asset-detail-drawer" :title="detailDrawerTitle" direction="rtl" size="72%" resizable append-to-body destroy-on-close @closed="clearDetailDrawer">
      <AssetDetailView v-if="detailAssetId && currentProjectId" embedded :target-project-id="currentProjectId" :target-asset-id="detailAssetId" @changed="handleDetailChanged" @deleted="handleDetailDeleted" />
    </el-drawer>
  </section>
</template>

<style scoped>
.asset-page{display:grid;gap:18px}.asset-heading{display:flex;gap:20px;align-items:flex-start;justify-content:space-between}.asset-heading__actions{display:flex;gap:9px}.project-context{display:flex;gap:14px;align-items:end;padding:15px 17px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);flex-wrap:wrap}.project-context label{display:grid;min-width:240px;gap:6px}.project-context label span{color:var(--sg-text-muted);font-size:10px}.project-context select,.asset-filters select,.asset-search{padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.project-context__meta{display:flex;gap:8px;align-items:center;flex:1;justify-content:flex-end;flex-wrap:wrap}.project-context__meta span{padding:6px 8px;color:var(--sg-text-muted);font-size:10px;background:rgba(255,255,255,.035);border-radius:7px}.project-context__meta span[data-ready=true]{color:var(--sg-success)}.asset-filters{display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,minmax(130px,180px)) auto auto;gap:9px}.asset-search{display:flex;gap:8px;align-items:center}.asset-search input{width:100%;color:var(--sg-text);background:transparent;border:0;outline:0}.asset-toolbar{display:flex;align-items:center;justify-content:space-between}.asset-toolbar>div:first-child{display:flex;gap:6px;align-items:baseline}.asset-toolbar strong{font-size:23px}.asset-toolbar span{color:var(--sg-text-muted);font-size:11px}.view-switch{display:flex;padding:3px;background:rgba(255,255,255,.035);border-radius:9px}.view-switch button{display:flex;gap:6px;align-items:center;padding:7px 9px;color:var(--sg-text-muted);font-size:11px;cursor:pointer;background:transparent;border:0;border-radius:7px}.view-switch button[data-active=true]{color:var(--sg-text);background:rgba(255,255,255,.08)}.asset-table-wrap{overflow:auto;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}table{width:100%;min-width:1040px;border-collapse:collapse}th,td{padding:12px;border-bottom:1px solid var(--sg-border);font-size:11px;text-align:left;vertical-align:middle}th{color:var(--sg-text-muted)}td{color:var(--sg-text-secondary)}td strong,td small{display:block;margin-top:4px}.asset-description{max-width:290px;line-height:1.55}.asset-thumb--small{width:82px;height:54px;border-radius:7px}.type-chip,.status-chip{display:inline-flex;width:max-content;padding:5px 7px;font-size:10px;border-radius:999px}.type-chip[data-tone=character]{color:var(--sg-accent);background:var(--sg-accent-soft)}.type-chip[data-tone=environment]{color:#80bfff;background:rgba(128,191,255,.08)}.type-chip[data-tone=prop]{color:#8dd8a9;background:rgba(98,212,155,.08)}.status-chip{color:var(--sg-text-muted);background:rgba(255,255,255,.05)}.status-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}td small[data-tone=success]{color:var(--sg-success)}td small[data-tone=warning]{color:var(--sg-accent)}td small[data-tone=danger]{color:var(--sg-danger)}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:13px}.asset-card{overflow:hidden;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:.18s ease}.asset-card:hover,.asset-card:focus{border-color:var(--sg-border-strong);transform:translateY(-2px);outline:0}.asset-card>.asset-thumb{height:150px}.asset-card header,.asset-card footer{display:flex;align-items:center;justify-content:space-between}.asset-card header{padding:12px 14px 0}.asset-card h3,.asset-card p{margin:0;padding:0 14px}.asset-card h3{margin-top:10px}.asset-card p{min-height:38px;margin-top:6px;color:var(--sg-text-muted);font-size:11px;line-height:1.55}.asset-card footer{margin-top:12px;padding:10px 14px;color:var(--sg-text-muted);font-size:10px;border-top:1px solid var(--sg-border)}.type-board{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.type-board>section{min-width:0;padding:13px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.type-board section>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}.type-board header div{display:flex;gap:8px;align-items:center}.type-board header small,.type-board section>p{color:var(--sg-text-muted);font-size:10px}.type-board section>div{display:grid;gap:8px}.type-board button{display:grid;grid-template-columns:68px 1fr;gap:9px;align-items:center;padding:8px;color:var(--sg-text);text-align:left;cursor:pointer;background:rgba(255,255,255,.025);border:1px solid transparent;border-radius:9px}.type-board button:hover{border-color:var(--sg-border-strong)}.asset-thumb--board{width:68px;height:48px;border-radius:6px}.type-board button span strong,.type-board button span small{display:block}.type-board button span small{margin-top:4px;color:var(--sg-text-muted);font-size:9px}.asset-empty{display:grid;min-height:260px;align-content:center;color:var(--sg-text-muted);text-align:center;background:var(--sg-surface);border:1px dashed var(--sg-border);border-radius:var(--sg-radius-md);place-items:center}.asset-empty>.el-icon{font-size:34px}.asset-empty h3,.asset-empty p{margin:8px 0 0}.asset-empty p{font-size:11px}.asset-pagination{display:flex;gap:12px;align-items:center;justify-content:center}.asset-pagination button{padding:8px 11px;color:var(--sg-text-secondary);cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:7px}.asset-pagination button:disabled{opacity:.35;cursor:not-allowed}.asset-pagination span{color:var(--sg-text-muted);font-size:11px}.is-refreshing{opacity:.55;pointer-events:none}@media(max-width:1100px){.asset-filters{grid-template-columns:1fr 1fr 1fr}.type-board{grid-template-columns:1fr}}@media(max-width:700px){.asset-heading{flex-direction:column}.asset-filters{grid-template-columns:1fr}.project-context label{min-width:100%}.project-context__meta{justify-content:flex-start}.asset-grid{grid-template-columns:1fr}}
.asset-toolbar{gap:12px}.asset-toolbar__summary{display:flex!important;gap:8px!important;align-items:center!important;flex-wrap:wrap}.asset-table-wrap table{min-width:1180px}.asset-select-cell{width:34px;text-align:center}.asset-row-actions{display:flex;align-items:center;white-space:nowrap}.asset-batch-assign-dialog{display:grid;gap:16px}.asset-batch-assign-dialog p{margin:0;color:var(--sg-text-secondary);font-size:12px;line-height:1.65}.asset-batch-assign-dialog label{display:grid;gap:7px}.asset-batch-assign-dialog label span{color:var(--sg-text-muted);font-size:11px}
:global(.asset-detail-drawer){min-width:720px;max-width:1100px;background:#10141a}:global(.asset-detail-drawer .el-drawer__header){margin-bottom:0;padding:18px 22px;color:var(--sg-text);border-bottom:1px solid var(--sg-border)}:global(.asset-detail-drawer .el-drawer__body){padding:20px 22px}@media(max-width:760px){:global(.asset-detail-drawer){min-width:0;width:94%!important}}
.project-context:deep(.el-form-item){min-width:240px;margin:0}.project-context:deep(.el-form-item__label){height:auto;padding-bottom:6px;color:var(--sg-text-muted);font-size:10px;line-height:1}.project-context__meta:deep(.el-tag){background:rgba(255,255,255,.035);border-color:transparent}.asset-filters .asset-search{padding:0;background:transparent;border:0}.view-switch{padding:0;background:transparent}.view-switch:deep(.el-radio-button__inner){display:flex;gap:6px;align-items:center;color:var(--sg-text-muted);background:var(--sg-surface);border-color:var(--sg-border);box-shadow:none}.view-switch:deep(.el-radio-button__original-radio:checked+.el-radio-button__inner){color:var(--sg-accent);background:var(--sg-accent-soft);border-color:rgba(255,182,87,.32);box-shadow:-1px 0 0 0 rgba(255,182,87,.32)}.asset-table-wrap{overflow:hidden}.asset-data-table{--el-table-bg-color:var(--sg-surface);--el-table-tr-bg-color:var(--sg-surface);--el-table-header-bg-color:#15191f;--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);--el-table-border-color:var(--sg-border);--el-table-row-hover-bg-color:#171b22;width:100%}.asset-data-table:deep(.el-table__cell){padding:11px 0;font-size:11px}.asset-data-table:deep(.el-table-fixed-column--left),.asset-data-table:deep(.el-table-fixed-column--right){background:var(--sg-surface)}.asset-data-table:deep(th.el-table-fixed-column--left),.asset-data-table:deep(th.el-table-fixed-column--right){background:#15191f}.asset-data-table:deep(.el-table__body tr:hover>td.el-table-fixed-column--left),.asset-data-table:deep(.el-table__body tr:hover>td.el-table-fixed-column--right){background:#171b22}.asset-identity strong,.asset-identity small,.asset-status small{display:block;margin-top:5px}.asset-card:deep(.el-card__body){padding:0}.asset-card>.asset-thumb,.asset-card:deep(.el-card__body>.asset-thumb){height:150px}.type-board__column{min-width:0;background:var(--sg-surface);border-color:var(--sg-border)}.type-board__column:deep(.el-card__body){padding:13px}.type-board__column header{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}.type-board__items{display:grid;gap:8px}.type-board .type-board__asset{display:grid;width:100%;height:auto;grid-template-columns:68px minmax(0,1fr);gap:9px;align-items:center;justify-content:stretch;margin:0;padding:8px;color:var(--sg-text);text-align:left;background:rgba(255,255,255,.025);border:1px solid transparent}.type-board .type-board__asset:hover{background:rgba(255,255,255,.04);border-color:var(--sg-border-strong)}.type-board__asset>span{display:block;min-width:0}.type-board__asset>span strong,.type-board__asset>span small{display:block;overflow:hidden;text-overflow:ellipsis}.asset-pagination{margin-top:2px}.asset-pagination:deep(.el-pager li),.asset-pagination:deep(button){background:var(--sg-surface)!important}.asset-pagination:deep(.is-active){color:#17130d!important;background:var(--sg-accent)!important}
.asset-filters{grid-template-columns:minmax(220px,1fr) repeat(3,minmax(130px,180px)) auto}
.asset-filters:deep(.el-form-item){min-width:0;margin-bottom:0}
.asset-filter-item:deep(.el-form-item__content),.asset-filter-item:deep(.el-select),.asset-filter-item:deep(.el-input){width:100%;min-width:0}
.asset-filter-actions:deep(.el-form-item__content){flex-wrap:nowrap;justify-content:flex-end}
@media(max-width:1100px){.asset-filters{grid-template-columns:1fr 1fr 1fr}.asset-filter-actions:deep(.el-form-item__content){justify-content:flex-start}}
@media(max-width:700px){.asset-filters{grid-template-columns:1fr}}
</style>
