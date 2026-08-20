<template>
  <main class="platform-home">
    <section class="welcome-panel" aria-labelledby="platform-home-title">
      <div class="welcome-panel__identity">
        <el-avatar
          :size="72"
          :src="userStore.avatar"
          :alt="`${displayName}的头像`"
          class="welcome-panel__avatar"
        >
          <el-icon><UserFilled /></el-icon>
        </el-avatar>

        <div class="welcome-panel__content">
          <p class="welcome-panel__eyebrow">SHOT GRID ADMINISTRATION</p>
          <h1 id="platform-home-title">{{ greeting }}，{{ displayName }}</h1>
          <p class="welcome-panel__description">
            在这里维护 Shot Grid 的账号权限、存储资源和平台运行状态，只展示当前账号可使用的管理入口。
          </p>
          <div class="welcome-panel__roles" aria-label="当前账号角色">
            <span class="welcome-panel__roles-label">当前身份</span>
            <el-tag
              v-for="role in displayRoles"
              :key="role.key"
              :type="role.type"
              effect="plain"
              round
            >
              {{ role.label }}
            </el-tag>
            <el-tag v-if="displayRoles.length === 0" type="info" effect="plain" round>
              已登录用户
            </el-tag>
          </div>
        </div>
      </div>

      <el-button type="primary" plain :icon="User" @click="openPage('/user/profile')">
        个人中心
      </el-button>
    </section>

    <el-row :gutter="20" class="home-layout">
      <el-col :xs="24" :lg="16">
        <el-card class="home-card navigation-card" shadow="never">
          <template #header>
            <div class="card-heading">
              <div>
                <p class="card-heading__eyebrow">MANAGEMENT</p>
                <h2>管理工作台</h2>
              </div>
            </div>
          </template>

          <div v-if="accessibleEntries.length" class="navigation-grid">
            <article v-for="entry in accessibleEntries" :key="entry.path" class="navigation-item">
              <div class="navigation-item__icon" aria-hidden="true">
                <el-icon><component :is="entry.icon" /></el-icon>
              </div>
              <div class="navigation-item__body">
                <h3>{{ entry.title }}</h3>
                <p>{{ entry.description }}</p>
                <el-button
                  link
                  type="primary"
                  :icon="ArrowRight"
                  @click="openPage(entry.path)"
                >
                  进入管理
                </el-button>
              </div>
            </article>
          </div>

          <el-empty
            v-else
            :image-size="88"
            description="当前账号暂无可用的管理入口，请联系超级管理员配置角色与菜单权限。"
          />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="home-card responsibility-card" shadow="never">
          <template #header>
            <div class="card-heading">
              <div>
                <p class="card-heading__eyebrow">RESPONSIBILITIES</p>
                <h2>平台治理职责</h2>
              </div>
            </div>
          </template>

          <el-timeline>
            <el-timeline-item
              v-for="item in responsibilities"
              :key="item.title"
              :type="item.type"
              :hollow="true"
            >
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-alert
          class="permission-alert"
          title="权限边界说明"
          type="info"
          :closable="false"
          show-icon
        >
          <template #default>
            具体数据和可执行操作以当前账号的授权范围为准；如需调整，请联系平台超级管理员。
          </template>
        </el-alert>
      </el-col>
    </el-row>
  </main>
</template>

<script setup>
import {
  ArrowRight,
  Connection,
  Document,
  FolderOpened,
  Key,
  Menu,
  Monitor,
  SetUp,
  Tickets,
  User,
  UserFilled
} from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import usePermissionStore from '@/store/modules/permission'

defineOptions({
  name: 'DashBoard'
})

const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()

const roleMeta = {
  admin: { label: '平台超级管理员', type: 'danger' },
  shotgrid_platform_admin: { label: 'Shot Grid 平台管理员', type: 'warning' },
  shotgrid_admin: { label: '项目管理人', type: 'primary' },
  shotgrid_creator: { label: '制作人员', type: 'success' }
}

