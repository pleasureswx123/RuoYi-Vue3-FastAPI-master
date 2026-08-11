<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, Grid, List, Plus, Refresh, Search, Upload, VideoCamera } from '@element-plus/icons-vue'

import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { getEpisodePage, getScenePage, getShotPage, listShotAssignees } from '@/api/shot-grid/shots'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'
import { directoryStatusMeta, formatShotDuration, shotErrorState, shotStatusMeta } from '@/views/shot/shotPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const project = ref(null)
const episodes = ref([])
const scenes = ref([])
const members = ref([])
const shots = ref([])
const total = ref(0)
const hasNext = ref(false)
const projectsLoading = ref(false)
const shotsLoading = ref(false)
const scenesLoading = ref(false)
const projectsError = ref(null)
const shotsError = ref(null)
const viewMode = ref('table')
const showCreate = ref(false)
const showImport = ref(false)
const createProjectId = ref(null)
const importProjectId = ref(null)
const createOperationGeneration = ref(null)
const importOperationGeneration = ref(null)
const scope = ref('')
const selectedProjectId = ref('')
const query = reactive({
  keyword: '', episodeId: '', sceneId: '', shotStatus: '', assigneeUserId: '',
  pageNum: 1, pageSize: 20, orderByColumn: 'sortOrder', isAsc: 'ascending'
})
let projectController = null
let shotController = null
let sceneController = null
let episodeRefreshController = null
let disposed = false
let operationGeneration = 0

const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canViewAll = computed(() => hasPermission('shotgrid:project:all'))
const isDirector = computed(() => project.value?.myProjectRole === 'director' || wildcard.value || canViewAll.value)
const projectAllowsWrites = computed(() => project.value && !['completed', 'archived'].includes(project.value.projectStatus) && project.value.storageStatus === 'ready')
const canCreate = computed(() => isDirector.value && hasPermission('shotgrid:shot:add') && projectAllowsWrites.value)
const canImport = computed(() => isDirector.value && hasPermission('shotgrid:shot:import') && projectAllowsWrites.value)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const currentProjectId = computed(() => {
  try { return assertPositiveId(selectedProjectId.value, '项目') } catch { return null }
})
const creatorMembers = computed(() => members.value.filter(member => member.producerCode))

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
    projects.value = await fetchAllPages(
      (params, options) => getProjectPage(params, options),
      { scope: scope.value || undefined, orderByColumn: 'projectName', isAsc: 'ascending' },
      controller.signal
    )
    const routeId = preferredId || route.query.projectId
    const candidate = projects.value.find(item => String(item.projectId) === String(routeId)) || projects.value[0]
    selectedProjectId.value = candidate ? String(candidate.projectId) : ''
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      projects.value = []
      selectedProjectId.value = ''
      projectsError.value = shotErrorState(error, '项目范围加载失败')
    }
  } finally {
    if (projectController === controller) projectsLoading.value = false
  }
}

