<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'

import { getProjectPage } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectCreateDialog from '@/views/project/components/ProjectCreateDialog.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import {
  phaseLabel,
  projectErrorState,
  statusMeta,
  storageMeta
} from '@/views/project/projectPresentation'

const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const total = ref(0)
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

function tagType(tone) {
  return ['success', 'warning', 'danger'].includes(tone) ? tone : 'info'
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

    <el-form :model="query" class="project-filters" aria-label="项目筛选" @submit.prevent="submitFilters">
      <el-form-item class="project-filter-item project-filter-item--keyword" prop="keyword">
        <el-input v-model="query.keyword" :prefix-icon="Search" maxlength="200" clearable placeholder="搜索项目名称或代号" aria-label="搜索项目名称或代号" />
      </el-form-item>
      <el-form-item class="project-filter-item" prop="projectStatus">
        <el-select v-model="query.projectStatus" class="sg-select" placeholder="全部状态" aria-label="项目状态">
          <el-option label="全部状态" value="" />
          <el-option label="准备中" value="preparing" />
          <el-option label="进行中" value="active" />
          <el-option label="已完成" value="completed" />
          <el-option label="已归档" value="archived" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="canViewAll" class="project-filter-item" prop="scope">
        <el-select v-model="query.scope" class="sg-select" placeholder="我的项目" aria-label="项目范围">
          <el-option label="我的项目" value="" />
          <el-option label="全部项目" value="all" />
        </el-select>
      </el-form-item>
      <el-form-item class="project-filter-item" prop="orderByColumn">
        <el-select v-model="query.orderByColumn" class="sg-select" aria-label="排序字段">
          <el-option label="创建时间" value="createTime" />
          <el-option label="项目代号" value="projectCode" />
          <el-option label="项目名称" value="projectName" />
        </el-select>
      </el-form-item>
      <el-form-item class="project-filter-item" prop="isAsc">
        <el-select v-model="query.isAsc" class="sg-select" aria-label="排序方向">
          <el-option label="降序" value="descending" />
          <el-option label="升序" value="ascending" />
        </el-select>
      </el-form-item>
      <el-form-item class="project-filter-actions">
        <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
        <el-button :icon="Refresh" circle aria-label="刷新项目列表" :disabled="loading" @click="loadProjects" />
      </el-form-item>
    </el-form>

    <ProjectStatePanel
      v-if="errorState"
      :title="errorState.title"
      :message="errorState.message"
      :retryable="errorState.retryable"
      @retry="loadProjects"
    />

    <div v-else-if="loading && projects.length === 0" class="project-grid" aria-label="项目加载中">
      <el-card v-for="index in 6" :key="index" class="project-card project-card--skeleton" shadow="never">
        <el-skeleton :rows="5" animated />
      </el-card>
    </div>

    <el-empty v-else-if="projects.length === 0" class="project-empty" description="当前范围暂无项目">
      <p>可以调整筛选条件，或由具备权限的项目总监创建第一个项目。</p>
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="showCreate = true">创建项目</el-button>
    </el-empty>

    <template v-else>
      <div class="project-summary">
        <span>共 {{ total }} 个项目</span>
        <span v-if="loading">正在刷新…</span>
      </div>
      <div class="project-grid" :class="{ 'is-refreshing': loading }">
        <el-card
          v-for="project in projects"
          :key="project.projectId"
          class="project-card"
          shadow="hover"
          tabindex="0"
          role="link"
          :aria-label="`打开项目 ${project.projectName}`"
          @click="openProject(project.projectId)"
          @keydown.enter="openProject(project.projectId)"
        >
          <header class="project-card__header">
            <span class="project-card__code">{{ project.projectCode }}</span>
            <el-tag size="small" effect="plain" :type="tagType(statusMeta(project.projectStatus).tone)">
              {{ statusMeta(project.projectStatus).label }}
            </el-tag>
          </header>
          <div class="project-card__title-row">
            <div>
              <h3>{{ project.projectName }}</h3>
              <p>{{ project.projectTypeName }} · {{ project.aspectRatio }}</p>
            </div>
            <el-tag class="project-card__role" size="small" effect="plain" type="info">{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</el-tag>
          </div>
          <div class="project-card__storage">
            <span class="status-dot" :data-tone="storageMeta(project.storageStatus).tone"></span>
            {{ storageMeta(project.storageStatus).label }}
          </div>
          <dl class="project-card__metrics">
            <div><dt>阶段</dt><dd>{{ phaseLabel(project.currentPhase) }}</dd></div>
            <div><dt>镜头</dt><dd>{{ project.completedShots }}/{{ project.totalShots }}</dd></div>
            <div><dt>资产</dt><dd>{{ project.completedAssets }}/{{ project.totalAssets }}</dd></div>
          </dl>
          <div class="project-card__progress">
            <el-progress :percentage="Number(project.overallProgress || 0)" :stroke-width="5" :show-text="false" />
            <strong>{{ Number(project.overallProgress || 0).toFixed(0) }}%</strong>
          </div>
        </el-card>
      </div>
      <el-pagination
        v-if="total > query.pageSize"
        class="project-pagination"
        background
        layout="prev, pager, next"
        :current-page="query.pageNum"
        :page-size="query.pageSize"
        :total="total"
        :disabled="loading"
        aria-label="项目分页"
        @current-change="changePage"
      />
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
  grid-template-columns: minmax(220px, 1.6fr) repeat(4, minmax(120px, 0.7fr)) auto;
  gap: 10px;
  margin-bottom: 24px;
  padding: 14px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
}

.project-filters :deep(.el-form-item) { min-width: 0; margin-bottom: 0; }
.project-filter-item :deep(.el-form-item__content),
.project-filter-item :deep(.el-input),
.project-filter-item :deep(.el-select) { width: 100%; min-width: 0; }
.project-filter-actions :deep(.el-form-item__content) { flex-wrap: nowrap; justify-content: flex-end; }

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
  cursor: pointer;
  --el-card-bg-color: var(--sg-surface);
  --el-card-border-color: var(--sg-border);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.035), transparent 55%), var(--sg-surface);
  border-radius: var(--sg-radius-md);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.14);
  transition: transform 160ms ease, border-color 160ms ease;
}

