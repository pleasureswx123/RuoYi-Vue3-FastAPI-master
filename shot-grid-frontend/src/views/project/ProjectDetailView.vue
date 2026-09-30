<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Calendar, Delete, Edit, Lock, MoreFilled, Refresh } from '@element-plus/icons-vue'

import { assertPositiveId, getProjectDetail, getProjectOverview } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ProjectArchiveDialog from '@/views/project/components/ProjectArchiveDialog.vue'
import ProjectEditDialog from '@/views/project/components/ProjectEditDialog.vue'
import ProjectMemberPanel from '@/views/project/components/ProjectMemberPanel.vue'
import ProjectPurgeDialog from '@/views/project/components/ProjectPurgeDialog.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProjectStoragePanel from '@/views/project/components/ProjectStoragePanel.vue'
import {
  formatDateTime,
  phaseLabel,
  projectErrorState,
  projectRoleMeta,
  statusMeta,
  storageMeta
} from '@/views/project/projectPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const project = ref(null)
const overview = ref(null)
const loading = ref(false)
const errorState = ref(null)
const overviewError = ref(null)
const descriptionExpanded = ref(false)
const membersVisible = ref(false)
const memberRefreshKey = ref(0)
const showEdit = ref(false)
const editReferencesOnly = ref(false)
const showArchive = ref(false)
const showPurge = ref(false)
let controller = null

const projectId = computed(() => {
  try { return assertPositiveId(route.params.projectId, '项目') } catch { return null }
})
const allowedActions = computed(() => new Set(project.value?.allowedActions || []))
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const isDirectorScope = computed(
  () => project.value?.myProjectRole === 'director' || wildcard.value || hasPermission('shotgrid:project:all')
)
const canDiagnoseStorage = computed(() => isDirectorScope.value && hasPermission('shotgrid:storage:path'))
const canRetryOperation = computed(() => isDirectorScope.value && hasPermission('shotgrid:storage:retry'))
const canViewSchedule = computed(() => hasPermission('shotgrid:task:list'))
const metrics = computed(() => [
  { label: '总集数', value: overview.value?.totalEpisodes ?? project.value?.totalEpisodes ?? 0 },
  { label: '总场次', value: overview.value?.totalScenes ?? project.value?.totalScenes ?? 0 },
  { label: '总镜头', value: overview.value?.totalShots ?? project.value?.totalShots ?? 0 },
  { label: '总资产', value: overview.value?.totalAssets ?? project.value?.totalAssets ?? 0 },
  { label: '待审核镜头', value: overview.value?.pendingReviewShots ?? project.value?.pendingReviewShots ?? 0 },
  { label: '待修改镜头', value: overview.value?.revisionShots ?? project.value?.revisionShots ?? 0 },
  { label: '待审核资产项', value: overview.value?.pendingReviewAssetItems ?? project.value?.pendingReviewAssetItems ?? 0 },
  { label: '待修改资产项', value: overview.value?.revisionAssetItems ?? project.value?.revisionAssetItems ?? 0 }
])

async function loadProject() {
  if (!projectId.value) {
    errorState.value = { title: '项目地址无效', message: '请从项目列表重新进入。', retryable: false, status: 404 }
    return
  }
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  errorState.value = null
  overviewError.value = null
  try {
    const detailResponse = await getProjectDetail(projectId.value, { signal: requestController.signal })
    project.value = detailResponse.data
    try {
      const overviewResponse = await getProjectOverview(projectId.value, { signal: requestController.signal })
      overview.value = overviewResponse.data
    } catch (error) {
      if (error?.code !== 'ERR_CANCELED') overviewError.value = projectErrorState(error, '项目概览加载失败')
    }
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      project.value = null
      overview.value = null
      errorState.value = projectErrorState(error, '项目详情加载失败')
    }
  } finally {
    if (controller === requestController) loading.value = false
  }
}

async function handleSaved() {
  showEdit.value = false
  ElMessage.success(editReferencesOnly.value ? '项目资料已更新' : '项目基本信息已更新')
  await loadProject()
}

