<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Box, Collection, Grid, List, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'

import { getAssetPage, listAssetAssignees } from '@/api/shot-grid/assets'
import { assertPositiveId, getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import AssetImportDialog from '@/views/asset/components/AssetImportDialog.vue'
import ProtectedAssetThumbnail from '@/views/asset/components/ProtectedAssetThumbnail.vue'
import { assetAssigneeSummary, assetDirectoryStatusMeta, assetErrorState, assetStatusMeta, assetTypeMeta, memberLabel, resolveAssetThumbnail } from '@/views/asset/assetPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const project = ref(null)
const members = ref([])
const assets = ref([])
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
const createContext = ref(null)
const importContext = ref(null)
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
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      assets.value = []
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

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum) return
  query.pageNum = page
  loadAssets()
}

async function openAsset(asset) {
  await router.push(`/projects/${currentProjectId.value}/assets/${asset.assetId}`)
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
      <div class="asset-heading__actions"><el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建资产</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <section class="project-context">
        <label><span>当前项目</span><select v-model="selectedProjectId" :disabled="projectsLoading"><option value="">{{ projectsLoading ? '正在加载项目…' : '请选择项目' }}</option><option v-for="item in projects" :key="item.projectId" :value="String(item.projectId)">{{ item.projectCode }} · {{ item.projectName }}</option></select></label>
        <label v-if="canViewAll"><span>项目范围</span><select v-model="scope"><option value="">我的项目</option><option value="all">全部项目</option></select></label>
        <div v-if="project" class="project-context__meta"><span>{{ project.projectTypeName }}</span><span>{{ project.aspectRatio }}</span><span>{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</span><span :data-ready="project.storageStatus === 'ready'">存储：{{ project.storageStatus === 'ready' ? '就绪' : project.storageStatus === 'failed' ? '失败' : '初始化中' }}</span></div>
      </section>

      <section v-if="!selectedProjectId && !projectsLoading" class="asset-empty"><el-icon><Collection /></el-icon><h3>当前范围暂无可选项目</h3><p>请先创建项目或加入项目成员范围。</p></section>

      <template v-else-if="selectedProjectId">
        <form class="asset-filters" aria-label="资产筛选" @submit.prevent="submitFilters">
          <label class="asset-search"><el-icon><Search /></el-icon><input v-model="query.keyword" maxlength="200" placeholder="资产名称或描述" /></label>
          <select v-model="query.assetType" aria-label="按资产类型筛选"><option value="">全部类型</option><option value="Character">角色</option><option value="Environment">场景</option><option value="Prop">道具</option></select>
          <select v-model="query.assetStatus" aria-label="按资产状态筛选"><option value="">全部状态</option><option value="unassigned">未分配</option><option value="not_started">未开始</option><option value="in_progress">制作中</option><option value="reviewing">待审核</option><option value="revision">修改中</option><option value="completed">已完成</option></select>
          <select v-model="query.assigneeUserId" aria-label="按制作人筛选"><option value="">全部制作人</option><option v-for="member in members" :key="member.userId" :value="String(member.userId)">{{ memberLabel(member) }}</option></select>
          <el-button native-type="submit" :icon="Search" :loading="assetsLoading">查询</el-button>
          <el-button :icon="Refresh" :disabled="assetsLoading" @click="loadProjectContext">刷新</el-button>
        </form>

        <section class="asset-toolbar"><div><strong>{{ total }}</strong><span>个资产</span></div><div class="view-switch"><button type="button" :data-active="viewMode === 'table'" @click="viewMode = 'table'"><el-icon><List /></el-icon>表格</button><button type="button" :data-active="viewMode === 'card'" @click="viewMode = 'card'"><el-icon><Grid /></el-icon>卡片</button><button type="button" :data-active="viewMode === 'type'" @click="viewMode = 'type'"><el-icon><Box /></el-icon>类型看板</button></div></section>

        <ProjectStatePanel v-if="assetsError" :title="assetsError.title" :message="assetsError.message" :retryable="assetsError.retryable" @retry="loadProjectContext" />
        <section v-else-if="!assetsLoading && !assets.length" class="asset-empty"><el-icon><Box /></el-icon><h3>当前筛选没有资产</h3><p>调整筛选条件，或在存储就绪的活动项目中新建/导入资产。</p></section>

        <div v-else-if="viewMode === 'table'" class="asset-table-wrap" :class="{ 'is-refreshing': assetsLoading }"><table><thead><tr><th>缩略图</th><th>类型 / 名称</th><th>说明</th><th>制作分项</th><th>制作人</th><th>镜头使用</th><th>状态 / 目录</th><th></th></tr></thead><tbody><tr v-for="asset in assets" :key="asset.assetId"><td><ProtectedAssetThumbnail class="asset-thumb asset-thumb--small" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /></td><td><span class="type-chip" :data-tone="assetTypeMeta(asset.assetType).tone">{{ assetTypeMeta(asset.assetType).label }}</span><strong>{{ asset.assetName }}</strong><small>排序 {{ asset.sortOrder }}</small></td><td class="asset-description">{{ asset.description || '—' }}</td><td>{{ asset.itemCount }}</td><td>{{ assetAssigneeSummary(asset.assigneeUserIds, members) }}</td><td>{{ asset.usageShotCount }}</td><td><span class="status-chip" :data-tone="assetStatusMeta(asset.assetStatus).tone">{{ assetStatusMeta(asset.assetStatus).label }}</span><small :data-tone="assetDirectoryStatusMeta(asset.directoryStatus).tone">{{ assetDirectoryStatusMeta(asset.directoryStatus).label }}</small></td><td><el-button text type="primary" @click="openAsset(asset)">详情</el-button></td></tr></tbody></table></div>

        <div v-else-if="viewMode === 'card'" class="asset-grid" :class="{ 'is-refreshing': assetsLoading }"><article v-for="asset in assets" :key="asset.assetId" class="asset-card" tabindex="0" @click="openAsset(asset)" @keydown.enter="openAsset(asset)"><ProtectedAssetThumbnail class="asset-thumb" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /><header><span class="type-chip" :data-tone="assetTypeMeta(asset.assetType).tone">{{ assetTypeMeta(asset.assetType).label }}</span><span class="status-chip" :data-tone="assetStatusMeta(asset.assetStatus).tone">{{ assetStatusMeta(asset.assetStatus).label }}</span></header><h3>{{ asset.assetName }}</h3><p>{{ asset.description || '暂无资产说明' }}</p><footer><span>{{ asset.itemCount }} 个制作分项</span><span>{{ asset.usageShotCount }} 个使用镜头</span></footer></article></div>

        <div v-else class="type-board" :class="{ 'is-refreshing': assetsLoading }"><section v-for="group in groupedAssets" :key="group.type"><header><div><span class="type-chip" :data-tone="assetTypeMeta(group.type).tone">{{ assetTypeMeta(group.type).label }}</span><strong>{{ group.assets.length }}</strong></div><small>当前分页结果</small></header><div v-if="group.assets.length"><button v-for="asset in group.assets" :key="asset.assetId" type="button" @click="openAsset(asset)"><ProtectedAssetThumbnail class="asset-thumb asset-thumb--board" :thumbnail="resolveAssetThumbnail(asset)" :alt="`${asset.assetName} 缩略图`" /><span><strong>{{ asset.assetName }}</strong><small>{{ asset.itemCount }} 分项 · {{ assetStatusMeta(asset.assetStatus).label }}</small></span></button></div><p v-else>本页暂无{{ assetTypeMeta(group.type).label }}资产</p></section></div>

        <nav v-if="total" class="asset-pagination" aria-label="资产分页"><button type="button" :disabled="query.pageNum <= 1 || assetsLoading" @click="changePage(query.pageNum - 1)">上一页</button><span>第 {{ query.pageNum }} / {{ pageCount }} 页</span><button type="button" :disabled="query.pageNum >= pageCount || assetsLoading" @click="changePage(query.pageNum + 1)">下一页</button></nav>
      </template>
    </template>

    <AssetFormDialog v-if="showCreate && createContext" :project-id="createContext.projectId" :operation-generation="createContext.operationGeneration" :members="members" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <AssetImportDialog v-if="showImport && importContext" :project-id="importContext.projectId" :operation-generation="importContext.operationGeneration" :project-name="project?.projectName" @close="closeImportDialog" @imported="handleImported" />
  </section>
</template>

<style scoped>
.asset-page{display:grid;gap:18px}.asset-heading{display:flex;gap:20px;align-items:flex-start;justify-content:space-between}.asset-heading__actions{display:flex;gap:9px}.project-context{display:flex;gap:14px;align-items:end;padding:15px 17px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);flex-wrap:wrap}.project-context label{display:grid;min-width:240px;gap:6px}.project-context label span{color:var(--sg-text-muted);font-size:10px}.project-context select,.asset-filters select,.asset-search{padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.project-context__meta{display:flex;gap:8px;align-items:center;flex:1;justify-content:flex-end;flex-wrap:wrap}.project-context__meta span{padding:6px 8px;color:var(--sg-text-muted);font-size:10px;background:rgba(255,255,255,.035);border-radius:7px}.project-context__meta span[data-ready=true]{color:var(--sg-success)}.asset-filters{display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,minmax(130px,180px)) auto auto;gap:9px}.asset-search{display:flex;gap:8px;align-items:center}.asset-search input{width:100%;color:var(--sg-text);background:transparent;border:0;outline:0}.asset-toolbar{display:flex;align-items:center;justify-content:space-between}.asset-toolbar>div:first-child{display:flex;gap:6px;align-items:baseline}.asset-toolbar strong{font-size:23px}.asset-toolbar span{color:var(--sg-text-muted);font-size:11px}.view-switch{display:flex;padding:3px;background:rgba(255,255,255,.035);border-radius:9px}.view-switch button{display:flex;gap:6px;align-items:center;padding:7px 9px;color:var(--sg-text-muted);font-size:11px;cursor:pointer;background:transparent;border:0;border-radius:7px}.view-switch button[data-active=true]{color:var(--sg-text);background:rgba(255,255,255,.08)}.asset-table-wrap{overflow:auto;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}table{width:100%;min-width:1040px;border-collapse:collapse}th,td{padding:12px;border-bottom:1px solid var(--sg-border);font-size:11px;text-align:left;vertical-align:middle}th{color:var(--sg-text-muted)}td{color:var(--sg-text-secondary)}td strong,td small{display:block;margin-top:4px}.asset-description{max-width:290px;line-height:1.55}.asset-thumb--small{width:82px;height:54px;border-radius:7px}.type-chip,.status-chip{display:inline-flex;width:max-content;padding:5px 7px;font-size:10px;border-radius:999px}.type-chip[data-tone=character]{color:var(--sg-accent);background:var(--sg-accent-soft)}.type-chip[data-tone=environment]{color:#80bfff;background:rgba(128,191,255,.08)}.type-chip[data-tone=prop]{color:#8dd8a9;background:rgba(98,212,155,.08)}.status-chip{color:var(--sg-text-muted);background:rgba(255,255,255,.05)}.status-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}td small[data-tone=success]{color:var(--sg-success)}td small[data-tone=warning]{color:var(--sg-accent)}td small[data-tone=danger]{color:var(--sg-danger)}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:13px}.asset-card{overflow:hidden;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:.18s ease}.asset-card:hover,.asset-card:focus{border-color:var(--sg-border-strong);transform:translateY(-2px);outline:0}.asset-card>.asset-thumb{height:150px}.asset-card header,.asset-card footer{display:flex;align-items:center;justify-content:space-between}.asset-card header{padding:12px 14px 0}.asset-card h3,.asset-card p{margin:0;padding:0 14px}.asset-card h3{margin-top:10px}.asset-card p{min-height:38px;margin-top:6px;color:var(--sg-text-muted);font-size:11px;line-height:1.55}.asset-card footer{margin-top:12px;padding:10px 14px;color:var(--sg-text-muted);font-size:10px;border-top:1px solid var(--sg-border)}.type-board{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.type-board>section{min-width:0;padding:13px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.type-board section>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}.type-board header div{display:flex;gap:8px;align-items:center}.type-board header small,.type-board section>p{color:var(--sg-text-muted);font-size:10px}.type-board section>div{display:grid;gap:8px}.type-board button{display:grid;grid-template-columns:68px 1fr;gap:9px;align-items:center;padding:8px;color:var(--sg-text);text-align:left;cursor:pointer;background:rgba(255,255,255,.025);border:1px solid transparent;border-radius:9px}.type-board button:hover{border-color:var(--sg-border-strong)}.asset-thumb--board{width:68px;height:48px;border-radius:6px}.type-board button span strong,.type-board button span small{display:block}.type-board button span small{margin-top:4px;color:var(--sg-text-muted);font-size:9px}.asset-empty{display:grid;min-height:260px;align-content:center;color:var(--sg-text-muted);text-align:center;background:var(--sg-surface);border:1px dashed var(--sg-border);border-radius:var(--sg-radius-md);place-items:center}.asset-empty>.el-icon{font-size:34px}.asset-empty h3,.asset-empty p{margin:8px 0 0}.asset-empty p{font-size:11px}.asset-pagination{display:flex;gap:12px;align-items:center;justify-content:center}.asset-pagination button{padding:8px 11px;color:var(--sg-text-secondary);cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:7px}.asset-pagination button:disabled{opacity:.35;cursor:not-allowed}.asset-pagination span{color:var(--sg-text-muted);font-size:11px}.is-refreshing{opacity:.55;pointer-events:none}@media(max-width:1100px){.asset-filters{grid-template-columns:1fr 1fr 1fr}.type-board{grid-template-columns:1fr}}@media(max-width:700px){.asset-heading{flex-direction:column}.asset-filters{grid-template-columns:1fr}.project-context label{min-width:100%}.project-context__meta{justify-content:flex-start}.asset-grid{grid-template-columns:1fr}}
</style>
