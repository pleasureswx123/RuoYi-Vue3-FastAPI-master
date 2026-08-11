<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Collection, Film, FolderOpened, Right, Tickets } from '@element-plus/icons-vue'

import { useSessionStore } from '@/store/modules/session'

const router = useRouter()
const sessionStore = useSessionStore()

const moduleRegistry = Object.freeze({
  projects: { title: '项目', path: '/projects', icon: Collection, description: '管理项目资料与项目成员' },
  shots: { title: '镜头管理', path: '/shots', icon: Film, description: '进入镜头生产与任务视图' },
  assets: { title: '资产库管理', path: '/assets', icon: Box, description: '查看角色、场景与道具资产' },
  reviews: { title: '版本审核', path: '/reviews', icon: Tickets, description: '处理版本反馈与审核动作' },
  files: { title: '文件与 NAS', path: '/files', icon: FolderOpened, description: '查看业务文件和存储状态' }
})

const availableModules = computed(() => {
  const navigation = Array.isArray(sessionStore.navigation) ? sessionStore.navigation : []
  return navigation
    .map((item, index) => {
      if (!Object.hasOwn(moduleRegistry, item?.routeKey)) return null
      const module = moduleRegistry[item?.routeKey]
      return { ...module, routeKey: item.routeKey, orderNum: Number(item.orderNum ?? index) }
    })
    .filter(Boolean)
    .sort((left, right) => left.orderNum - right.orderNum)
})

const displayName = computed(
  () => sessionStore.user?.nickName || sessionStore.user?.userName || '制作成员'
)
</script>

<template>
  <section class="sg-page workbench-page">
    <div class="workbench-hero">
      <div>
        <p class="sg-eyebrow">PRODUCTION DESK</p>
        <h2>你好，{{ displayName }}</h2>
        <p>这里仅展示当前账号由后端授权的业务入口。项目进度与待办数据将在对应真实接口接入后呈现。</p>
      </div>
      <span class="workbench-hero__label">当前工作区</span>
    </div>

    <div class="workbench-section-heading">
      <div>
        <h3>可访问模块</h3>
        <p>权限来自 Shot Grid 业务导航，不加载系统管理菜单。</p>
      </div>
    </div>

    <div v-if="availableModules.length" class="module-grid">
      <button
        v-for="item in availableModules"
        :key="item.routeKey"
        class="module-card"
        type="button"
        @click="router.push(item.path)"
      >
        <span class="module-card__icon"><el-icon><component :is="item.icon" /></el-icon></span>
        <span class="module-card__copy">
          <strong>{{ item.title }}</strong>
          <small>{{ item.description }}</small>
        </span>
        <el-icon class="module-card__arrow"><Right /></el-icon>
      </button>
    </div>

    <div v-else class="workbench-empty">
      当前账号没有可访问的业务模块，请联系管理员核对权限配置。
    </div>
  </section>
</template>

<style scoped lang="scss">
.workbench-hero {
  position: relative;
  display: flex;
  min-height: 240px;
  align-items: flex-end;
  justify-content: space-between;
  padding: clamp(30px, 5vw, 58px);
  overflow: hidden;
  background:
    radial-gradient(circle at 86% 12%, rgba(255, 182, 87, 0.24), transparent 28%),
    linear-gradient(135deg, #1c222c, #101319 72%);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-lg);
  box-shadow: var(--sg-shadow);
}

.workbench-hero::after {
  position: absolute;
  top: -80px;
  right: -10px;
  width: 310px;
  height: 310px;
  content: '';
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 50%;
}

.workbench-hero > div {
  position: relative;
  z-index: 1;
  max-width: 760px;
}

.workbench-hero h2 {
  margin: 0;
  font-size: clamp(30px, 4vw, 48px);
  font-weight: 600;
  letter-spacing: -0.045em;
}

.workbench-hero p:not(.sg-eyebrow) {
  max-width: 650px;
  margin: 16px 0 0;
  color: var(--sg-text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.workbench-hero__label {
  position: relative;
  z-index: 1;
  padding: 7px 11px;
  color: var(--sg-text-secondary);
  font-size: 11px;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid var(--sg-border);
  border-radius: 999px;
}

.workbench-section-heading {
  margin: 38px 0 18px;
}

.workbench-section-heading h3 {
  margin: 0;
  font-size: 18px;
}

.workbench-section-heading p {
  margin: 7px 0 0;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.module-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.module-card {
  display: grid;
  min-height: 122px;
  padding: 22px;
  color: var(--sg-text);
  text-align: left;
  cursor: pointer;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
  grid-template-columns: 42px minmax(0, 1fr) auto;
  gap: 15px;
  align-items: center;
  transition: 160ms ease;
}

.module-card:hover {
  background: var(--sg-surface-raised);
  border-color: rgba(255, 182, 87, 0.3);
  transform: translateY(-2px);
}

.module-card__icon {
  display: grid;
  width: 42px;
  height: 42px;
  color: var(--sg-accent);
  background: var(--sg-accent-soft);
  border-radius: 12px;
  place-items: center;
}

.module-card__icon .el-icon { font-size: 20px; }
.module-card__copy strong,
.module-card__copy small { display: block; }
.module-card__copy strong { font-size: 14px; }
.module-card__copy small { margin-top: 7px; color: var(--sg-text-muted); font-size: 11px; line-height: 1.6; }
.module-card__arrow { color: var(--sg-text-muted); }

.workbench-empty {
  padding: 40px;
  color: var(--sg-text-secondary);
  text-align: center;
  background: var(--sg-surface);
  border: 1px dashed var(--sg-border-strong);
  border-radius: var(--sg-radius-md);
}

@media (max-width: 1100px) {
  .module-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 680px) {
  .module-grid { grid-template-columns: 1fr; }
  .workbench-hero__label { display: none; }
}
</style>
