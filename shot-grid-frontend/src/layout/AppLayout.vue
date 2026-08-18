<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Box,
  Collection,
  Film,
  FolderOpened,
  Grid,
  Search,
  SwitchButton,
  Tickets
} from '@element-plus/icons-vue'

import { useSessionStore } from '@/store/modules/session'
import GlobalSearchDialog from '@/components/search/GlobalSearchDialog.vue'
import ThemeModeSwitch from '@/components/theme/ThemeModeSwitch.vue'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const collapsed = ref(false)
const searchVisible = ref(false)

const localNavigation = Object.freeze({
  workbench: { title: '工作台', path: '/workbench', icon: Grid },
  projects: { title: '项目', path: '/projects', icon: Collection },
  shots: { title: '镜头管理', path: '/shots', icon: Film },
  assets: { title: '资产库管理', path: '/assets', icon: Box },
  reviews: { title: '版本审核', path: '/reviews', icon: Tickets },
  files: { title: '文件与 NAS', path: '/files', icon: FolderOpened }
})

const navigationItems = computed(() => {
  const serverItems = Array.isArray(sessionStore.navigation) ? sessionStore.navigation : []

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
    .sort((left, right) => left.orderNum - right.orderNum)
})

const userDisplayName = computed(
  () => sessionStore.user?.nickName || sessionStore.user?.userName || '当前用户'
)

const pageTitle = computed(() => route.meta?.title || 'Shot Grid')
const activeNavigationPath = computed(() => {
  const routeKey = route.meta?.routeKey
  const matchedByKey = navigationItems.value.find(item => item.routeKey === routeKey)
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

onMounted(() => window.addEventListener('keydown', handleSearchShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', handleSearchShortcut))
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
          <small>影视制作协作平台</small>
        </span>
      </div>

      <nav class="app-navigation">
        <p v-show="!collapsed" class="app-navigation__label">制作工作区</p>
        <el-menu
          v-if="navigationItems.length"
          class="app-navigation__menu"
          router
          :collapse="collapsed"
          :collapse-transition="false"
          :default-active="activeNavigationPath"
        >
          <el-menu-item
            v-for="item in navigationItems"
            :key="item.routeKey"
            :index="item.path"
            :route="{ path: item.path }"
            :aria-label="item.title"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.title }}</template>
          </el-menu-item>
        </el-menu>

        <el-empty v-else-if="!collapsed" class="app-navigation__empty" :image-size="42" description="当前账号没有可访问的业务模块" />
      </nav>

      <el-button
        class="app-sidebar__toggle"
        text
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="collapsed = !collapsed"
      >
        <el-icon>
          <ArrowRightBold v-if="collapsed" />
          <ArrowLeftBold v-else />
        </el-icon>
        <span v-show="!collapsed">收起导航</span>
      </el-button>
    </el-aside>

    <el-container class="app-stage" direction="vertical">
      <el-header class="app-header" height="auto">
        <div>
          <p class="app-header__context">AI 影视短片制作</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="app-account">
          <el-button
            v-if="canUseSearch"
            class="app-search-trigger"
            :icon="Search"
            aria-label="打开全局搜索"
            @click="searchVisible = true"
          >
            搜索 <kbd>Ctrl K</kbd>
          </el-button>
          <ThemeModeSwitch />
          <el-avatar class="app-account__avatar" :size="32" aria-hidden="true">{{ userDisplayName.slice(0, 1) }}</el-avatar>
          <span class="app-account__name">{{ userDisplayName }}</span>
          <el-button text :icon="SwitchButton" aria-label="退出登录" @click="handleSignOut">
            退出
          </el-button>
        </div>
      </el-header>

      <el-alert v-if="passwordNotice" class="app-security-notice" :title="passwordNotice" type="warning" :closable="false" show-icon />

      <el-main class="app-content">
        <router-view />
      </el-main>
    </el-container>
    <GlobalSearchDialog v-model="searchVisible" :permissions="sessionStore.permissions" />
  </el-container>
</template>

<style scoped lang="scss">
.app-shell {
  --app-sidebar-width: 244px;
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
  background: var(--sg-sidebar-bg);
  border-right: 1px solid var(--sg-border);
  backdrop-filter: blur(18px);
  transition: background-color 180ms ease, border-color 180ms ease;
}

.app-brand {
  display: flex;
  height: 76px;
  gap: 13px;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid var(--sg-border);
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
  color: var(--sg-text-muted);
  font-size: 10px;
}

.app-navigation {
  min-height: 0;
  padding: 20px 12px;
  overflow-y: auto;
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

.app-navigation__menu:deep(.el-menu-item) {
  height: 44px;
  margin: 4px 0;
  padding: 0 12px;
  font-size: 13px;
  border: 1px solid transparent;
  border-radius: 10px;
  transition: 150ms ease;
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

.app-sidebar__toggle {
  width: 100%;
  height: 58px;
  gap: 10px;
  justify-content: flex-start;
  margin: auto 0 0;
  padding: 0 24px;
  color: var(--sg-text-muted);
  border-top: 1px solid var(--sg-border);
  border-radius: 0;
}

.app-sidebar__toggle:hover {
  color: var(--sg-text);
}

.app-stage {
  min-width: 0;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  height: 76px;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(20px, 3vw, 48px);
  background: var(--sg-header-bg);
  border-bottom: 1px solid var(--sg-border);
  backdrop-filter: blur(18px);
  transition: background-color 180ms ease, border-color 180ms ease;
}

.app-header__context {
  margin: 0 0 2px;
  color: var(--sg-text-muted);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.app-header h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.app-account {
  display: flex;
  gap: 10px;
  align-items: center;
}

.app-search-trigger kbd {
  margin-left: 8px;
  padding: 1px 5px;
  color: var(--sg-text-muted);
  font-family: inherit;
  font-size: 10px;
  background: var(--sg-fill-soft);
  border: 1px solid var(--sg-border);
  border-radius: 4px;
}

.app-account__avatar {
  color: #17130e;
  font-size: 13px;
  font-weight: 700;
  background: var(--sg-accent-surface);
}

.app-account__name {
  color: var(--sg-text-secondary);
  font-size: 13px;
}

.app-content {
  min-height: calc(100vh - 76px);
  padding: 0;
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

@media (max-width: 820px) {
  .app-shell,
  .app-shell.is-collapsed {
    --app-sidebar-width: 68px;
  }

  .app-brand {
    padding: 0 16px;
  }

  .app-brand__copy,
  .app-navigation__label,
  .app-navigation__empty,
  .app-sidebar__toggle span,
  .app-account__name {
    display: none;
  }

  .app-search-trigger kbd { display: none; }

  .app-navigation__menu:deep(.el-menu-item) {
    justify-content: center;
    padding: 0;
  }

  .app-navigation__menu:deep(.el-menu-item > span) {
    display: none;
  }

  .app-sidebar__toggle {
    justify-content: center;
    padding: 0;
  }
}

@media (max-width: 560px) {
  .app-header {
    height: 68px;
    padding: 0 16px;
  }

  .app-header__context,
  .app-account .el-button:not(.app-search-trigger) span,
  .app-search-trigger span {
    display: none;
  }

  .app-content {
    min-height: calc(100vh - 68px);
  }
}
</style>