const managementEntries = [
  {
    title: '用户管理',
    description: '维护平台账号、部门归属、状态和基础资料。',
    path: '/system/user',
    permission: 'system:user:list',
    icon: User
  },
  {
    title: '角色管理',
    description: '配置角色的数据范围、菜单权限和用户关联。',
    path: '/system/role',
    permission: 'system:role:list',
    icon: Key
  },
  {
    title: '菜单权限',
    description: '维护管理端菜单、接口权限字符和路由入口。',
    path: '/system/menu',
    permission: 'system:menu:list',
    icon: Menu
  },
  {
    title: 'NAS 根目录',
    description: '维护 Shot Grid 可选存储根目录并执行可达性探测。',
    path: '/system/nas',
    permission: 'shotgrid:storageRoot:query',
    icon: FolderOpened
  },
  {
    title: '文件管理',
    description: '查看受保护文件、业务引用、保留策略和存储状态。',
    path: '/system/file',
    permission: 'system:file:list',
    icon: Document
  },
  {
    title: '插件管理',
    description: '检查插件状态、依赖、配置以及生命周期计划。',
    path: '/system/plugin',
    permission: 'system:plugin:list',
    icon: SetUp
  },
  {
    title: '在线用户',
    description: '查看当前在线会话并处理异常登录状态。',
    path: '/monitor/online',
    permission: 'monitor:online:list',
    icon: Connection
  },
  {
    title: '服务监控',
    description: '查看服务器、运行环境和资源使用情况。',
    path: '/monitor/server',
    permission: 'monitor:server:list',
    icon: Monitor
  },
  {
    title: '操作日志',
    description: '追踪平台管理操作，辅助安全审计和问题定位。',
    path: '/system/log/operlog',
    permission: 'monitor:operlog:list',
    icon: Tickets
  }
]

const responsibilities = [
  {
    title: '账号与授权',
    description: '保持用户、角色、菜单和数据范围一致，遵循最小授权原则。',
    type: 'primary'
  },
  {
    title: '存储与文件治理',
    description: '维护 NAS 根目录可用性，关注文件引用、访问控制和保留策略。',
    type: 'warning'
  },
  {
    title: '运行与安全审计',
    description: '通过在线会话、服务状态和操作日志及时发现平台异常。',
    type: 'success'
  }
]

const displayName = computed(() => userStore.nickName || userStore.name || '管理员')

const greeting = '欢迎回来'

const displayRoles = computed(() => {
  return (userStore.roles || []).map((role) => ({
    key: role,
    ...(roleMeta[role] || { label: role, type: 'info' })
  }))
})

const accessibleEntries = computed(() => {
  const permissions = userStore.permissions || []
  const isSuperAdmin = permissions.includes('*:*:*')
  return managementEntries.filter((entry) => {
    const hasPermission = isSuperAdmin || permissions.includes(entry.permission)
    return hasPermission && hasRegisteredRoute(permissionStore.routes, entry.path)
  })
})

function normalizeRoutePath(parentPath, routePath) {
  if (routePath.startsWith('/')) return routePath.replace(/\/+$/, '') || '/'
  return `${parentPath}/${routePath}`.replace(/\/{2,}/g, '/').replace(/\/+$/, '') || '/'
}

function hasRegisteredRoute(routes, targetPath, parentPath = '') {
  return (routes || []).some((route) => {
    if (!route?.path || route.path.includes(':pathMatch')) return false

    const currentPath = normalizeRoutePath(parentPath, route.path)
    if (currentPath === targetPath) return true
    return hasRegisteredRoute(route.children, targetPath, currentPath)
  })
}

function openPage(path) {
  router.push(path)
}
</script>

<style scoped lang="scss">
.platform-home {
  min-height: 100%;
  padding: 24px;
  background:
    radial-gradient(circle at 88% 0%, color-mix(in srgb, var(--el-color-primary) 9%, transparent), transparent 34%),
    var(--el-bg-color-page);
}

