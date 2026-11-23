<script setup>
import FeedbackNotification from '@/components/FeedbackNotification.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElSubMenu } from 'element-plus'
import {
  Fold,
  Expand,
  Box,
  Reading,
  Collection,
  Film,
  FolderOpened,
  FullScreen,
  Grid,
  ScaleToOriginal,
  Search,
  SwitchButton,
  Tickets
} from '@element-plus/icons-vue'

import { useFeedbackInbox } from '@/store/modules/feedbackInbox'
import { useSessionStore } from '@/store/modules/session'
import GlobalSearchDialog from '@/components/search/GlobalSearchDialog.vue'
import ThemeModeSwitch from '@/components/theme/ThemeModeSwitch.vue'
import { getEpisodePage, getScenePage, listShotAssignees } from '@/api/shot-grid/shots'
import { listAssetAssignees } from '@/api/shot-grid/assets'
import { getMineReviewProducers } from '@/api/shot-grid/reviews'

const route = useRoute()
const desktopVersion = window.__SHOTGRID_VERSION__
function checkDesktopUpdate() {
  window.location.assign('/desktop-updates/check')
}
const router = useRouter()
const sessionStore = useSessionStore()
const inbox = useFeedbackInbox()
const collapsed = ref(typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 820px)').matches)
const searchVisible = ref(false)
const fullscreenSupported = ref(false)
const isFullscreen = ref(false)
const fullscreenPending = ref(false)
const companyLogoUrl = `${import.meta.env.BASE_URL}company_logo.svg`
const userManualUrl = `${import.meta.env.BASE_URL}help/user-manual.html`
const companyLogoMaskStyle = Object.freeze({
  '--app-company-logo-mask': `url("${companyLogoUrl}")`
})

const localNavigation = Object.freeze({
  'daily-records': { title: '每日记录', path: '/daily-records', icon: Reading },
  'production-statistics': { title: '产出统计', path: '/production-statistics', icon: Tickets },
  workbench: { title: '工作台', path: '/workbench', icon: Grid },
  projects: { title: '项目', path: '/projects', icon: Collection },
  shots: { title: '镜头管理', path: '/shots', icon: Film },
  assets: { title: '资产库管理', path: '/assets', icon: Box },
  reviews: { title: '版本审核', path: '/reviews', icon: Tickets },
  files: { title: '文件与 NAS', path: '/files', icon: FolderOpened }
})

const navigationItems = computed(() => {
  const serverItems = Array.isArray(sessionStore.navigation) ? sessionStore.navigation : []
  if (sessionStore.isCreatorWorkspace) {
    const keys = new Set(serverItems.map(item => item.routeKey))
    return [
      ...(keys.has('workbench') ? [{ ...localNavigation.workbench, routeKey: 'workbench', title: '我的任务', index: '/workbench' }] : []),
      ...(keys.has('daily-records') ? [{ ...localNavigation['daily-records'], routeKey: 'daily-records' }] : []),
      ...(keys.has('shots') ? [{ ...localNavigation.shots, routeKey: 'shots' }] : []),
      ...(keys.has('assets') ? [{ ...localNavigation.assets, routeKey: 'assets' }] : []),
      ...(keys.has('workbench') && sessionStore.permissions.includes('shotgrid:version:list')
        ? [{ ...localNavigation.workbench, icon: Tickets, routeKey: 'submissions', title: '提交记录', index: 'submissions', query: { tab: 'submissions' } }] : [])
    ]
  }

  return serverItems
    .map((item, index) => {
      if (!Object.hasOwn(localNavigation, item?.routeKey)) return null
      const localItem = localNavigation[item?.routeKey]

      return {
        ...localItem,
        routeKey: item.routeKey,
        title: item.title || localItem.title,
        orderNum: Number.isFinite(Number(item.orderNum)) ? Number(item.orderNum) : index
      }
    })
    .filter(Boolean)
    .sort((left, right) => (left.routeKey === 'projects' ? -1 : right.routeKey === 'projects' ? 1 : left.orderNum - right.orderNum))
})

