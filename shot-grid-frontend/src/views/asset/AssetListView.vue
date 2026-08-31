<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Box, Calendar, Clock, Collection, Delete, Edit, Grid, List, Plus, Refresh, RefreshLeft, Search, Switch, Upload, User, VideoPlay, View } from '@element-plus/icons-vue'

import { archiveAsset, batchAssignAssetItemTasks, batchDeleteAssets, getAssetDetail, getAssetPage, listAssetAssignees } from '@/api/shot-grid/assets'
import { assertPositiveId, getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useTaskStatePolling } from '@/composables/useTaskStatePolling'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import TableActionButton from '@/components/TableActionButton.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetTreeTable from '@/views/asset/components/AssetTreeTable.vue'
import AssetItemOperationHost from '@/views/asset/components/AssetItemOperationHost.vue'
import { canAssetItemAction } from '@/views/asset/assetItemActions'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'
import AssetRequirementDialog from '@/views/asset/components/AssetRequirementDialog.vue'
import AssetDetailView from '@/views/asset/AssetDetailView.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import { assetErrorState, assetItemStatusEntries, assetStatusMeta, assetStatusTagClass, assetTypeMeta, memberLabel, memberUserName, resolveAssetThumbnail } from '@/views/asset/assetPresentation'
import { projectRoleMeta, storageMeta } from '@/views/project/projectPresentation'