.welcome-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 30px;
  margin-bottom: 20px;
  overflow: hidden;
  background:
    linear-gradient(120deg, color-mix(in srgb, var(--el-color-primary) 10%, var(--el-bg-color-overlay)), var(--el-bg-color-overlay) 55%),
    var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  box-shadow: var(--el-box-shadow-light);
}

.welcome-panel__identity {
  display: flex;
  align-items: center;
  min-width: 0;
}

.welcome-panel__avatar {
  flex: 0 0 auto;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border: 2px solid color-mix(in srgb, var(--el-color-primary) 28%, transparent);

  .el-icon {
    font-size: 32px;
  }
}

.welcome-panel__content {
  min-width: 0;
  margin-left: 22px;

  h1 {
    margin: 2px 0 8px;
    color: var(--el-text-color-primary);
    font-size: clamp(24px, 3vw, 34px);
    line-height: 1.3;
  }
}

.welcome-panel__eyebrow,
.card-heading__eyebrow {
  margin: 0;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.13em;
}

.welcome-panel__description {
  max-width: 760px;
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.8;
}

.welcome-panel__roles {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.welcome-panel__roles-label {
  margin-right: 2px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.home-layout > .el-col {
  margin-bottom: 20px;
}

.home-card {
  height: 100%;
  border-radius: 12px;

  :deep(.el-card__header) {
    padding: 20px 22px 16px;
  }

  :deep(.el-card__body) {
    padding: 20px 22px 22px;
  }
}

.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  h2 {
    margin: 4px 0 0;
    color: var(--el-text-color-primary);
    font-size: 19px;
  }
}

.navigation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.navigation-item {
  display: flex;
  gap: 14px;
  min-width: 0;
  padding: 17px;
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;

  &:hover {
    border-color: color-mix(in srgb, var(--el-color-primary) 45%, var(--el-border-color));
    box-shadow: var(--el-box-shadow-lighter);
    transform: translateY(-1px);
  }
}

.navigation-item__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 42px;
  width: 42px;
  height: 42px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 10px;

  .el-icon {
    font-size: 22px;
  }
}

.navigation-item__body {
  min-width: 0;

  h3 {
    margin: 0 0 6px;
    color: var(--el-text-color-primary);
    font-size: 16px;
  }

  p {
    min-height: 44px;
    margin: 0 0 6px;
    color: var(--el-text-color-secondary);
    font-size: 13px;
    line-height: 1.65;
  }

  .el-button {
    padding: 0;
  }
}

.responsibility-card {
  height: auto;
  margin-bottom: 20px;

  :deep(.el-timeline) {
    padding-left: 3px;
  }

  :deep(.el-timeline-item:last-child) {
    padding-bottom: 0;
  }

  h3 {
    margin: 0 0 6px;
    color: var(--el-text-color-primary);
    font-size: 15px;
  }

  p {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 13px;
    line-height: 1.7;
  }
}

.permission-alert {
  align-items: flex-start;
  border: 1px solid var(--el-color-info-light-7);

  :deep(.el-alert__description) {
    line-height: 1.65;
  }
}

@media (max-width: 1100px) {
  .navigation-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .platform-home {
    padding: 14px;
  }

  .welcome-panel {
    align-items: stretch;
    flex-direction: column;
    padding: 22px 20px;
  }

  .welcome-panel__identity {
    align-items: flex-start;
  }

  .welcome-panel__avatar {
    width: 56px;
    height: 56px;
  }

  .welcome-panel__content {
    margin-left: 14px;
  }
}

@media (max-width: 480px) {
  .welcome-panel__avatar {
    display: none;
  }

  .welcome-panel__content {
    margin-left: 0;
  }

  .navigation-item {
    padding: 14px;
  }
}
</style>