// 项目与筛选使用现有 Pinia 会话作用域；退出登录清空，链接携带项目 ID。
const activeProject = ref(null)
const episodes = ref([])
const sceneGroups = reactive({})
const producers = ref([])
const catalogLoading = ref(false)
const catalogError = ref('')
const filterForm = ref(null)
const applyingFilters = ref(false)
const filterDraft = reactive({ assigneeUserId: '', dates: [] })
const filterRules = {
  dates: [{ validator: (_rule, value, done) => {
    done(value?.length && (value.length !== 2 || value[0] > value[1]) ? new Error('请选择有效的制作周期') : undefined)
  }, trigger: 'change' }]
}
const hasPermission = permission => sessionStore.permissions.includes('*:*:*') || sessionStore.permissions.includes(permission)
const showProductionFilters = computed(() => !sessionStore.isCreatorWorkspace && sessionStore.activeProjectId && ['shots', 'assets', 'workbench'].includes(route.name))
const workspaceKey = computed(() => `${sessionStore.activeProjectId}:${route.name === 'workbench' && !sessionStore.isCreatorWorkspace ? JSON.stringify(sessionStore.workspaceFilters) : ''}`)
let catalogController
async function allPages(loader, signal) {
  const rows = []
  for (let pageNum = 1; ; pageNum += 1) {
    const response = await loader({ pageNum, pageSize: 100 }, { signal })
    if (signal.aborted) return []
    rows.push(...(response.rows || []))
    if (!response.hasNext && rows.length >= Number(response.total || rows.length)) return rows
    if (!(response.rows || []).length) return rows
  }
}
async function loadWorkspaceCatalog() {
  catalogController?.abort()
  const request = new AbortController()
  catalogController = request
  const id = sessionStore.activeProjectId
  activeProject.value = null
  episodes.value = []
  producers.value = []
  Object.keys(sceneGroups).forEach(key => delete sceneGroups[key])
  catalogError.value = ''
  if (!id) { catalogLoading.value = false; return }
  catalogLoading.value = true
  try {
    const projectRows = await sessionStore.loadWorkspaceProjects({ signal: request.signal })
    if (request.signal.aborted) return
    activeProject.value = projectRows[0] || null
    if (hasPermission('shotgrid:episode:list')) {
      const rows = await allPages((params, options) => getEpisodePage(id, { ...params, lifecycleStatus: 'active', orderByColumn: 'episodeNo', isAsc: 'ascending' }, options), request.signal)
      if (request.signal.aborted) return
      episodes.value = rows
    }
    if (sessionStore.isCreatorWorkspace) return
    const loader = hasPermission('shotgrid:shot:list') ? listShotAssignees : hasPermission('shotgrid:asset:list') ? listAssetAssignees : null
    let rows = []
    if (loader) rows = await allPages((params, options) => loader(id, params, options), request.signal)
    else if (hasPermission('shotgrid:version:review') && hasPermission('shotgrid:reviewList:list')) {
      rows = (await getMineReviewProducers({ projectId: id }, { signal: request.signal })).data || []
    } else if (sessionStore.user) rows = [sessionStore.user]
    if (!request.signal.aborted) producers.value = rows
  } catch (error) {
    if (!request.signal.aborted) catalogError.value = error.message || '筛选选项加载失败'
  } finally {
    if (catalogController === request) catalogLoading.value = false
  }
}
async function loadSceneGroup(index) {
  if (!index.startsWith('episode:') || !hasPermission('shotgrid:scene:list')) return
  const episodeId = index.slice(8)
  if (sceneGroups[episodeId]?.loading || sceneGroups[episodeId]?.loaded) return
  const request = catalogController
  const id = sessionStore.activeProjectId
  if (!request || !id) return
  sceneGroups[episodeId] = { loading: true, loaded: false, error: '', rows: [] }
  try {
    const rows = await allPages((params, options) => getScenePage(id, episodeId, { ...params, lifecycleStatus: 'active', orderByColumn: 'sceneNo', isAsc: 'ascending' }, options), request.signal)
    if (request.signal.aborted) return
    sceneGroups[episodeId] = { loading: false, loaded: true, error: '', rows }
  } catch (error) {
    if (!request.signal.aborted) sceneGroups[episodeId] = { loading: false, loaded: false, error: error.message || '场次加载失败', rows: [] }
  }
}
function moduleLocation(path) {
  return { path, query: path === '/projects' ? {} : { projectId: sessionStore.activeProjectId } }
}
async function selectShotScope(episodeId = '', sceneId = '') {
  Object.assign(sessionStore.workspaceFilters, { episodeId: String(episodeId), sceneId: String(sceneId) })
  await router.push(moduleLocation('/shots'))
}
async function selectAssetType(assetType = '') {
  sessionStore.workspaceFilters.assetType = assetType
  await router.push(moduleLocation('/assets'))
}
async function applyProductionFilters() {
  if (applyingFilters.value) return
  applyingFilters.value = true
  try {
    if (!await filterForm.value.validate().catch(() => false)) return
    Object.assign(sessionStore.workspaceFilters, { assigneeUserId: filterDraft.assigneeUserId,
      productionFrom: filterDraft.dates?.[0] || '', productionTo: filterDraft.dates?.[1] || '' })
  } finally { applyingFilters.value = false }
}
function resetProductionFilters() {
  filterForm.value?.resetFields()
  filterDraft.assigneeUserId = ''
  filterDraft.dates = []
  filterForm.value?.clearValidate()
  void applyProductionFilters()
}
watch(() => sessionStore.activeProjectId, loadWorkspaceCatalog, { immediate: true })
watch(() => sessionStore.workspaceFilters, value => {
  filterDraft.assigneeUserId = value.assigneeUserId
  filterDraft.dates = value.productionFrom && value.productionTo ? [value.productionFrom, value.productionTo] : []
}, { deep: true, immediate: true })