async function handleArchived() {
  showArchive.value = false
  ElMessage.success('项目已归档')
  await loadProject()
}

async function handlePurged() {
  showPurge.value = false
  ElMessage.success('项目业务数据已删除，NAS 与独占文件正在后台清理')
  await router.replace('/projects')
}

async function refreshAndCloseDialogs() {
  showEdit.value = false
  showArchive.value = false
  showPurge.value = false
  await loadProject()
}

onMounted(loadProject)
watch(() => route.params.projectId, (next, previous) => {
  if (next !== previous) { descriptionExpanded.value = false; membersVisible.value = false; loadProject() }
})
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="sg-page project-detail-page">
    <el-button class="back-link" link :icon="ArrowLeft" @click="router.push('/projects')">返回项目列表</el-button>

    <ProjectStatePanel v-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadProject" />
    <el-card v-else-if="loading && !project" class="detail-loading" shadow="never" aria-label="正在加载项目详情"><el-skeleton :rows="8" animated /></el-card>

    <template v-else-if="project">
      <el-card class="project-hero" shadow="never">
        <div class="project-hero__top">
        <div class="project-hero__main">
          <div class="project-hero__code">{{ project.projectCode }}</div>
          <div>
            <div class="project-hero__title-row">
              <h2>{{ project.projectName }}</h2>
              <el-tag size="small" effect="plain" round :type="tagTypeFromTone(statusMeta(project.projectStatus).tone)">{{ statusMeta(project.projectStatus).label }}</el-tag>
            </div>
            <p :class="{ 'description-clamped': !descriptionExpanded }">{{ project.projectDescription || '暂无项目描述' }}</p><el-button v-if="project.projectDescription?.length > 60" link type="primary" :aria-expanded="descriptionExpanded" @click="descriptionExpanded = !descriptionExpanded">{{ descriptionExpanded ? '收起描述' : '展开描述' }}</el-button>
          </div>
        </div>
        <div class="project-hero__actions">
          <el-button :icon="Refresh" circle aria-label="刷新项目" :loading="loading" @click="loadProject" />
          <el-button v-if="canViewSchedule" type="primary" :icon="Calendar" @click="router.push(`/projects/${projectId}/schedule`)">项目排期</el-button>
          <el-button v-if="allowedActions.has('project.edit')" type="primary" plain :icon="Edit" @click="editReferencesOnly = false; showEdit = true">编辑项目</el-button>
          <el-dropdown v-if="allowedActions.has('project.archive') || allowedActions.has('project.delete')" trigger="click" @command="command => command === 'archive' ? showArchive = true : showPurge = true">
            <el-button :icon="MoreFilled">更多</el-button>
            <template #dropdown><el-dropdown-menu><el-dropdown-item v-if="allowedActions.has('project.archive')" command="archive" :icon="Lock">归档项目</el-dropdown-item><el-dropdown-item v-if="allowedActions.has('project.delete')" command="purge" :icon="Delete" :divided="allowedActions.has('project.archive')">永久删除</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
        </div>
        <el-descriptions class="project-hero__meta" :column="3" border>
          <el-descriptions-item label="项目类型"><el-tag size="small" effect="plain" type="primary">{{ project.projectTypeName }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="画幅"><el-tag size="small" effect="plain" type="info">{{ project.aspectRatio }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="当前阶段"><el-tag size="small" effect="plain" type="info">{{ phaseLabel(project.currentPhase) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="我的角色"><el-tag size="small" effect="plain" round :type="projectRoleMeta(project.myProjectRole).type">{{ projectRoleMeta(project.myProjectRole).label }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="存储状态"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(storageMeta(project.storageStatus).tone)">{{ storageMeta(project.storageStatus).label }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="最后更新">{{ formatDateTime(project.updateTime) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="overview-section" shadow="never">
        <div class="overview-progress">
          <div><h2>制作进度</h2></div>
          <strong>{{ Number(overview?.overallProgress ?? project.overallProgress ?? 0).toFixed(0) }}%</strong>
        <nav class="project-shortcuts" aria-label="项目制作入口">
          <el-button v-if="hasPermission('shotgrid:shot:list')" type="primary" @click="router.push({ path: '/shots', query: { projectId } })">查看镜头</el-button>
          <el-button v-if="hasPermission('shotgrid:asset:list')" type="primary" plain @click="router.push({ path: '/assets', query: { projectId } })">查看资产</el-button>
          <el-button v-if="hasPermission('shotgrid:reviewList:list') && hasPermission('shotgrid:version:review')" type="warning" plain @click="router.push({ path: '/reviews', query: { projectId, reviewStatus: 'active' } })">待审核</el-button>
        </nav>
          <el-progress :percentage="Number(overview?.overallProgress ?? project.overallProgress ?? 0)" :stroke-width="8" :show-text="false" color="var(--sg-accent)" />
        </div>
        <ProjectStatePanel v-if="overviewError" compact :title="overviewError.title" :message="overviewError.message" :retryable="overviewError.retryable" @retry="loadProject" />
        <div v-else class="overview-metrics"><el-card v-for="metric in metrics" :key="metric.label" shadow="never"><el-statistic :title="metric.label" :value="metric.value" /></el-card></div>
      </el-card>

      <div class="project-support-grid">
      <ProjectMemberPanel
        :key="`members-${projectId}-${memberRefreshKey}`"
        :project-id="projectId"
        compact
        @show-all="membersVisible = true"
        :can-manage="allowedActions.has('member.manage')"
        :permissions="sessionStore.permissions"
      />

      <el-card class="project-references" shadow="never" data-testid="project-references">

        <div class="section-heading"><h2>项目资料</h2><el-button v-if="allowedActions.has('project.edit')" type="primary" plain :icon="Edit" @click="editReferencesOnly = true; showEdit = true">编辑资料</el-button></div>
        <p v-if="project.referenceDescription" class="project-references__description">{{ project.referenceDescription }}</p>
        <ReviewReferenceFiles v-if="project.referenceFiles?.length" :key="project.projectId" :files="project.referenceFiles" />
        <el-empty v-if="!project.referenceDescription && !project.referenceFiles?.length" description="项目暂未提供剧本或参考资料" :image-size="48" />
      </el-card>

      </div>

      <ProjectStoragePanel
        :key="`storage-${projectId}`"
        :show-operations="false"
        :project-id="projectId"
        :can-diagnose="canDiagnoseStorage"
        :can-retry-project="allowedActions.has('storage.retry')"
        :can-retry-operation="canRetryOperation"
      />

      <el-drawer v-model="membersVisible" @closed="memberRefreshKey += 1" title="完整成员列表" size="min(1000px, 94vw)" append-to-body destroy-on-close>
        <ProjectMemberPanel v-if="membersVisible" :project-id="projectId" :can-manage="allowedActions.has('member.manage')" :permissions="sessionStore.permissions" />
      </el-drawer>
      <ProjectEditDialog v-if="showEdit" :project="project" :references-only="editReferencesOnly" @close="showEdit = false" @saved="handleSaved" @refresh="refreshAndCloseDialogs" />
      <ProjectArchiveDialog v-if="showArchive" :project="project" @close="showArchive = false" @archived="handleArchived" @refresh="refreshAndCloseDialogs" />
      <ProjectPurgeDialog v-if="showPurge" :project="project" @close="showPurge = false" @purged="handlePurged" @refresh="refreshAndCloseDialogs" />
    </template>
  </section>
</template>

<style scoped>
.project-hero__top { display:flex;align-items:flex-start;justify-content:space-between;gap:24px }
.project-hero__main { min-width:0;flex:1 }
.project-hero__main > div:last-child { min-width:0 }
.description-clamped { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden }
.project-hero p { overflow-wrap:anywhere }
.project-support-grid { display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:20px;align-items:start }
.project-support-grid > * { min-width:0 }
.section-heading { display:flex;align-items:center;justify-content:space-between;gap:12px }
.project-shortcuts { display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-bottom:0 }
@media(max-width:1150px){.project-support-grid{grid-template-columns:1fr}.project-hero__top{flex-direction:column;gap:12px}}

.project-detail-page { display:grid; gap:20px; }
.back-link { width:max-content; color:var(--sg-text-muted); }
.back-link:hover { color:var(--sg-text); }
.detail-loading { min-height:360px; background:var(--sg-surface); border-color:var(--sg-border); border-radius:var(--sg-radius-lg); }.detail-loading :deep(.el-card__body){padding:30px}
.project-hero { background:linear-gradient(135deg,rgba(255,182,87,.08),transparent 38%),var(--sg-surface); border-color:var(--sg-border); border-radius:var(--sg-radius-lg); box-shadow:var(--sg-shadow); }.project-hero :deep(.el-card__body){padding:20px}
.project-hero__main { display:flex; gap:18px; align-items:flex-start; }
.project-hero__code { display:grid; width:62px; height:62px; flex:0 0 auto; color:var(--sg-on-accent); font-size:13px; font-weight:900; background:var(--sg-accent-surface); border-radius:16px; place-items:center; }
.project-hero__title-row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.project-hero h2,.project-hero p { margin:0; }.project-hero h2{font-size:28px}.project-hero p{max-width:760px;margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.7}
.project-hero__actions { display:flex; gap:9px; justify-content:flex-end; margin-top:0;flex-wrap:wrap;flex-shrink:0; }
.project-hero__meta { margin-top:18px; }.project-hero__meta :deep(.el-descriptions__body),.project-hero__meta :deep(.el-descriptions__cell){background:rgba(13,16,21,.92)!important;border-color:var(--sg-border)!important}.project-hero__meta :deep(.el-descriptions__label){color:var(--sg-text-muted);font-size:10px}.project-hero__meta :deep(.el-descriptions__content){color:var(--sg-text-secondary);font-size:12px}
.project-references { min-width:0;background:var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-lg) }
.project-references :deep(.el-card__body) { display:grid;gap:12px;padding:20px }
.project-references h2 { margin:0;font-size:19px }
.project-references__description { margin:0;color:var(--sg-text-secondary);font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere }
.overview-section { background:var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-lg) }.overview-section :deep(.el-card__body){padding:20px}
.overview-progress { display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:center }.overview-progress h2{margin:0;font-size:19px}.overview-progress>strong{color:var(--sg-accent);font-size:26px}.overview-progress>span{grid-column:1/-1;height:7px;overflow:hidden;background:rgba(255,255,255,.06);border-radius:99px}.overview-progress i{display:block;height:100%;background:linear-gradient(90deg,var(--sg-accent-strong),var(--sg-accent));border-radius:inherit}
.overview-progress>.el-progress{--el-fill-color-light:var(--sg-progress-track);grid-column:1/-1}.overview-metrics { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px }.overview-metrics>.el-card{background:rgba(255,255,255,.025);border-color:var(--sg-border);border-radius:10px}.overview-metrics :deep(.el-card__body){padding:15px}.overview-metrics :deep(.el-statistic__head){color:var(--sg-text-muted);font-size:10px}.overview-metrics :deep(.el-statistic__number){color:var(--sg-text);font-size:21px}
@media(max-width:980px){.project-hero__actions{margin-top:20px;justify-content:flex-start}.project-hero__meta,.overview-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.overview-progress{grid-template-columns:1fr auto}.project-shortcuts{grid-column:1/-1;justify-content:flex-start}.project-hero{padding:20px}.project-hero__main{flex-direction:column}.project-hero__meta,.overview-metrics{grid-template-columns:1fr}}
.project-hero__meta :deep(.el-descriptions__body),
.project-hero__meta :deep(.el-descriptions__cell) { background: var(--sg-surface-raised) !important; }
</style>