.project-card :deep(.el-card__body) { padding: 20px; }

.project-card:hover,
.project-card:focus-visible {
  border-color: rgba(255, 182, 87, 0.32);
  outline: none;
  transform: translateY(-3px);
}

.project-card__header,
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

.project-card__progress :deep(.el-progress) {
  flex: 1;
}

.project-card__progress :deep(.el-progress-bar__outer) { background: rgba(255, 255, 255, 0.06); }
.project-card__progress :deep(.el-progress-bar__inner) { background: var(--sg-accent); }

.project-card__progress strong {
  color: var(--sg-text-secondary);
  font-size: 11px;
}

.project-card--skeleton {
  cursor: default;
}

.project-empty {
  min-height: 330px;
  padding: 36px;
  background: var(--sg-surface);
  border: 1px dashed var(--sg-border-strong);
  border-radius: var(--sg-radius-lg);
}
.project-empty :deep(.el-empty__description p) { color: var(--sg-text-secondary); }
.project-empty > p { margin: 0 0 16px; color: var(--sg-text-muted); font-size: 13px; }

.project-pagination {
  justify-content: center;
  margin-top: 24px;
}
.project-pagination :deep(.el-pager li),
.project-pagination :deep(button) { background: var(--sg-surface) !important; }
.project-pagination :deep(.is-active) { color: #17130d !important; background: var(--sg-accent) !important; }

@media (max-width: 1180px) {
  .project-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .project-filter-item--keyword { grid-column: span 2; }
  .project-filter-actions :deep(.el-form-item__content) { justify-content: flex-start; }
  .project-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .project-filters,
  .project-grid { grid-template-columns: 1fr; }
  .project-filter-item--keyword { grid-column: auto; }
}
</style>