const userDisplayName = computed(() => sessionStore.displayName)

const pageTitle = computed(() => {
  if (sessionStore.isCreatorWorkspace && route.name === 'workbench') {
    if (route.query.tab === 'submissions') return '提交记录'
    if (route.query.tab === 'messages' && hasPermission('shotgrid:note:list') && inbox.total > 0) return '我的消息'
    return '我的任务'
  }
  return route.meta?.title || 'Shot Grid'
})
const activeNavigationPath = computed(() => {
  if (sessionStore.isCreatorWorkspace && route.name === 'workbench') return route.query.tab === 'submissions' ? 'submissions' : '/workbench'
  const routeKey = route.meta?.routeKey
  const matchedByKey = navigationItems.value.find(item => item.routeKey === routeKey)
  if (route.name === 'shots') {
    const { episodeId, sceneId } = sessionStore.workspaceFilters
    return sceneId ? `shots:${episodeId}:${sceneId}` : episodeId ? `shots:${episodeId}` : 'shots:all'
  }
  if (route.name === 'assets') return `assets:${sessionStore.workspaceFilters.assetType || 'all'}`
  if (matchedByKey) return matchedByKey.path
  return navigationItems.value.find(item => route.path === item.path || route.path.startsWith(`${item.path}/`))?.path || ''
})
const canUseSearch = computed(() => {
  const permissions = sessionStore.permissions || []
  if (permissions.includes('*:*:*')) return true
  return [
    ['shotgrid:shot:list', 'shotgrid:shot:query'],
    ['shotgrid:asset:list', 'shotgrid:asset:query'],
    ['shotgrid:storage:path', 'shotgrid:version:query']
  ].some(required => required.every(permission => permissions.includes(permission)))
})
const passwordNotice = computed(() => {
  if (sessionStore.passwordNotice === 'expired') return '当前密码已过期，请尽快在管理平台修改密码。'
  return ''
})
const fullscreenLabel = computed(() => (isFullscreen.value ? '退出全屏' : '进入全屏'))

async function handleSignOut() {
  try {
    await ElMessageBox.confirm('确认退出当前工作空间吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await sessionStore.signOut().catch(() => undefined)
    await router.replace('/login')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') throw error
  }
}

function handleSearchShortcut(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && canUseSearch.value) {
    event.preventDefault()
    searchVisible.value = true
  }
}

function syncFullscreenState() {
  isFullscreen.value = Boolean(document.fullscreenElement)
}