const ScheduleBoard = defineAsyncComponent(() => import('@/views/schedule/ScheduleBoard.vue'))

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
const assetTable = ref(null)
const itemOperations = ref(null)
const itemActionBusy = ref(false)
const backgroundAssetRefresh = ref(false)
const projectsError = ref(null)
const assetsError = ref(null)
const projectContextForm = ref(null)
const projectContext = reactive({ selectedProjectId: '', scope: '' })
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
const batchAssignFormRef = ref(null)
const batchAssignForm = reactive({ assigneeUserId: '' })
const showDetail = ref(false)
const detailAssetId = ref(null)
const detailAssetItemId = ref(null)
const createContext = ref(null)
const importContext = ref(null)
const assetFilterForm = ref(null)
const appliedAssetQuery = ref('')
const query = reactive({
  keyword: '',
  assetType: '',
  assetStatus: '',
  assigneeUserId: '',
  pageNum: 1,
  pageSize: 100,
  orderByColumn: 'sortOrder',
  isAsc: 'ascending'
})
const projectContextRules = {
  selectedProjectId: [{ required: true, message: '请选择当前项目', trigger: 'change' }],
  scope: [{
    validator: (_rule, value, callback) => {
      if (!['', 'all'].includes(String(value || ''))) {
        callback(new Error('项目范围无效'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}
const assetFilterRules = {
  keyword: [{ max: 200, message: '搜索关键字不能超过 200 个字符', trigger: 'blur' }]
}
const batchAssignRules = {
  assigneeUserId: [{ required: true, message: '请选择要分配的新制作人', trigger: 'change' }]
}
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
const canSchedule = computed(() => Boolean(
  project.value
  && isDirector.value
  && hasPermission('shotgrid:task:schedule')
  && !['completed', 'archived'].includes(project.value.projectStatus)
))
const canResolveRequirements = computed(() => hasPermission('shotgrid:assetRequirement:resolve'))
const canIgnoreRequirements = computed(() => hasPermission('shotgrid:assetRequirement:ignore'))
const canRematchRequirements = computed(() => hasPermission('shotgrid:assetRequirement:rematch'))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const currentProjectId = computed(() => {
  try {
    return assertPositiveId(projectContext.selectedProjectId, '项目')
  } catch {
    return null
  }
})
const scheduleInitialFilters = computed(() => ({
  keyword: query.keyword.trim(),
  assigneeUserIds: query.assigneeUserId ? [Number(query.assigneeUserId)] : [],
  assetTypes: query.assetType ? [query.assetType] : [],
  taskStatuses: query.assetStatus && query.assetStatus !== 'unassigned'
    ? [query.assetStatus === 'reviewing' ? 'pending_review' : query.assetStatus]
    : []
}))
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
const canDeleteSelection = computed(() => Boolean(selectedAssets.value.length) && selectedAssets.value.every(asset => canDeleteAsset(asset)))

function itemStatusEntries(asset) {
  return assetItemStatusEntries(asset?.itemStatusCounts).filter(entry => entry.count > 0)
}

function canOpenItemStart(asset) {
  return hasPermission('shotgrid:task:start') && (asset?.allowedActions || []).includes('task.start')
}

function handleScheduleQueryChange({ mode }) {
  if (['swimlane', 'gantt'].includes(mode)) viewMode.value = mode
}

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

function assetQueryParams() {
  return {
    keyword: query.keyword.trim() || undefined,
    assetType: query.assetType || undefined,
    assetStatus: query.assetStatus || undefined,
    assigneeUserId: query.assigneeUserId || undefined,
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    orderByColumn: query.orderByColumn,
    isAsc: query.isAsc
  }
}

function currentAssetQueryKey() {
  return JSON.stringify(assetQueryParams())
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
      { scope: projectContext.scope || undefined, orderByColumn: 'projectName', isAsc: 'ascending' },
      controller.signal
    )
    if (projectController !== controller || controller.signal.aborted) return
    projects.value = rows
    const routeId = preferredId || route.query.projectId
    const candidate = rows.find(item => String(item.projectId) === String(routeId)) || rows[0]
    projectContext.selectedProjectId = candidate ? String(candidate.projectId) : ''
  } catch (error) {
    if (projectController === controller && !controller.signal.aborted && error?.code !== 'ERR_CANCELED') {
      projects.value = []
      projectContext.selectedProjectId = ''
      projectsError.value = assetErrorState(error, '项目范围加载失败')
    }
  } finally {
    if (projectController === controller) projectsLoading.value = false
  }
}

async function loadProjectContext(preserveList = false) {
  const projectId = currentProjectId.value
  assetController?.abort()
  backgroundAssetRefresh.value = false
  if (preserveList !== true) {
    project.value = null
    members.value = []
    assets.value = []
    selectedAssetIds.value = new Set()
    total.value = 0
  }
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
    if (error?.code !== 'ERR_CANCELED') assetsError.value = assetErrorState(error, '当前项目资产信息加载失败')
  } finally {
    if (assetController === controller) assetsLoading.value = false
  }
}

async function loadAssets(existingController = null, background = false) {
  const projectId = currentProjectId.value
  if (!projectId) return
  if (!existingController) assetController?.abort()
  const controller = existingController || new AbortController()
  assetController = controller
  const params = background ? JSON.parse(appliedAssetQuery.value || '{}') : assetQueryParams()
  if (!background) {
    backgroundAssetRefresh.value = false
    assetsLoading.value = true
    assetsError.value = null
    appliedAssetQuery.value = JSON.stringify(params)
  }
  try {
    // 背景轮询等待当前分项查询完成，避免慢请求被下一轮刷新不断取消。
    if (background) await assetTable.value?.waitForLoads()
    if (disposed || assetController !== controller || controller.signal.aborted || currentProjectId.value !== projectId) return
    const response = await getAssetPage(projectId, params, { signal: controller.signal })
    if (assetController !== controller || controller.signal.aborted || currentProjectId.value !== projectId) return
    const loadedAssets = Array.isArray(response.rows) ? response.rows : []
    backgroundAssetRefresh.value = background
    assets.value = loadedAssets
    selectedAssetIds.value = background
      ? new Set(loadedAssets.filter(asset => selectedAssetIds.value.has(Number(asset.assetId)) && canSelectAsset(asset)).map(asset => Number(asset.assetId)))
      : new Set()
    total.value = Number(response.total || 0)
    await nextTick()
    // 父级状态结束轮询时仍更新本轮已加载分支；新的人工请求或项目切换会使本轮失效。
    if (background && !disposed && assetController === controller && currentProjectId.value === projectId) {
      await assetTable.value?.refreshLoadedChildren()
    }
  } catch (error) {
    if (background) throw error
    if (error?.code !== 'ERR_CANCELED') {
      assets.value = []
      selectedAssetIds.value = new Set()
      total.value = 0
      assetsError.value = assetErrorState(error, '资产列表加载失败')
    }
  } finally {
    if (!background && assetController === controller) assetsLoading.value = false
  }
}

async function submitFilters() {
  const isValid = await assetFilterForm.value?.validate().catch(() => false)
  if (!isValid) return
  query.pageNum = 1
  loadAssets()
}

async function resetFilters() {
  assetFilterForm.value?.resetFields()
  assetFilterForm.value?.clearValidate()
  query.pageNum = 1
  await loadAssets()
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
  detailAssetItemId.value = Number(asset.assetItemId) || null
  showDetail.value = true
}

function openAssetItemStart(asset) {
  if (!canOpenItemStart(asset)) return
  openAsset(asset)
}

function closeDetailDrawer() {
  showDetail.value = false
}

function clearDetailDrawer() {
  detailAssetId.value = null
  detailAssetItemId.value = null
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

const { pollingError } = useTaskStatePolling({
  getDelay: () => {
    if (!currentProjectId.value || assetsLoading.value || assetsError.value || showDetail.value || showCreate.value ||
      showImport.value || showRequirements.value || showEdit.value || editingAssetId.value || showBatchAssign.value ||
      assigning.value || deleting.value || itemActionBusy.value || appliedAssetQuery.value !== currentAssetQueryKey()) return null
    if (assets.value.some(asset => Number(asset?.itemStatusCounts?.preparing) > 0)) return 1500
    return assets.value.some(asset => Number(asset?.itemStatusCounts?.not_started) > 0) ? 5000 : null
  },
  refresh: controller => loadAssets(controller, true)
})

function updateAssetSelection(rows) {
  selectedAssetIds.value = new Set(rows.filter(canSelectAsset).map(asset => Number(asset.assetId)))
}

function itemCan(asset, item, action) {
  return canAssetItemAction(asset, item, action, hasPermission)
}

async function handleItemOperationChanged(operation) {
  if (!disposed && currentProjectId.value === Number(operation?.projectId)) await loadAssets()
}

function handleAssetCommand(command, asset) {
  if (deleting.value || assigning.value || editingAssetId.value !== null || Number(asset.projectId) !== currentProjectId.value) return
  if (command === 'edit' && canEditAsset(asset)) openEditDialog(asset)
  else if (command === 'delete' && canDeleteAsset(asset)) deleteAsset(asset)
}

function openBatchAssignDialog() {
  if (!selectedAssets.value.length || assigning.value || deleting.value) return
  batchAssignForm.assigneeUserId = ''
  batchAssignFormRef.value?.clearValidate()
  showBatchAssign.value = true
}

function closeBatchAssignDialog() {
  if (assigning.value) return
  showBatchAssign.value = false
}

function resetBatchAssignForm() {
  batchAssignFormRef.value?.resetFields()
  batchAssignFormRef.value?.clearValidate()
  batchAssignForm.assigneeUserId = ''
}

async function confirmBatchAssign() {
  if (assigning.value || !selectedAssets.value.length) return
  const isValid = await batchAssignFormRef.value?.validate().catch(() => false)
  if (!isValid) return
  const assigneeUserId = Number(batchAssignForm.assigneeUserId)
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
      ElMessage.warning(`${blockedItem.productionItem || '待补制作分项'} 当前不能分配或改派，请刷新状态；仅未开工任务可改派`)
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
    ElMessage.success(`已将 ${targetAssets.length} 个资产的 ${items.length} 个制作分项分配给 ${memberUserName(member)}`)
    if (currentProjectId.value === targetProjectId) {
      showBatchAssign.value = false
      batchAssignForm.assigneeUserId = ''
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
  ElMessage.success('操作已完成；请切回对应项目查看最新结果。')
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

watch(() => projectContext.selectedProjectId, (next, previous) => {
  if (next === previous) return
  closeCreateDialog()
  closeImportDialog()
  closeRequirementDialog()
  closeEditDialog()
  closeDetailDrawer()
  clearDetailDrawer()
  showBatchAssign.value = false
  batchAssignForm.assigneeUserId = ''
  selectedAssetIds.value = new Set()
  query.pageNum = 1
  query.assigneeUserId = ''
  loadProjectContext()
})
watch(() => projectContext.scope, () => loadProjects())
watch(() => route.query.projectId, next => {
  if (next && String(next) !== projectContext.selectedProjectId && projects.value.some(item => String(item.projectId) === String(next))) {
    projectContext.selectedProjectId = String(next)
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
  <AssetItemOperationHost v-if="currentProjectId" ref="itemOperations" :project-id="currentProjectId" :context-key="`${currentProjectId}:${appliedAssetQuery}`" :members="members" @busy-change="itemActionBusy = $event" @changed="handleItemOperationChanged" />
  <section class="sg-page asset-page">
    <header class="sg-page-heading asset-heading">
      <div><p class="sg-eyebrow">ASSETS</p>
        <h2 class="sg-page-title">资产库管理</h2>
        <p class="sg-page-description">统一管理角色、场景和道具制作分项，也可切换人员泳道或任务甘特监管资产制作排期。</p>
      </div>
      <div class="asset-heading__actions">
        <el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button>
        <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建资产</el-button>
      </div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form ref="projectContextForm" :model="projectContext" :rules="projectContextRules" class="project-context" size="large" inline label-position="top" aria-label="当前项目筛选">
        <el-form-item label="当前项目" prop="selectedProjectId"><el-select v-model="projectContext.selectedProjectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :disabled="projectsLoading"><el-option :label="projectsLoading ? '正在加载项目…' : '请选择项目'" value="" /><el-option v-for="item in projects" :key="item.projectId" :label="`${item.projectCode} · ${item.projectName}`" :value="String(item.projectId)" /></el-select></el-form-item>
        <el-form-item v-if="canViewAll" label="项目范围" prop="scope"><el-select v-model="projectContext.scope" class="sg-select" placeholder="我的项目"><el-option label="我的项目" value="" /><el-option label="全部项目" value="all" /></el-select></el-form-item>
        <div v-if="project" class="project-context__meta"><el-tag size="small" effect="plain" type="primary">{{ project.projectTypeName }}</el-tag><el-tag size="small" effect="plain" type="info">{{ project.aspectRatio }}</el-tag><el-tag size="small" effect="plain" round :type="projectRoleMeta(project.myProjectRole).type">我的角色：{{ projectRoleMeta(project.myProjectRole).label }}</el-tag><el-tag size="small" effect="plain" round :type="tagTypeFromTone(storageMeta(project.storageStatus).tone)">存储：{{ storageMeta(project.storageStatus).label }}</el-tag></div>
      </el-form>

      <el-card v-if="projectsLoading && !projectContext.selectedProjectId" class="asset-context-loading" shadow="never"><el-skeleton :rows="3" animated /></el-card>
      <el-empty v-else-if="!projectContext.selectedProjectId" class="asset-empty" description="当前范围暂无可选项目"><template #image><el-icon><Collection /></el-icon></template><p>请先创建项目或加入项目成员范围。</p></el-empty>

      <template v-else-if="projectContext.selectedProjectId">
        <el-alert v-if="pollingError" :title="pollingError" type="warning" show-icon :closable="false" />
        <el-form ref="assetFilterForm" :model="query" :rules="assetFilterRules" class="asset-filters" size="large" aria-label="资产筛选">
          <el-form-item class="asset-filter-item asset-filter-item--keyword" prop="keyword">
            <el-input v-model="query.keyword" class="asset-search sg-input" :prefix-icon="Search" maxlength="200" clearable placeholder="资产名称或描述" aria-label="按资产名称或描述搜索" />
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assetType">
            <el-select v-model="query.assetType" class="sg-select" placeholder="全部类型" aria-label="按资产类型筛选" @change="submitFilters"><el-option label="全部类型" value="" /><el-option label="角色" value="Character" /><el-option label="场景" value="Environment" /><el-option label="道具" value="Prop" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assetStatus">
            <el-select v-model="query.assetStatus" class="sg-select" placeholder="全部状态" aria-label="按资产状态筛选" @change="submitFilters"><el-option label="全部状态" value="" /><el-option v-for="status in ['unassigned','not_started','preparing','in_progress','reviewing','revision','completed']" :key="status" :label="assetStatusMeta(status).label" :value="status" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-item" prop="assigneeUserId">
            <el-select v-model="query.assigneeUserId" class="sg-select" placeholder="全部制作人" aria-label="按制作人筛选" @change="submitFilters"><el-option label="全部制作人" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select>
          </el-form-item>
          <el-form-item class="asset-filter-actions">
            <el-button type="primary" :icon="Search" :loading="assetsLoading" @click="submitFilters">查询</el-button>
            <el-button :icon="RefreshLeft" :disabled="assetsLoading" @click="resetFilters">重置</el-button>
            <el-button :icon="Refresh" :disabled="assetsLoading" @click="loadProjectContext(true)">刷新</el-button>
          </el-form-item>
        </el-form>

        <section class="asset-toolbar"><div class="asset-toolbar__summary"><strong>{{ total }}</strong><span>个资产</span><template v-if="selectedAssets.length"><el-button v-if="canAssign" text type="primary" :loading="assigning" @click="openBatchAssignDialog">{{ batchAssignLabel }}（{{ selectedAssets.length }}）</el-button><el-button v-if="canDelete" text type="danger" :icon="Delete" :loading="deleting" :disabled="!canDeleteSelection" @click="deleteSelectedAssets">批量删除（{{ selectedAssets.length }}）</el-button></template></div><el-radio-group v-model="viewMode" class="view-switch" size="small" aria-label="资产视图"><el-radio-button value="table"><el-icon><List /></el-icon>表格</el-radio-button><el-radio-button value="card"><el-icon><Grid /></el-icon>卡片</el-radio-button><el-radio-button value="type"><el-icon><Box /></el-icon>类型看板</el-radio-button><el-radio-button value="swimlane"><el-icon><Clock /></el-icon>人员泳道</el-radio-button><el-radio-button value="gantt"><el-icon><Calendar /></el-icon>任务甘特</el-radio-button></el-radio-group></section>

        <Suspense v-if="['swimlane', 'gantt'].includes(viewMode) && currentProjectId">
          <ScheduleBoard :project-id="currentProjectId" target-kind="asset_item" :initial-mode="viewMode" :initial-filters="scheduleInitialFilters" :editable-allowed="canSchedule" @query-change="handleScheduleQueryChange" />
          <template #fallback><el-card class="asset-context-loading" shadow="never"><el-skeleton :rows="8" animated /></el-card></template>
        </Suspense>
        <ProjectStatePanel v-else-if="assetsError" :title="assetsError.title" :message="assetsError.message" :retryable="assetsError.retryable" @retry="loadProjectContext" />
        <el-empty v-else-if="!assetsLoading && !assets.length" class="asset-empty" description="当前筛选没有资产"><template #image><el-icon><Box /></el-icon></template><p>调整筛选条件，或在存储就绪的活动项目中新建/导入资产。</p></el-empty>

        <AssetTreeTable v-else-if="viewMode === 'table'" ref="assetTable" :assets="assets" :project-id="currentProjectId"
                        :context-key="`${currentProjectId}:${appliedAssetQuery}`" :members="members"
                        :selected-asset-ids="selectedAssetIds" :selectable="canSelectAsset"
                        :can-query="hasPermission('shotgrid:asset:query')" :loading="assetsLoading" :background-refresh="backgroundAssetRefresh" :selection-disabled="assigning || deleting || itemActionBusy"
                        @selection-change="updateAssetSelection" @open-item="openAsset">
          <template #asset-actions="{ row }">
            <div class="asset-row-actions">
              <TableActionButton v-if="canOpenItemStart(row)" label="选择分项开工" type="primary" :plain="false" :icon="VideoPlay" @click="openAssetItemStart(row)" />
              <TableActionButton label="详情" :icon="View" @click="openAsset(row)" />
              <TableActionButton v-if="canEditAsset(row)" label="编辑资产" :icon="Edit" :loading="editingAssetId === Number(row.assetId)" :disabled="deleting || assigning || editingAssetId !== null" @click="handleAssetCommand('edit', row)" />
              <TableActionButton v-if="canDeleteAsset(row)" label="删除资产" type="danger" :icon="Delete" :disabled="deleting || assigning || editingAssetId !== null" @click="handleAssetCommand('delete', row)" />
            </div>
          </template>
          <template #item-actions="{ row, asset }">
            <div class="asset-row-actions">
              <TableActionButton v-if="itemCan(asset, row, 'task.start')" label="开始任务" type="primary" :plain="false" :icon="VideoPlay" :disabled="assetsLoading || itemActionBusy || assigning || deleting" @click="itemOperations.run('task.start', asset, row)" />
              <TableActionButton v-if="itemCan(asset, row, 'task.assign')" :label="row.task ? '改派任务' : '分配任务'" type="info" :icon="row.task ? Switch : User" :disabled="assetsLoading || itemActionBusy || assigning || deleting" @click="itemOperations.run('task.assign', asset, row)" />
              <TableActionButton v-if="itemCan(asset, row, 'assetItem.edit')" :label="String(row.productionItem || '').trim() ? '编辑分项' : '补齐制作分项'" :icon="Edit" :type="String(row.productionItem || '').trim() ? '' : 'warning'" :dashed="!String(row.productionItem || '').trim()" :disabled="assetsLoading || itemActionBusy || assigning || deleting" @click="itemOperations.run('assetItem.edit', asset, row)" />
              <TableActionButton v-if="itemCan(asset, row, 'assetItem.delete')" label="删除分项" type="danger" :icon="Delete" :disabled="assetsLoading || itemActionBusy || assigning || deleting" @click="itemOperations.run('assetItem.delete', asset, row)" />
              <TableActionButton label="分项详情" :icon="View" :disabled="itemActionBusy" @click="openAsset(row)" />
            </div>
          </template>
        </AssetTreeTable>

        <div v-else-if="viewMode === 'card'" class="asset-grid" v-loading="assetsLoading"><el-card v-for="asset in assets" :key="asset.assetId" class="asset-card" shadow="hover" tabindex="0" @click="openAsset(asset)" @keydown.enter="openAsset(asset)"><ProtectedAssetThumbnail class="asset-thumb" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /><header><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(asset.assetType).tone)">{{ assetTypeMeta(asset.assetType).label }}</el-tag><el-tag class="asset-status-tag" :class="assetStatusTagClass(asset.assetStatus)" size="small" effect="light" round :type="tagTypeFromTone(assetStatusMeta(asset.assetStatus).tone)">{{ assetStatusMeta(asset.assetStatus).label }}</el-tag></header><h3>{{ asset.assetName }}</h3><p>{{ asset.description || '暂无资产描述' }}</p><div v-if="itemStatusEntries(asset).length" class="asset-item-status-counts asset-item-status-counts--card"><el-tag v-for="entry in itemStatusEntries(asset)" :key="entry.status" size="small" effect="plain" round :type="tagTypeFromTone(assetStatusMeta(entry.status).tone)">{{ entry.label }} {{ entry.count }}</el-tag></div><footer><span>{{ asset.itemCount }} 个制作分项</span><span>{{ asset.usageShotCount }} 个使用镜头</span><el-button v-if="canOpenItemStart(asset)" size="small" type="primary" :icon="VideoPlay" @click.stop="openAssetItemStart(asset)">选择分项开工</el-button></footer></el-card></div>

        <div v-else class="type-board" v-loading="assetsLoading">
          <el-card v-for="group in groupedAssets" :key="group.type" class="type-board__column" shadow="never">
            <template #header>
              <div class="type-board__header">
                <div class="type-board__heading">
                  <el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(group.type).tone)">{{ assetTypeMeta(group.type).label }}</el-tag>
                  <strong>{{ group.assets.length }} 个资产</strong>
                </div>
                <small>当前分页结果</small>
              </div>
            </template>
            <div v-if="group.assets.length" class="type-board__items">
              <div v-for="asset in group.assets" :key="asset.assetId" class="type-board__asset-row">
                <el-button class="type-board__asset" :aria-label="`查看${asset.assetName}资产详情`" @click="openAsset(asset)">
                  <span class="type-board__content">
                    <ProtectedAssetThumbnail class="asset-thumb--board" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" />
                    <span class="type-board__summary">
                      <el-text tag="strong" class="type-board__name" :line-clamp="2">{{ asset.assetName }}</el-text>
                      <span class="type-board__count">{{ asset.itemCount }} 个制作分项</span>
                      <span class="type-board__statuses">
                        <template v-if="itemStatusEntries(asset).length">
                          <el-tag v-for="entry in itemStatusEntries(asset)" :key="entry.status" class="asset-status-tag" :class="assetStatusTagClass(entry.status)" size="small" effect="light" round :type="tagTypeFromTone(assetStatusMeta(entry.status).tone)">{{ entry.label }} {{ entry.count }}</el-tag>
                        </template>
                        <el-tag v-else class="asset-status-tag" :class="assetStatusTagClass(asset.assetStatus)" size="small" effect="light" round :type="tagTypeFromTone(assetStatusMeta(asset.assetStatus).tone)">{{ assetStatusMeta(asset.assetStatus).label }}</el-tag>
                      </span>
                    </span>
                  </span>
                </el-button>
                <el-button v-if="canOpenItemStart(asset)" class="type-board__start" size="small" type="primary" :icon="VideoPlay" @click="openAssetItemStart(asset)">选择分项开工</el-button>
              </div>
            </div>
            <el-empty v-else :image-size="48" :description="`本页暂无${assetTypeMeta(group.type).label}资产`" />
          </el-card>
        </div>

        <el-pagination v-if="total" class="asset-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="assetsLoading" aria-label="资产分页" @current-change="changePage" />
      </template>
    </template>

    <AssetFormDialog v-if="showCreate && createContext" :project-id="createContext.projectId" :operation-generation="createContext.operationGeneration" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <AssetFormDialog v-if="showEdit && editContext && editingAsset" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :asset="editingAsset" @close="closeEditDialog" @saved="handleEdited" @refresh="loadProjectContext" />
    <AssetImportDialog v-if="showImport && importContext" :project-id="importContext.projectId" :operation-generation="importContext.operationGeneration" :project-name="project?.projectName" @close="closeImportDialog" @imported="handleImported" />
    <AssetRequirementDialog v-if="showRequirements && currentProjectId" :project-id="currentProjectId" :can-resolve="canResolveRequirements" :can-ignore="canIgnoreRequirements" :can-rematch="canRematchRequirements" @close="closeRequirementDialog" @updated="loadProjectContext" />

    <el-dialog v-model="showBatchAssign" :title="`${batchAssignLabel}资产制作人`" width="480px" :close-on-click-modal="!assigning" :close-on-press-escape="!assigning" :show-close="!assigning" @closed="resetBatchAssignForm">
      <el-form ref="batchAssignFormRef" :model="batchAssignForm" :rules="batchAssignRules" class="asset-batch-assign-dialog" size="large" label-position="top" aria-label="资产批量分配表单"><p>将所选 {{ selectedAssets.length }} 个资产的全部活动制作分项分配给同一位制作人；已有任务会执行改派。</p><el-form-item label="制作人" prop="assigneeUserId"><el-select v-model="batchAssignForm.assigneeUserId" class="sg-select" placeholder="请选择制作人" :disabled="assigning"><el-option v-for="member in creatorMembers" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></el-form-item></el-form>
      <template #footer><el-button size="large" :disabled="assigning" @click="closeBatchAssignDialog">取消</el-button><el-button size="large" type="primary" :loading="assigning" @click="confirmBatchAssign">确认{{ batchAssignLabel }}</el-button></template>
    </el-dialog>
    <el-drawer v-model="showDetail" class="sg-detail-drawer asset-detail-drawer" modal-class="sg-detail-drawer-mask" header-class="sg-detail-drawer__header" body-class="sg-detail-drawer__body" :title="detailDrawerTitle" direction="rtl" size="72%" resizable append-to-body destroy-on-close @closed="clearDetailDrawer">
      <AssetDetailView v-if="detailAssetId && currentProjectId" embedded :target-project-id="currentProjectId" :target-asset-id="detailAssetId" :target-asset-item-id="detailAssetItemId" @changed="handleDetailChanged" @deleted="handleDetailDeleted" />
    </el-drawer>
  </section>
</template>

<style scoped>
.asset-page { display: grid; gap: 18px; }
.asset-heading { display: flex; gap: 20px; align-items: flex-start; justify-content: space-between; }
.asset-heading__actions { display: flex; gap: 9px; flex-wrap: wrap; }
.project-context { display: flex; gap: 14px; align-items: end; padding: 15px 17px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); flex-wrap: wrap; }
.project-context__meta { display: flex; flex: 1; gap: 8px; align-items: center; justify-content: flex-end; flex-wrap: wrap; }
.asset-filters { display: grid; grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(130px, 180px)) auto; gap: 9px; }
.asset-toolbar { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.asset-toolbar > div:first-child { display: flex; gap: 6px; align-items: baseline; }
.asset-toolbar strong { font-size: 23px; }
.asset-toolbar span { color: var(--sg-text-muted); font-size: 11px; }
.asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 13px; min-height: 120px; }
.asset-card { overflow: hidden; cursor: pointer; background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-md); transition: .18s ease; }
.asset-card:hover, .asset-card:focus { border-color: var(--sg-border-strong); transform: translateY(-2px); outline: 0; }
.asset-card header, .asset-card footer { display: flex; align-items: center; justify-content: space-between; }
.asset-card header { padding: 12px 14px 0; }
.asset-card h3, .asset-card p { margin: 0; padding: 0 14px; }
.asset-card h3 { margin-top: 10px; }
.asset-card p { min-height: 38px; margin-top: 6px; color: var(--sg-text-muted); font-size: 11px; line-height: 1.55; }
.asset-card footer { margin-top: 12px; padding: 10px 14px; color: var(--sg-text-muted); font-size: 10px; border-top: 1px solid var(--sg-border); }
.type-board { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; min-height: 120px; }
.type-board__column { min-width: 0; background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-md); }
.type-board__column :deep(.el-card__header) { padding: 14px; border-bottom-color: var(--sg-border); }
.type-board__column :deep(.el-card__body) { padding: 12px; }
.type-board__header, .type-board__heading { display: flex; gap: 8px; align-items: center; }
.type-board__header { justify-content: space-between; flex-wrap: wrap; }
.type-board__heading strong { color: var(--sg-text-secondary); font-size: 12px; font-weight: 500; }
.type-board__header small { color: var(--sg-text-muted); font-size: 11px; }
.type-board__items { display: grid; gap: 10px; }
.type-board__asset-row { display: flex; min-width: 0; flex-direction: column; gap: 8px; align-items: stretch; }
.type-board__asset {
  --el-button-bg-color: var(--sg-surface-raised);
  --el-button-border-color: var(--sg-border);
  --el-button-text-color: var(--sg-text);
  --el-button-hover-bg-color: var(--sg-surface-soft);
  --el-button-hover-border-color: var(--sg-border-strong);
  --el-button-hover-text-color: var(--sg-text);
  --el-button-active-bg-color: var(--sg-surface-soft);
  --el-button-active-border-color: var(--sg-border-strong);
  --el-button-active-text-color: var(--sg-text);
  width: 100%; height: auto; min-width: 0; margin: 0; padding: 12px;
  border-radius: 8px; text-align: left; white-space: normal; line-height: 1.5;
}
.type-board__asset :deep(> span) { width: 100%; min-width: 0; }
.type-board__content { display: grid; width: 100%; min-width: 0; grid-template-columns: 88px minmax(0, 1fr); gap: 14px; align-items: center; }
.type-board__content .asset-thumb--board { width: 88px; height: 76px; border-radius: 8px; }
.type-board__summary { display: flex; min-width: 0; flex-direction: column; align-items: flex-start; gap: 6px; }
.type-board__name { align-self: stretch; margin: 0; color: var(--sg-text); font-size: 14px; font-weight: 600; line-height: 1.5; white-space: normal; overflow-wrap: anywhere; }
.type-board__count { color: var(--sg-text-secondary); font-size: 12px; line-height: 1.5; }
.type-board__statuses { display: flex; max-width: 100%; gap: 6px; align-items: center; flex-wrap: wrap; }
.type-board__statuses .el-tag { margin: 0; flex-shrink: 0; }
.type-board__start { align-self: flex-end; margin: 0; }
.asset-empty, .asset-context-loading { min-height: 260px; background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-md); }
.asset-empty :deep(.el-empty__image .el-icon) { color: var(--sg-text-muted); font-size: 34px; }
.asset-empty p { margin: 8px 0 0; color: var(--sg-text-muted); font-size: 11px; }
.asset-pagination { justify-content: center; }
@media (max-width: 1100px) { .asset-filters { grid-template-columns: 1fr 1fr 1fr; } .type-board { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .asset-heading { flex-direction: column; } .asset-filters { grid-template-columns: 1fr; } .project-context__meta { justify-content: flex-start; } .asset-grid { grid-template-columns: 1fr; } }
.asset-toolbar{gap:12px}.asset-toolbar__summary{display:flex!important;gap:8px!important;align-items:center!important;flex-wrap:wrap}.asset-row-actions{display:flex;align-items:center;flex-wrap:wrap;gap:4px}.asset-row-actions :deep(.el-button){margin-left:0}.asset-batch-assign-dialog{display:grid;gap:16px}.asset-batch-assign-dialog p{margin:0;color:var(--sg-text-secondary);font-size:12px;line-height:1.65}.asset-batch-assign-dialog:deep(.el-form-item){margin-bottom:0}.asset-batch-assign-dialog:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.asset-batch-assign-dialog:deep(.el-select){width:100%}
.project-context:deep(.el-form-item){min-width:240px;margin:0}.project-context:deep(.el-form-item__label){height:auto;padding-bottom:6px;color:var(--sg-text-muted);font-size:10px;line-height:1}.asset-filters .asset-search{padding:0;background:transparent;border:0}.view-switch{padding:0;background:transparent}.view-switch:deep(.el-radio-button__inner){display:flex;gap:6px;align-items:center;color:var(--sg-text-muted);background:var(--sg-surface);border-color:var(--sg-border);box-shadow:none}.view-switch:deep(.el-radio-button__original-radio:checked+.el-radio-button__inner){color:var(--sg-accent);background:var(--sg-accent-soft);border-color:rgba(255,182,87,.32);box-shadow:-1px 0 0 0 rgba(255,182,87,.32)}.asset-card:deep(.el-card__body){padding:0}.asset-card>.asset-thumb,.asset-card:deep(.el-card__body>.asset-thumb){height:150px}.asset-pagination{margin-top:2px}.asset-pagination:deep(.el-pager li),.asset-pagination:deep(button){background:var(--sg-surface)!important}.asset-pagination:deep(.is-active){color:#17130d!important;background:var(--sg-accent)!important}
.asset-filters{grid-template-columns:minmax(220px,1fr) repeat(3,minmax(130px,180px)) auto}
.asset-filters:deep(.el-form-item){min-width:0;margin-bottom:0}
.asset-filter-item:deep(.el-form-item__content),.asset-filter-item:deep(.el-select),.asset-filter-item:deep(.el-input){width:100%;min-width:0}
.asset-filter-actions:deep(.el-form-item__content){flex-wrap:nowrap;justify-content:flex-end}
@media(max-width:1100px){.asset-filters{grid-template-columns:1fr 1fr 1fr}.asset-filter-actions:deep(.el-form-item__content){justify-content:flex-start}}
@media(max-width:700px){.asset-filters{grid-template-columns:1fr}}
.asset-item-status-counts{display:flex;gap:4px;align-items:center;justify-content:center;flex-wrap:wrap;font-size:10px}.asset-item-status-counts--card{padding:0 14px;justify-content:flex-start}
</style>