async function loadProjectContext() {
  const projectId = currentProjectId.value
  shotController?.abort()
  sceneController?.abort()
  episodeRefreshController?.abort()
  project.value = null
  episodes.value = []
  scenes.value = []
  members.value = []
  shots.value = []
  total.value = 0
  if (!projectId) return
  const controller = new AbortController()
  shotController = controller
  shotsLoading.value = true
  shotsError.value = null
  try {
    await router.replace({ query: { ...route.query, projectId: String(projectId) } })
    if (controller.signal.aborted || currentProjectId.value !== projectId) return
    const [detailResponse, episodeRows, memberResponse] = await Promise.all([
      getProjectDetail(projectId, { signal: controller.signal }),
      fetchAllPages(
        (params, options) => getEpisodePage(projectId, params, options),
        { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
        controller.signal
      ),
      fetchAllPages(
        (params, options) => listShotAssignees(projectId, params, options),
        {},
        controller.signal
      )
    ])
    project.value = detailResponse.data
    episodes.value = episodeRows
    members.value = Array.isArray(memberResponse) ? memberResponse : []
    if (query.episodeId && !episodes.value.some(item => String(item.episodeId) === query.episodeId)) {
      query.episodeId = ''
      query.sceneId = ''
    }
    await loadScenes(false)
    await loadShots(controller)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') shotsError.value = shotErrorState(error, '镜头项目上下文加载失败')
  } finally {
    if (shotController === controller) shotsLoading.value = false
  }
}

async function loadScenes(resetScene = true) {
  sceneController?.abort()
  scenes.value = []
  if (resetScene) query.sceneId = ''
  const projectId = currentProjectId.value
  const episodeId = Number(query.episodeId)
  if (!projectId || !Number.isSafeInteger(episodeId) || episodeId <= 0) return
  const controller = new AbortController()
  sceneController = controller
  scenesLoading.value = true
  try {
    scenes.value = await fetchAllPages(
      (params, options) => getScenePage(projectId, episodeId, params, options),
      { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
      controller.signal
    )
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') shotsError.value = shotErrorState(error, '场次筛选项加载失败')
  } finally {
    if (sceneController === controller) scenesLoading.value = false
  }
}

async function loadShots(existingController = null) {
  const projectId = currentProjectId.value
  if (!projectId) return
  if (!existingController) shotController?.abort()
  const controller = existingController || new AbortController()
  shotController = controller
  shotsLoading.value = true
  shotsError.value = null
  try {
    const response = await getShotPage(projectId, {
      keyword: query.keyword.trim() || undefined,
      episodeId: query.episodeId || undefined,
      sceneId: query.sceneId || undefined,
      shotStatus: query.shotStatus || undefined,
      assigneeUserId: query.assigneeUserId || undefined,
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: query.orderByColumn,
      isAsc: query.isAsc
    }, { signal: controller.signal })
    shots.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
    hasNext.value = Boolean(response.hasNext)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      shots.value = []
      total.value = 0
      shotsError.value = shotErrorState(error, '镜头列表加载失败')
    }
  } finally {
    if (shotController === controller) shotsLoading.value = false
  }
}

function submitFilters() {
  query.pageNum = 1
  loadShots()
}

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum) return
  query.pageNum = page
  loadShots()
}

async function openShot(shot) {
  await router.push(`/projects/${currentProjectId.value}/shots/${shot.shotId}`)
}

function openCreateDialog() {
  if (!currentProjectId.value) return
  createProjectId.value = currentProjectId.value
  createOperationGeneration.value = ++operationGeneration
  showCreate.value = true
}

function closeCreateDialog() {
  showCreate.value = false
  createProjectId.value = null
  createOperationGeneration.value = null
}

function openImportDialog() {
  if (!currentProjectId.value) return
  importProjectId.value = currentProjectId.value
  importOperationGeneration.value = ++operationGeneration
  showImport.value = true
}

function closeImportDialog() {
  showImport.value = false
  importProjectId.value = null
  importOperationGeneration.value = null
}

function notifyDetachedOperation() {
  ElMessage.success('操作已完成；当前项目未自动刷新。')
}

function isActiveOperation(targetProjectId, targetGeneration, operationContext) {
  return (
    targetProjectId === Number(operationContext?.projectId) &&
    targetGeneration === Number(operationContext?.operationGeneration)
  )
}