async function toggleFullscreen() {
  if (!fullscreenSupported.value || fullscreenPending.value) return

  const leavingFullscreen = Boolean(document.fullscreenElement)
  fullscreenPending.value = true
  try {
    if (leavingFullscreen) {
      await document.exitFullscreen()
    } else {
      await document.documentElement.requestFullscreen()
    }
  } catch {
    ElMessage.warning(
      leavingFullscreen
        ? '无法退出全屏，请按 Esc 重试。'
        : '浏览器未允许进入全屏，请检查窗口权限后重试。'
    )
  } finally {
    syncFullscreenState()
    fullscreenPending.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleSearchShortcut)
  fullscreenSupported.value = document.fullscreenEnabled !== false
    && typeof document.documentElement?.requestFullscreen === 'function'
    && typeof document.exitFullscreen === 'function'
  syncFullscreenState()
  if (fullscreenSupported.value) {
    document.addEventListener('fullscreenchange', syncFullscreenState)
  }
})

onBeforeUnmount(() => {
  catalogController?.abort()
  window.removeEventListener('keydown', handleSearchShortcut)
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  if (document.fullscreenElement === document.documentElement && typeof document.exitFullscreen === 'function') {
    void document.exitFullscreen().catch(() => undefined)
  }
})
</script>

<template>
  <el-container class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <el-aside class="app-sidebar" width="var(--app-sidebar-width)" aria-label="Shot Grid 主导航">
      <div class="app-brand">
        <span class="app-brand__mark" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
        <span v-show="!collapsed" class="app-brand__copy">
          <strong>SHOT GRID</strong>
          <small>影视制作协作平台<span v-if="desktopVersion"> · V{{ desktopVersion }}</span></small>
        </span>
      </div>

      <nav id="shot-grid-navigation" class="app-navigation">
        <p v-show="!collapsed" class="app-navigation__label">{{ activeProject?.projectName || (sessionStore.isCreatorWorkspace ? '我的全部项目任务' : '请先选择项目') }}</p>
        <el-button v-if="sessionStore.isCreatorWorkspace && sessionStore.allowedRouteKeys.has('projects')" link type="primary" aria-label="切换项目" @click="router.push('/projects')">{{ collapsed ? '项目' : '选择 / 切换项目' }}</el-button>
        <el-alert v-if="catalogError && !collapsed" :title="catalogError" type="error" :closable="false"><el-button link @click="loadWorkspaceCatalog">重新加载</el-button></el-alert>
        <el-menu
          v-if="navigationItems.length"
          class="app-navigation__menu"
          @open="loadSceneGroup"
          :collapse="collapsed"
          :collapse-transition="false"
          :default-active="activeNavigationPath"
        >
          <template v-for="item in navigationItems" :key="item.routeKey">
            <el-sub-menu v-if="item.routeKey === 'shots' && sessionStore.activeProjectId" index="/shots">
              <template #title><el-icon><Film /></el-icon><span>镜头管理</span></template>
              <el-menu-item index="shots:all" @click="selectShotScope()">全部镜头</el-menu-item>
              <el-sub-menu v-for="episode in episodes" :key="episode.episodeId" :index="`episode:${episode.episodeId}`">
                <template #title>{{ episode.episodeName || `第 ${episode.episodeNo} 集` }}</template>
                <el-menu-item :index="`shots:${episode.episodeId}`" @click="selectShotScope(episode.episodeId)">本集全部场次</el-menu-item>
                <el-menu-item v-if="sceneGroups[episode.episodeId]?.loading" disabled :index="`scene-loading:${episode.episodeId}`">场次加载中…</el-menu-item>
                <el-menu-item v-else-if="sceneGroups[episode.episodeId]?.error" :index="`retry:${episode.episodeId}`" @click="loadSceneGroup(`episode:${episode.episodeId}`)">加载失败，点击重试</el-menu-item>
                <el-menu-item v-else-if="sceneGroups[episode.episodeId]?.loaded && !sceneGroups[episode.episodeId].rows.length" disabled :index="`empty:${episode.episodeId}`">暂无场次</el-menu-item>
                <el-menu-item v-for="scene in sceneGroups[episode.episodeId]?.rows || []" :key="scene.sceneId" :index="`shots:${episode.episodeId}:${scene.sceneId}`" @click="selectShotScope(episode.episodeId, scene.sceneId)">场 {{ scene.sceneNo }} · {{ scene.sceneName || '未命名' }}</el-menu-item>
              </el-sub-menu>
              <el-menu-item v-if="!catalogLoading && !episodes.length" disabled index="episodes-empty">暂无可选集与场次</el-menu-item>
            </el-sub-menu>
            <el-sub-menu v-else-if="item.routeKey === 'assets' && sessionStore.activeProjectId" index="/assets">
              <template #title><el-icon><Box /></el-icon><span>资产库管理</span></template>
              <el-menu-item index="assets:all" @click="selectAssetType()">全部资产</el-menu-item>
              <el-menu-item v-for="type in [{ value: 'Character', label: '角色' }, { value: 'Environment', label: '场景' }, { value: 'Prop', label: '道具' }]" :key="type.value" :index="`assets:${type.value}`" @click="selectAssetType(type.value)">{{ type.label }}</el-menu-item>
            </el-sub-menu>
            <el-menu-item v-else :index="item.index || item.path" :disabled="!sessionStore.isCreatorWorkspace && item.routeKey !== 'projects' && !sessionStore.activeProjectId" :aria-label="item.title" @click="router.push({ ...moduleLocation(item.path), query: { ...moduleLocation(item.path).query, ...item.query } })">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title><span>{{ item.routeKey === 'projects' ? '全部项目 / 切换项目' : item.title }}</span></template>
            </el-menu-item>
          </template>
        </el-menu>

        <el-empty v-else-if="!collapsed" class="app-navigation__empty" :image-size="42" description="当前账号没有可访问的业务模块" />
        <el-form v-if="showProductionFilters && !collapsed" ref="filterForm" :model="filterDraft" :rules="filterRules" label-position="top" class="workspace-filters" aria-label="制作筛选">
          <el-form-item label="制作人" prop="assigneeUserId"><el-select v-model="filterDraft.assigneeUserId" filterable clearable placeholder="全部制作人" :loading="catalogLoading"><el-option v-for="producer in producers" :key="producer.userId" :value="String(producer.userId)" :label="producer.userName || producer.nickName" /></el-select></el-form-item>
          <el-form-item label="制作周期（预期）" prop="dates"><el-date-picker v-model="filterDraft.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" unlink-panels /></el-form-item>
          <el-form-item><el-button type="primary" :loading="applyingFilters" @click="applyProductionFilters">应用筛选</el-button><el-button :disabled="applyingFilters" @click="resetProductionFilters">重置</el-button></el-form-item>
          <small>按预期制作时间交集筛选；我的任务和提交记录仍保留本人权限范围。</small>
        </el-form>
      </nav>

      <div
        v-show="!collapsed"
        class="app-company-brand"
        :style="companyLogoMaskStyle"
        role="img"
        aria-label="LAPUTTA"
      >
        <span class="app-company-brand__logo" aria-hidden="true"></span>
      </div>
    </el-aside>

    <el-container class="app-stage" direction="vertical">
      <el-header class="app-header" height="auto">
        <div class="app-header__leading">
          <el-tooltip :content="collapsed ? '展开侧边栏' : '收起侧边栏'" placement="bottom" :show-after="350">
            <el-button
              class="app-header__navigation-toggle"
              :icon="collapsed ? Expand : Fold"
              :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
              :aria-expanded="!collapsed"
              aria-controls="shot-grid-navigation"
              @click="collapsed = !collapsed"
            />
          </el-tooltip>
          <div class="app-header__heading">
            <p class="app-header__context">AI 影视短片制作</p>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>
        <div class="app-account">
          <el-tooltip content="使用操作手册（新标签页）" placement="bottom" :show-after="350">
            <el-button tag="a" :href="userManualUrl" target="_blank" rel="noopener noreferrer" :icon="Reading" aria-label="打开使用操作手册（新标签页）">使用手册</el-button>
          </el-tooltip>
          <el-button
            v-if="canUseSearch"
            class="app-search-trigger"
            :icon="Search"
            aria-label="打开全局搜索"
            @click="searchVisible = true"
          >
            搜索 <kbd>Ctrl K</kbd>
          </el-button>
          <el-tooltip v-if="fullscreenSupported" :content="fullscreenLabel" placement="bottom" :show-after="350">
            <el-button
              class="app-fullscreen-toggle"
              text
              circle
              :icon="isFullscreen ? ScaleToOriginal : FullScreen"
              :disabled="fullscreenPending"
              :aria-label="fullscreenLabel"
              :aria-pressed="isFullscreen"
              @click="toggleFullscreen"
            />
          </el-tooltip>
          <ThemeModeSwitch />
          <el-button v-if="desktopVersion" text @click="checkDesktopUpdate">
            {{ collapsed ? `V${desktopVersion} · 检查更新` : '检查更新' }}
          </el-button>
          <el-avatar class="app-account__avatar" :size="32" aria-hidden="true">{{ userDisplayName.slice(0, 1) }}</el-avatar>
          <span class="app-account__name">{{ userDisplayName }}</span>
          <el-button text :icon="SwitchButton" aria-label="退出登录" @click="handleSignOut">
            退出
          </el-button>
        </div>
      </el-header>

      <el-alert v-if="passwordNotice" class="app-security-notice" :title="passwordNotice" type="warning" :closable="false" show-icon />

      <el-main class="app-content">
        <FeedbackNotification />
        <router-view :key="workspaceKey" />
      </el-main>
    </el-container>
    <GlobalSearchDialog v-model="searchVisible" :permissions="sessionStore.permissions" />
  </el-container>
