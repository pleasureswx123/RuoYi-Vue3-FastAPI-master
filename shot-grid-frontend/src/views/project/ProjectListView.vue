<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, Plus, Refresh, Search } from '@element-plus/icons-vue'

import { getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectCreateDialog from '@/views/project/components/ProjectCreateDialog.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import {
  formatDuration,
  phaseLabel,
  projectErrorState,
  statusMeta,
  storageMeta
} from '@/views/project/projectPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const total = ref(0)
const hasNext = ref(false)
const loading = ref(false)
const errorState = ref(null)
const showCreate = ref(false)
const query = reactive({
  keyword: '',
  projectStatus: '',
  scope: '',
  pageNum: 1,
  pageSize: 12,
  orderByColumn: 'createTime',
  isAsc: 'descending'
})
let activeController = null

const hasWildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const canCreate = computed(
  () => hasWildcard.value || sessionStore.permissions.includes('shotgrid:project:add')
)
const canViewAll = computed(
  () => hasWildcard.value || sessionStore.permissions.includes('shotgrid:project:all')
)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))

async function loadProjects() {
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  errorState.value = null
  try {
    const response = await getProjectPage(
      {
        ...query,
        projectStatus: query.projectStatus || undefined,
        scope: query.scope || undefined
      },
      { signal: controller.signal }
    )
    projects.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
    hasNext.value = Boolean(response.hasNext)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      projects.value = []
      total.value = 0
      errorState.value = projectErrorState(error, '项目列表加载失败')
    }
  } finally {
    if (activeController === controller) loading.value = false
  }
}

function submitFilters() {
  query.pageNum = 1
  loadProjects()
}

function changePage(nextPage) {
  if (nextPage < 1 || nextPage > pageCount.value || nextPage === query.pageNum) return
  query.pageNum = nextPage
  loadProjects()
}

async function openProject(projectId) {
  await router.push(`/projects/${projectId}/overview`)
}

async function handleCreated(result) {
  showCreate.value = false
  ElMessage.success('项目已受理，NAS 目录正在初始化')
  await router.push(`/projects/${result.projectId}/overview`)
}

onMounted(loadProjects)
onBeforeUnmount(() => activeController?.abort())
</script>

