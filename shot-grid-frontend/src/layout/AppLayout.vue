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
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside class="app-sidebar" aria-label="Shot Grid 主导航">
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
        <router-link
          v-for="item in navigationItems"
          :key="item.routeKey"
          :to="item.path"
          class="app-navigation__item"
          :aria-label="item.title"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span v-show="!collapsed">{{ item.title }}</span>
        </router-link>

        <p v-if="navigationItems.length === 0 && !collapsed" class="app-navigation__empty">
          当前账号没有可访问的业务模块
        </p>
      </nav>

      <button
        class="app-sidebar__toggle"
        type="button"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="collapsed = !collapsed"
      >
        <el-icon>
          <ArrowRightBold v-if="collapsed" />
          <ArrowLeftBold v-else />
        </el-icon>
        <span v-show="!collapsed">收起导航</span>
      </button>
    </aside>

    <section class="app-stage">
      <header class="app-header">
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
          <span class="app-account__avatar" aria-hidden="true">{{ userDisplayName.slice(0, 1) }}</span>
          <span class="app-account__name">{{ userDisplayName }}</span>
          <el-button text :icon="SwitchButton" aria-label="退出登录" @click="handleSignOut">
            退出
          </el-button>
        </div>
      </header>

      <p v-if="passwordNotice" class="app-security-notice" role="status">{{ passwordNotice }}</p>

      <main class="app-content">
        <router-view />
      </main>
    </section>
    <GlobalSearchDialog v-model="searchVisible" :permissions="sessionStore.permissions" />
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 244px minmax(0, 1fr);
  transition: grid-template-columns 180ms ease;
}

.app-shell.is-collapsed {
  grid-template-columns: 76px minmax(0, 1fr);
}

.app-sidebar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  height: 100vh;
  min-width: 0;
  flex-direction: column;
  background: rgba(13, 16, 21, 0.94);
  border-right: 1px solid var(--sg-border);
  backdrop-filter: blur(18px);
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
  background: var(--sg-accent);
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

.app-navigation__item {
  display: flex;
  height: 44px;
  gap: 12px;
  align-items: center;
  margin: 4px 0;
  padding: 0 12px;
  color: var(--sg-text-secondary);
  font-size: 13px;
  border: 1px solid transparent;
  border-radius: 10px;
  transition: 150ms ease;
}

.app-navigation__item:hover {
  color: var(--sg-text);
  background: rgba(255, 255, 255, 0.045);
}

.app-navigation__item.router-link-active {
  color: var(--sg-text);
  background: var(--sg-accent-soft);
  border-color: rgba(255, 182, 87, 0.15);
}

.app-navigation__item.router-link-active .el-icon {
  color: var(--sg-accent);
}

.app-navigation__item .el-icon {
  flex: 0 0 auto;
  font-size: 18px;
}

.app-navigation__empty {
  margin: 14px 10px;
  color: var(--sg-text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.app-sidebar__toggle {
  display: flex;
  height: 58px;
  gap: 10px;
  align-items: center;
  margin-top: auto;
  padding: 0 24px;
  color: var(--sg-text-muted);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--sg-border);
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
  background: rgba(9, 11, 15, 0.82);
  border-bottom: 1px solid var(--sg-border);
  backdrop-filter: blur(18px);
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
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--sg-border);
  border-radius: 4px;
}

.app-account__avatar {
  display: grid;
  width: 32px;
  height: 32px;
  color: #17130e;
  font-size: 13px;
  font-weight: 700;
  background: var(--sg-accent);
  border-radius: 50%;
  place-items: center;
}

.app-account__name {
  color: var(--sg-text-secondary);
  font-size: 13px;
}

.app-content {
  min-height: calc(100vh - 76px);
}

.app-security-notice {
  margin: 0;
  padding: 10px clamp(20px, 3vw, 48px);
  color: #ffd49b;
  font-size: 12px;
  background: rgba(255, 182, 87, 0.08);
  border-bottom: 1px solid rgba(255, 182, 87, 0.18);
}

@media (max-width: 820px) {
  .app-shell,
  .app-shell.is-collapsed {
    grid-template-columns: 68px minmax(0, 1fr);
  }

  .app-brand {
    padding: 0 16px;
  }

  .app-brand__copy,
  .app-navigation__label,
  .app-navigation__item span,
  .app-navigation__empty,
  .app-sidebar__toggle span,
  .app-account__name {
    display: none;
  }

  .app-search-trigger kbd { display: none; }

  .app-navigation__item {
    justify-content: center;
    padding: 0;
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