</template>

<style scoped lang="scss">
.app-shell {
  --app-sidebar-width: 180px;
  --app-header-height: 76px;
  min-height: 100vh;
  transition: 180ms ease;
}

.app-shell.is-collapsed {
  --app-sidebar-width: 76px;
}

.app-sidebar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  height: 100vh;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--sg-sidebar-bg);
  // 导航和公司标识共用连续背景，主题色遮罩保证可读。
  background-image:
    linear-gradient(
      to bottom,
      color-mix(in srgb, var(--sg-sidebar-bg) 88%, transparent),
      color-mix(in srgb, var(--sg-sidebar-bg) 65%, transparent)
    ),
    url('../assets/branding/cinematic-sidebar.png');
  background-repeat: no-repeat;
  background-position: center bottom, right bottom;
  background-size: 100% calc(100% - var(--app-header-height)), auto calc(100% - var(--app-header-height));
  border-right: 1px solid var(--sg-border);
  backdrop-filter: blur(18px);
  transition: background-color 180ms ease, border-color 180ms ease;
}

// 顶部共用影棚全景，品牌区选取暖光局部，主栏保留摄影机与冷暖光束。
.app-brand,
.app-header {
  color: #f6f3ee;
  background-color: #080d13;
  background-image:
    linear-gradient(90deg, rgba(5, 9, 14, 0.55), rgba(5, 9, 14, 0.25) 42%, rgba(5, 9, 14, 0.42) 64%, rgba(5, 9, 14, 0.92)),
    url('../assets/branding/cinematic-masthead.webp');
  background-repeat: no-repeat;
  background-position: 0 center;
  background-size: max(100vw, 1280px) auto;
  border-bottom: 1px solid rgba(255, 182, 87, 0.28);
}