<template>
  <section class="sg-page project-page">
    <header class="sg-page-heading">
      <div>
        <p class="sg-eyebrow">PROJECTS</p>
        <h2 class="sg-page-title">项目</h2>
        <p class="sg-page-description">仅展示当前账号项目成员范围内的数据；具备跨项目权限时可显式切换全部范围。</p>
      </div>
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="showCreate = true">创建项目</el-button>
    </header>

    <form class="project-filters" aria-label="项目筛选" @submit.prevent="submitFilters">
      <label class="project-search">
        <el-icon><Search /></el-icon>
        <input v-model="query.keyword" maxlength="200" placeholder="搜索项目名称或代号" />
      </label>
      <select v-model="query.projectStatus" aria-label="项目状态">
        <option value="">全部状态</option>
        <option value="preparing">准备中</option>
        <option value="active">进行中</option>
        <option value="completed">已完成</option>
        <option value="archived">已归档</option>
      </select>
      <select v-if="canViewAll" v-model="query.scope" aria-label="项目范围">
        <option value="">我的项目</option>
        <option value="all">全部项目</option>
      </select>
      <select v-model="query.orderByColumn" aria-label="排序字段">
        <option value="createTime">创建时间</option>
        <option value="projectCode">项目代号</option>
        <option value="projectName">项目名称</option>
        <option value="deliveryDate">交付日期</option>
      </select>
      <select v-model="query.isAsc" aria-label="排序方向">
        <option value="descending">降序</option>
        <option value="ascending">升序</option>
      </select>
      <el-button native-type="submit" :loading="loading">查询</el-button>
      <el-button :icon="Refresh" circle aria-label="刷新项目列表" :disabled="loading" @click="loadProjects" />
    </form>

    <ProjectStatePanel
      v-if="errorState"
      :title="errorState.title"
      :message="errorState.message"
      :retryable="errorState.retryable"
      @retry="loadProjects"
    />

    <div v-else-if="loading && projects.length === 0" class="project-grid" aria-label="项目加载中">
      <div v-for="index in 6" :key="index" class="project-card project-card--skeleton"></div>
    </div>

    <section v-else-if="projects.length === 0" class="project-empty">
      <span class="project-empty__icon"><el-icon><Collection /></el-icon></span>
      <h3>当前范围暂无项目</h3>
      <p>可以调整筛选条件，或由具备权限的项目总监创建第一个项目。</p>
      <el-button v-if="canCreate" type="primary" @click="showCreate = true">创建项目</el-button>
    </section>

    <template v-else>
      <div class="project-summary">
        <span>共 {{ total }} 个项目</span>
        <span v-if="loading">正在刷新…</span>
      </div>
      <div class="project-grid" :class="{ 'is-refreshing': loading }">
        <article
          v-for="project in projects"
          :key="project.projectId"
          class="project-card"
          tabindex="0"
          @click="openProject(project.projectId)"
          @keydown.enter="openProject(project.projectId)"
        >
          <header>
            <span class="project-card__code">{{ project.projectCode }}</span>
            <span class="status-chip" :data-tone="statusMeta(project.projectStatus).tone">
              {{ statusMeta(project.projectStatus).label }}
            </span>
          </header>
          <div class="project-card__title-row">
            <div>
              <h3>{{ project.projectName }}</h3>
              <p>{{ project.projectTypeName }} · {{ project.aspectRatio }}</p>
            </div>
            <span class="project-card__role">{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</span>
          </div>
          <div class="project-card__storage">
            <span class="status-dot" :data-tone="storageMeta(project.storageStatus).tone"></span>
            {{ storageMeta(project.storageStatus).label }}
          </div>
          <dl class="project-card__metrics">
            <div><dt>阶段</dt><dd>{{ phaseLabel(project.currentPhase) }}</dd></div>
            <div><dt>镜头</dt><dd>{{ project.completedShots }}/{{ project.totalShots }}</dd></div>
            <div><dt>资产</dt><dd>{{ project.completedAssets }}/{{ project.totalAssets }}</dd></div>
            <div><dt>计划时长</dt><dd>{{ formatDuration(project.plannedDurationMs) }}</dd></div>
          </dl>
          <div class="project-card__progress">
            <span><i :style="{ width: `${project.overallProgress || 0}%` }"></i></span>
            <strong>{{ Number(project.overallProgress || 0).toFixed(0) }}%</strong>
          </div>
        </article>
      </div>
      <nav class="project-pagination" aria-label="项目分页">
        <el-button :disabled="query.pageNum <= 1 || loading" @click="changePage(query.pageNum - 1)">上一页</el-button>
        <span>第 {{ query.pageNum }} / {{ pageCount }} 页</span>
        <el-button :disabled="!hasNext || loading" @click="changePage(query.pageNum + 1)">下一页</el-button>
      </nav>
    </template>

    <ProjectCreateDialog
      v-if="showCreate"
      :current-user="sessionStore.user"
      @close="showCreate = false"
      @created="handleCreated"
    />
  </section>
</template>

<style scoped>
.project-page {
  position: relative;
}

.project-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1.6fr) repeat(4, minmax(120px, 0.7fr)) auto auto;
  gap: 10px;
  margin-bottom: 24px;
  padding: 14px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
}

.project-search {
  display: flex;
  height: 40px;
  gap: 9px;
  align-items: center;
  padding: 0 12px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--sg-border);
  border-radius: 9px;
}

.project-search .el-icon {
  color: var(--sg-text-muted);
}

.project-search input {
  min-width: 0;
  flex: 1;
  color: var(--sg-text);
  background: transparent;
  border: 0;
  outline: 0;
}

select {
  min-width: 0;
  height: 40px;
  padding: 0 10px;
  color: var(--sg-text-secondary);
  background: var(--sg-surface-soft);
  border: 1px solid var(--sg-border);
  border-radius: 9px;
}