async function handleSaved(_result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!isActiveOperation(createProjectId.value, createOperationGeneration.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeCreateDialog()
  if (currentProjectId.value !== targetProjectId) { notifyDetachedOperation(); return }
  ElMessage.success('镜头已创建')
  await Promise.all([loadShots(), loadEpisodesAfterWrite()])
}

async function loadEpisodesAfterWrite() {
  const projectId = currentProjectId.value
  if (!projectId) return
  episodeRefreshController?.abort()
  const controller = new AbortController()
  episodeRefreshController = controller
  try {
    const rows = await fetchAllPages(
      (params, options) => getEpisodePage(projectId, params, options),
      { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
      controller.signal
    )
    if (episodeRefreshController === controller && currentProjectId.value === projectId) episodes.value = rows
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && currentProjectId.value === projectId) {
      shotsError.value = shotErrorState(error, '集选项刷新失败')
    }
  }
}

async function handleImported(result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!isActiveOperation(importProjectId.value, importOperationGeneration.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeImportDialog()
  if (currentProjectId.value !== targetProjectId) { notifyDetachedOperation(); return }
  ElMessage.success(`镜头导入完成：${result.createdShots} 个新镜头`)
  query.pageNum = 1
  await Promise.all([loadShots(), loadEpisodesAfterWrite()])
}

watch(selectedProjectId, (next, previous) => {
  if (next !== previous) {
    closeCreateDialog()
    closeImportDialog()
    query.pageNum = 1
    query.episodeId = ''
    query.sceneId = ''
    query.assigneeUserId = ''
    loadProjectContext()
  }
})
watch(() => query.episodeId, () => loadScenes(true))
watch(scope, () => loadProjects())
onMounted(() => loadProjects(route.query.projectId))
onBeforeUnmount(() => { disposed = true; projectController?.abort(); shotController?.abort(); sceneController?.abort(); episodeRefreshController?.abort() })
</script>

<template>
  <section class="sg-page shot-page">
    <header class="sg-page-heading shot-heading">
      <div><p class="sg-eyebrow">SHOTS</p><h2 class="sg-page-title">镜头管理</h2><p class="sg-page-description">同一份服务端分页结果支持表格、卡片和故事板三种视图；所有写入均受项目角色与接口权限约束。</p></div>
      <div class="shot-heading__actions"><el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建镜头</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <section class="project-context">
        <label><span>当前项目</span><select v-model="selectedProjectId" :disabled="projectsLoading"><option value="">{{ projectsLoading ? '正在加载项目…' : '请选择项目' }}</option><option v-for="item in projects" :key="item.projectId" :value="String(item.projectId)">{{ item.projectCode }} · {{ item.projectName }}</option></select></label>
        <label v-if="canViewAll"><span>项目范围</span><select v-model="scope"><option value="">我的项目</option><option value="all">全部项目</option></select></label>
        <div v-if="project" class="project-context__meta"><span>{{ project.projectTypeName }}</span><span>{{ project.aspectRatio }}</span><span>{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</span><span :data-ready="project.storageStatus === 'ready'">存储：{{ project.storageStatus === 'ready' ? '就绪' : project.storageStatus === 'failed' ? '失败' : '初始化中' }}</span></div>
      </section>

      <section v-if="!selectedProjectId && !projectsLoading" class="shot-empty"><el-icon><Collection /></el-icon><h3>当前范围暂无可选项目</h3><p>请先创建项目或加入项目成员范围；具备跨项目权限时也可以切换“全部项目”。</p></section>

      <template v-else-if="selectedProjectId">
        <form class="shot-filters" aria-label="镜头筛选" @submit.prevent="submitFilters">
          <label class="shot-search"><el-icon><Search /></el-icon><input v-model="query.keyword" maxlength="200" placeholder="镜头号、目录、内容、台词或场次名称" /></label>
          <select v-model="query.episodeId" aria-label="按集筛选"><option value="">全部集</option><option v-for="episode in episodes" :key="episode.episodeId" :value="String(episode.episodeId)">{{ episode.episodeCode }} {{ episode.episodeName || '' }}</option></select>
          <select v-model="query.sceneId" aria-label="按场次筛选" :disabled="!query.episodeId || scenesLoading"><option value="">{{ scenesLoading ? '加载场次中…' : '全部场次' }}</option><option v-for="scene in scenes" :key="scene.sceneId" :value="String(scene.sceneId)">{{ scene.sceneCode }} {{ scene.sceneName || '' }}</option></select>
          <select v-model="query.shotStatus" aria-label="按状态筛选"><option value="">全部状态</option><option v-for="status in ['unassigned','not_started','in_progress','reviewing','revision','completed']" :key="status" :value="status">{{ shotStatusMeta(status).label }}</option></select>
          <select v-model="query.assigneeUserId" aria-label="按制作人筛选"><option value="">全部制作人</option><option v-for="member in creatorMembers" :key="member.userId" :value="String(member.userId)">{{ member.nickName }}（{{ member.producerCode }}）</option></select>
          <el-button native-type="submit" :loading="shotsLoading">查询</el-button><el-button :icon="Refresh" circle aria-label="刷新镜头" :disabled="shotsLoading" @click="loadShots" />
        </form>

        <div class="shot-list-toolbar"><span>共 {{ total }} 个镜头<span v-if="shotsLoading"> · 正在刷新</span></span><div role="group" aria-label="镜头视图"><button v-for="mode in [{key:'table',icon:List,label:'表格'},{key:'card',icon:Grid,label:'卡片'},{key:'storyboard',icon:VideoCamera,label:'故事板'}]" :key="mode.key" type="button" :class="{ active:viewMode===mode.key }" :aria-pressed="viewMode===mode.key" @click="viewMode=mode.key"><el-icon><component :is="mode.icon" /></el-icon>{{ mode.label }}</button></div></div>

        <ProjectStatePanel v-if="shotsError" :title="shotsError.title" :message="shotsError.message" :retryable="shotsError.retryable" @retry="loadProjectContext" />
        <div v-else-if="shotsLoading && !shots.length" class="shot-loading">正在加载镜头数据…</div>
        <section v-else-if="!shots.length" class="shot-empty"><el-icon><VideoCamera /></el-icon><h3>当前筛选没有镜头</h3><p>可以调整集、场次、状态或制作人筛选；项目总监也可以新建或导入镜头。</p></section>

        <div v-else-if="viewMode === 'table'" class="shot-table-wrap" :class="{ 'is-refreshing':shotsLoading }"><table><thead><tr><th>集 / 场 / 镜头</th><th>缩略图</th><th>制作内容</th><th>镜头参数</th><th>场景 / 角色</th><th>制作人</th><th>状态</th><th>最新反馈</th><th></th></tr></thead><tbody><tr v-for="shot in shots" :key="shot.shotId"><td><strong>{{ shot.episodeCode }} / {{ shot.sceneCode }} / {{ shot.shotCode }}</strong><small>顺序 {{ shot.sortOrder }} · {{ formatShotDuration(shot.durationMs) }}</small></td><td><ProtectedThumbnail class="shot-thumb shot-thumb--small" :thumbnail="shot.thumbnail" :alt="`${shot.shotCode} 缩略图`" /></td><td class="shot-description">{{ shot.description }}</td><td><span>{{ shot.shotSize || '—' }}</span><small>{{ [shot.cameraPosition,shot.cameraMovement,shot.focalLength].filter(Boolean).join(' · ') || '暂无参数' }}</small></td><td><span>{{ shot.environmentAssets.map(item=>item.assetName).join('、') || '—' }}</span><small>{{ shot.characterAssets.map(item=>item.assetName).join('、') || '暂无角色资产' }}</small></td><td>{{ shot.assignee ? `${shot.assignee.nickName}（${shot.assignee.producerCode || '无缩写'}）` : '未分配' }}</td><td><span class="shot-chip" :data-tone="shotStatusMeta(shot.status).tone">{{ shotStatusMeta(shot.status).label }}</span><small :data-tone="directoryStatusMeta(shot.directoryStatus).tone">{{ directoryStatusMeta(shot.directoryStatus).label }}</small></td><td class="feedback-cell">{{ shot.latestFeedback?.content || '—' }}</td><td><el-button text type="primary" @click="openShot(shot)">详情</el-button></td></tr></tbody></table></div>

        <div v-else-if="viewMode === 'card'" class="shot-grid" :class="{ 'is-refreshing':shotsLoading }"><article v-for="shot in shots" :key="shot.shotId" class="shot-card" tabindex="0" @click="openShot(shot)" @keydown.enter="openShot(shot)"><div class="shot-card__media"><ProtectedThumbnail class="shot-thumb" :thumbnail="shot.thumbnail" :alt="`${shot.shotCode} 缩略图`" /><span class="shot-card__duration">{{ formatShotDuration(shot.durationMs) }}</span></div><header><div><small>{{ shot.episodeCode }} / {{ shot.sceneCode }}</small><h3>{{ shot.shotCode }}</h3></div><span class="shot-chip" :data-tone="shotStatusMeta(shot.status).tone">{{ shotStatusMeta(shot.status).label }}</span></header><p>{{ shot.description }}</p><footer><span>{{ shot.assignee ? `${shot.assignee.nickName} · ${shot.assignee.producerCode || '无缩写'}` : '未分配制作人' }}</span><span>{{ shot.shotSize || '未设景别' }}</span></footer></article></div>

        <div v-else class="storyboard" :class="{ 'is-refreshing':shotsLoading }"><article v-for="(shot,index) in shots" :key="shot.shotId" class="story-frame" tabindex="0" @click="openShot(shot)" @keydown.enter="openShot(shot)"><span class="story-frame__index">{{ String((query.pageNum-1)*query.pageSize+index+1).padStart(3,'0') }}</span><ProtectedThumbnail class="shot-thumb" :thumbnail="shot.thumbnail" :alt="`${shot.shotCode} 缩略图`" /><div><strong>{{ shot.episodeCode }} · {{ shot.sceneCode }} · {{ shot.shotCode }}</strong><p>{{ shot.description }}</p><small>{{ formatShotDuration(shot.durationMs) }} · {{ shot.shotSize || '未设景别' }} · {{ shot.assignee?.producerCode || '未分配' }}</small></div></article></div>

        <nav v-if="shots.length" class="shot-pagination" aria-label="镜头分页"><el-button :disabled="query.pageNum<=1||shotsLoading" @click="changePage(query.pageNum-1)">上一页</el-button><span>第 {{ query.pageNum }} / {{ pageCount }} 页</span><el-button :disabled="!hasNext||shotsLoading" @click="changePage(query.pageNum+1)">下一页</el-button></nav>
      </template>
    </template>

    <ShotFormDialog v-if="showCreate && createProjectId && createOperationGeneration" :project-id="createProjectId" :operation-generation="createOperationGeneration" :episodes="episodes" :members="members" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <ShotImportDialog v-if="showImport && importProjectId && importOperationGeneration" :project-id="importProjectId" :operation-generation="importOperationGeneration" :project-name="project?.projectName" @close="closeImportDialog" @imported="handleImported" />
  </section>
</template>

<style scoped>
.shot-card__media{position:relative}
.shot-page{position:relative}.shot-heading__actions{display:flex;gap:10px}.project-context{display:flex;gap:16px;align-items:end;margin-bottom:14px;padding:16px;background:linear-gradient(90deg,rgba(255,182,87,.06),transparent),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.project-context label{display:grid;min-width:280px;gap:6px}.project-context label>span{color:var(--sg-text-muted);font-size:10px}.project-context__meta{display:flex;flex:1;gap:8px;justify-content:flex-end;flex-wrap:wrap}.project-context__meta span{padding:7px 9px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.035);border-radius:8px}.project-context__meta span[data-ready=true]{color:var(--sg-success)}select,input{color:var(--sg-text);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}select{height:40px;padding:0 10px}.shot-filters{display:grid;grid-template-columns:minmax(240px,1.6fr) repeat(4,minmax(130px,.7fr)) auto auto;gap:9px;margin-bottom:14px;padding:14px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.shot-search{display:flex;height:40px;gap:8px;align-items:center;padding:0 11px;background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}.shot-search input{min-width:0;flex:1;background:transparent;border:0;outline:0}.shot-list-toolbar{display:flex;align-items:center;justify-content:space-between;margin:0 2px 12px;color:var(--sg-text-muted);font-size:12px}.shot-list-toolbar>div{display:flex;gap:5px;padding:4px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:9px}.shot-list-toolbar button{display:flex;gap:5px;align-items:center;padding:7px 9px;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0;border-radius:6px}.shot-list-toolbar button.active{color:var(--sg-accent);background:var(--sg-accent-soft)}.shot-loading,.shot-empty{display:grid;min-height:320px;place-items:center;align-content:center;padding:30px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg)}.shot-empty>.el-icon{color:var(--sg-accent);font-size:34px}.shot-empty h3,.shot-empty p{margin:12px 0 0}.shot-empty p{max-width:600px;font-size:12px;text-align:center}.shot-table-wrap{overflow:auto;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}table{width:100%;min-width:1340px;border-collapse:collapse}th,td{padding:12px;border-bottom:1px solid var(--sg-border);font-size:11px;text-align:left;vertical-align:middle}th{color:var(--sg-text-muted);font-weight:650;background:rgba(255,255,255,.018)}td{color:var(--sg-text-secondary)}td strong,td small{display:block}td small{margin-top:5px;color:var(--sg-text-muted)}.shot-description{max-width:300px;line-height:1.55}.feedback-cell{max-width:220px}.shot-chip{display:inline-flex;padding:5px 8px;font-size:10px;border-radius:999px;background:rgba(255,255,255,.04)}.shot-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.shot-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.shot-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}.shot-chip[data-tone=info]{color:#80bfff;background:rgba(128,191,255,.09)}small[data-tone=success]{color:var(--sg-success)}small[data-tone=danger]{color:var(--sg-danger)}small[data-tone=warning]{color:var(--sg-accent)}.shot-thumb{position:relative;overflow:hidden;aspect-ratio:16/9;background:linear-gradient(135deg,#202630,#11151b);border-radius:10px}.shot-thumb img{width:100%;height:100%;object-fit:cover}.shot-thumb>div{display:grid;width:100%;height:100%;gap:5px;color:var(--sg-text-muted);place-items:center;align-content:center}.shot-thumb--small{width:90px}.shot-thumb--small>.el-icon{position:absolute;top:50%;left:50%;color:var(--sg-text-muted);font-size:20px;transform:translate(-50%,-50%)}.shot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.shot-card{padding:12px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.shot-card:hover,.shot-card:focus-visible,.story-frame:hover,.story-frame:focus-visible{border-color:rgba(255,182,87,.35);outline:0;transform:translateY(-2px)}.shot-card__duration{position:absolute;right:8px;bottom:8px;padding:4px 6px;color:white;font-size:10px;background:rgba(0,0,0,.72);border-radius:5px}.shot-card header,.shot-card footer{display:flex;gap:10px;align-items:center;justify-content:space-between}.shot-card header{margin-top:13px}.shot-card h3,.shot-card small,.shot-card p{margin:0}.shot-card h3{margin-top:3px;font-size:18px}.shot-card small,.shot-card footer{color:var(--sg-text-muted);font-size:10px}.shot-card>p{min-height:44px;margin:11px 0;color:var(--sg-text-secondary);font-size:12px;line-height:1.55}.storyboard{display:grid;gap:10px}.story-frame{display:grid;grid-template-columns:45px 230px 1fr;gap:14px;align-items:center;padding:10px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.story-frame__index{color:var(--sg-accent);font-size:12px;font-weight:800;text-align:center}.story-frame p{margin:7px 0;color:var(--sg-text-secondary);font-size:12px}.story-frame small{color:var(--sg-text-muted)}.is-refreshing{opacity:.55}.shot-pagination{display:flex;gap:14px;align-items:center;justify-content:center;margin-top:20px;color:var(--sg-text-muted);font-size:12px}@media(max-width:1180px){.shot-filters{grid-template-columns:repeat(3,minmax(0,1fr))}.shot-search{grid-column:span 2}.shot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.project-context{align-items:stretch;flex-direction:column}.project-context__meta{justify-content:flex-start}}@media(max-width:700px){.shot-filters,.shot-grid{grid-template-columns:1fr}.shot-search{grid-column:auto}.story-frame{grid-template-columns:35px 120px 1fr}.project-context label{min-width:0}}
</style>