.app-brand {
  display: flex;
  height: var(--app-header-height);
  flex: 0 0 auto;
  gap: 13px;
  align-items: center;
  padding: 0 20px;
  background-image:
    linear-gradient(90deg, rgba(5, 9, 14, 0.64), rgba(5, 9, 14, 0.4)),
    url('../assets/branding/cinematic-masthead.webp');
  background-position: center, 19% 34%;
  background-size: 100% 100%, 760px auto;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.65);
}

.app-brand__mark {
  display: flex;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  gap: 3px;
  align-items: flex-end;
  justify-content: center;
  padding: 8px;
  background: var(--sg-accent-surface);
  border-radius: 10px;
  box-shadow: 0 0 22px rgba(255, 173, 72, 0.2);
  transform: rotate(-2deg);
}

.app-brand__mark span {
  width: 4px;
  background: #17130e;
  border-radius: 2px;
}

.app-brand__mark span:nth-child(1) { height: 10px; }
.app-brand__mark span:nth-child(2) { height: 18px; }
.app-brand__mark span:nth-child(3) { height: 14px; }

.app-brand__copy {
  min-width: 0;
}

.app-brand__copy strong,
.app-brand__copy small {
  display: block;
  white-space: nowrap;
}

.app-brand__copy strong {
  font-size: 14px;
  letter-spacing: 0.14em;
}