.project-summary {
  display: flex;
  justify-content: space-between;
  margin: 0 2px 12px;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  transition: opacity 150ms ease;
}

.project-grid.is-refreshing {
  opacity: 0.58;
}

.project-card {
  min-height: 300px;
  padding: 20px;
  cursor: pointer;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.035), transparent 55%), var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.14);
  transition: transform 160ms ease, border-color 160ms ease;
}

.project-card:hover,
.project-card:focus-visible {
  border-color: rgba(255, 182, 87, 0.32);
  outline: none;
  transform: translateY(-3px);
}

.project-card > header,
.project-card__title-row,
.project-card__progress {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.project-card__code {
  color: var(--sg-accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.status-chip {
  padding: 5px 9px;
  color: var(--sg-text-secondary);
  font-size: 11px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 999px;
}

.status-chip[data-tone='success'] { color: var(--sg-success); background: rgba(98, 212, 155, 0.1); }
.status-chip[data-tone='warning'] { color: var(--sg-accent); background: var(--sg-accent-soft); }
.status-chip[data-tone='danger'] { color: var(--sg-danger); background: rgba(255, 107, 107, 0.09); }

.project-card__title-row {
  align-items: flex-start;
  margin-top: 25px;
}

.project-card h3,
.project-card p {
  margin: 0;
}

.project-card h3 {
  font-size: 20px;
}

.project-card p {
  margin-top: 7px;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.project-card__role {
  color: var(--sg-text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.project-card__storage {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 22px 0;
  color: var(--sg-text-secondary);
  font-size: 12px;
}

.status-dot {
  width: 7px;
  height: 7px;
  background: var(--sg-text-muted);
  border-radius: 50%;
}

.status-dot[data-tone='success'] { background: var(--sg-success); }
.status-dot[data-tone='warning'] { background: var(--sg-accent); }
.status-dot[data-tone='danger'] { background: var(--sg-danger); }

.project-card__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.project-card__metrics div {
  min-width: 0;
}

.project-card__metrics dt {
  color: var(--sg-text-muted);
  font-size: 10px;
}

.project-card__metrics dd {
  margin: 4px 0 0;
  overflow: hidden;
  color: var(--sg-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-card__progress {
  margin-top: 22px;
}

.project-card__progress > span {
  height: 5px;
  flex: 1;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 999px;
}

.project-card__progress i {
  display: block;
  height: 100%;
  background: var(--sg-accent);
  border-radius: inherit;
}

.project-card__progress strong {
  color: var(--sg-text-secondary);
  font-size: 11px;
}

.project-card--skeleton {
  cursor: default;
  background: linear-gradient(100deg, var(--sg-surface) 30%, var(--sg-surface-soft) 48%, var(--sg-surface) 66%);
  background-size: 300% 100%;
  animation: shimmer 1.5s infinite;
}

.project-empty {
  display: grid;
  min-height: 330px;
  place-items: center;
  align-content: center;
  padding: 36px;
  text-align: center;
  background: var(--sg-surface);
  border: 1px dashed var(--sg-border-strong);
  border-radius: var(--sg-radius-lg);
}

.project-empty__icon {
  display: grid;
  width: 58px;
  height: 58px;
  color: var(--sg-accent);
  font-size: 25px;
  background: var(--sg-accent-soft);
  border-radius: 16px;
  place-items: center;
}

.project-empty h3 { margin: 18px 0 0; }
.project-empty p { margin: 8px 0 20px; color: var(--sg-text-muted); font-size: 13px; }

.project-pagination {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: center;
  margin-top: 24px;
  color: var(--sg-text-muted);
  font-size: 12px;
}

@keyframes shimmer {
  to { background-position-x: -300%; }
}

@media (max-width: 1180px) {
  .project-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .project-search { grid-column: span 2; }
  .project-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .project-filters,
  .project-grid { grid-template-columns: 1fr; }
  .project-search { grid-column: auto; }
}
</style>