.app-brand__copy small {
  margin-top: 3px;
  color: #c5cbd3;
  font-size: 10px;
}

.app-navigation {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  padding: 20px 12px;
  overflow-x: hidden;
  overflow-y: auto;
}

.app-shell.is-collapsed .app-navigation {
  padding-inline: 6px;
}

.app-navigation__label {
  margin: 0 10px 10px;
  color: var(--sg-text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.app-navigation__menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--sg-text-secondary);
  --el-menu-hover-bg-color: var(--sg-fill-soft);
  --el-menu-active-color: var(--sg-text);
  border-right: 0;
}

.app-shell.is-collapsed .app-navigation__menu {
  width: 100%;
}

.app-navigation__menu:deep(.el-menu-item) {
  height: 44px;
  margin: 4px 0;
  padding: 0 12px;
  font-size: 13px;
  border: 1px solid transparent;
  border-radius: 10px;
  transition: 150ms ease;
}

.app-shell.is-collapsed .app-navigation__menu:deep(.el-menu-item) {
  justify-content: center;
  padding-inline: 0;
}

.app-navigation__menu:deep(.el-menu-item.is-active) {
  background: var(--sg-accent-soft);
  border-color: rgba(255, 182, 87, 0.15);
}

.app-navigation__menu:deep(.el-menu-item.is-active .el-icon) {
  color: var(--sg-accent);
}

.app-navigation__menu:deep(.el-menu-item .el-icon) {
  flex: 0 0 auto;
  font-size: 18px;
}

.app-navigation__empty {
  padding: 14px 4px;
}

.app-company-brand {
  display: flex;
  height: 56px;
  min-width: 0;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  padding: 10px 20px 12px;
  border-top: 1px solid var(--sg-border);
}

.app-shell.is-collapsed .app-company-brand {
  display: none;
}

.app-company-brand__logo {
  display: block;
  width: 112px;
  height: 25px;
  opacity: 1;
  background-color: var(--sg-text);
  pointer-events: none;
  mask-image: var(--app-company-logo-mask);
  mask-position: center;
  mask-repeat: no-repeat;
  mask-size: contain;
  -webkit-mask-image: var(--app-company-logo-mask);
  -webkit-mask-position: center;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-size: contain;
}

.app-stage {
  min-width: 0;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  height: var(--app-header-height);
  flex: 0 0 auto;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(20px, 3vw, 48px) 0 8px;
  background-position: calc(-1 * var(--app-sidebar-width)) center;
  box-shadow: 0 4px 18px rgba(5, 9, 14, 0.12);
}

.app-header__heading {
  min-width: 0;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.75);
}

.app-header__context {
  margin: 0 0 2px;
  color: #f5c98f;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.app-header h1 {
  margin: 0;
  overflow: hidden;
  font-size: 16px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header__leading {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: center;
}

.app-header__navigation-toggle {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  padding: 0;
  font-size: 19px;
}

.app-account {
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
  align-items: center;
}

// 图片上的操作区固定使用深底亮字，组件仍通过 Element Plus 变量处理交互状态。
.app-header__navigation-toggle,
.app-account > .el-button {
  --el-button-text-color: #e7ebf0;
  --el-button-bg-color: rgba(8, 14, 22, 0.56);
  --el-button-border-color: rgba(221, 231, 242, 0.24);
  --el-button-hover-text-color: #ffffff;
  --el-button-hover-bg-color: rgba(255, 182, 87, 0.17);
  --el-button-hover-border-color: rgba(255, 198, 120, 0.62);
  --el-button-active-text-color: #ffce8d;
  --el-button-active-bg-color: rgba(255, 182, 87, 0.24);
  --el-button-active-border-color: #ffce8d;
  --el-button-disabled-text-color: #8d97a4;
  --el-button-disabled-bg-color: rgba(8, 14, 22, 0.56);
  --el-button-disabled-border-color: rgba(221, 231, 242, 0.12);
}

.app-header__navigation-toggle:focus-visible,
.app-account > .el-button:focus-visible {
  outline: 2px solid #ffce8d;
  outline-offset: 3px;
}

.app-account :deep(.theme-mode-switch) {
  --sg-theme-switch-track: #29323d;
  --sg-theme-switch-border: #637080;
  --sg-theme-switch-action: #f3e9d9;
  --sg-theme-switch-icon: #493216;
  --sg-theme-switch-shadow: 0 1px 6px rgba(0, 0, 0, 0.25);
}

.app-fullscreen-toggle {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  padding: 0;
}

.app-search-trigger {
  backdrop-filter: blur(10px);
}

.app-search-trigger kbd {
  margin-left: 8px;
  padding: 1px 5px;
  color: #c5cbd3;
  font-family: inherit;
  font-size: 10px;
  background: rgba(230, 236, 244, 0.08);
  border: 1px solid rgba(221, 231, 242, 0.2);
  border-radius: 4px;
}

.app-account__avatar {
  color: #17130e;
  font-size: 13px;
  font-weight: 700;
  background: var(--sg-accent-surface);
}

.app-account__name {
  color: #e7ebf0;
  font-size: 13px;
}

.app-content {
  min-height: calc(100vh - var(--app-header-height));
  padding: 0;
  // 页面使用整页滚动，避免 ElMain 默认 overflow: auto 让 Affix 监听错误容器。
  overflow: visible;
}

.app-security-notice {
  margin: 0;
  background: rgba(255, 182, 87, 0.08);
  border-bottom: 1px solid rgba(255, 182, 87, 0.18);
  border-radius: 0;
}

.app-security-notice:deep(.el-alert__content) {
  padding: 0 clamp(12px, 2vw, 28px);
}

@media (min-width: 821px) {
  .app-shell:not(.is-collapsed) .app-brand {
    gap: 8px;
    padding-inline: 12px;
  }
}

@media (max-width: 820px) {
  .app-shell.is-collapsed {
    --app-sidebar-width: 68px;
  }

  .app-brand {
    padding: 0 16px;
  }

  .app-shell.is-collapsed .app-brand__copy,
  .app-shell.is-collapsed .app-navigation__label,
  .app-shell.is-collapsed .app-navigation__empty,
  .app-shell.is-collapsed .app-company-brand,
  .app-account__name {
    display: none;
  }

  .app-search-trigger kbd { display: none; }

  .app-shell.is-collapsed .app-navigation__menu:deep(.el-menu-item) {
    justify-content: center;
    padding: 0;
  }

  .app-shell.is-collapsed .app-navigation__menu:deep(.el-menu-item > span) {
    display: none;
  }

}

@media (max-width: 560px) {
  .app-shell {
    --app-header-height: 68px;
  }

  .app-header {
    gap: 8px;
    padding: 0 12px 0 8px;
  }

  .app-header__leading {
    gap: 8px;
  }

  .app-account {
    gap: 6px;
  }

  .app-account > .el-button {
    width: 32px;
    flex: 0 0 32px;
    margin-left: 0;
    padding: 0;
  }

  .app-header__context,
  .app-account :deep(.el-button > span) {
    display: none;
  }
}
</style>

<style scoped>
.workspace-filters { padding: 16px 12px; border-top: 1px solid var(--sg-border); }
.workspace-filters :deep(.el-select), .workspace-filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
.workspace-filters :deep(.el-range-input) { font-size: 12px; }
.workspace-filters small { color: var(--sg-text-muted); line-height: 1.6; }
.app-navigation__label { white-space: normal; overflow-wrap: anywhere; }
</style>
