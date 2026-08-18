<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Lock, Refresh } from '@element-plus/icons-vue'

import { assertPositiveId, getProjectDetail, getProjectOverview } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ProjectArchiveDialog from '@/views/project/components/ProjectArchiveDialog.vue'
import ProjectEditDialog from '@/views/project/components/ProjectEditDialog.vue'
import ProjectMemberPanel from '@/views/project/components/ProjectMemberPanel.vue'
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
const showEdit = ref(false)
const showArchive = ref(false)
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
const metrics = computed(() => [
  { label: '总集数', value: overview.value?.totalEpisodes ?? project.value?.totalEpisodes ?? 0 },
  { label: '总场次', value: overview.value?.totalScenes ?? project.value?.totalScenes ?? 0 },
  { label: '总镜头', value: overview.value?.totalShots ?? project.value?.totalShots ?? 0 },
  { label: '总资产', value: overview.value?.totalAssets ?? project.value?.totalAssets ?? 0 },
  { label: '待审核镜头', value: overview.value?.pendingReviewShots ?? project.value?.pendingReviewShots ?? 0 },
  { label: '修改中镜头', value: overview.value?.revisionShots ?? project.value?.revisionShots ?? 0 },
  { label: '待审核资产项', value: overview.value?.pendingReviewAssetItems ?? project.value?.pendingReviewAssetItems ?? 0 },
  { label: '修改中资产项', value: overview.value?.revisionAssetItems ?? project.value?.revisionAssetItems ?? 0 }
])

async function loadProject() {
  if (!projectId.value) {
    errorState.value = { title: '项目地址无效', message: '项目 ID 必须为正整数。', retryable: false, status: 404 }
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
  ElMessage.success('项目基本信息已更新')
  await loadProject()
}

async function handleArchived() {
  showArchive.value = false
  ElMessage.success('项目已归档')
  await loadProject()
}

async function refreshAndCloseDialogs() {
  showEdit.value = false
  showArchive.value = false
  await loadProject()
}

onMounted(loadProject)
watch(() => route.params.projectId, (next, previous) => {
  if (next !== previous) loadProject()
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
        <div class="project-hero__main">
          <div class="project-hero__code">{{ project.projectCode }}</div>
          <div>
            <div class="project-hero__title-row">
              <h2>{{ project.projectName }}</h2>
              <el-tag size="small" effect="plain" round :type="tagTypeFromTone(statusMeta(project.projectStatus).tone)">{{ statusMeta(project.projectStatus).label }}</el-tag>
            </div>
            <p>{{ project.projectDescription || '暂无项目描述' }}</p>
          </div>
        </div>
        <div class="project-hero__actions">
          <el-button :icon="Refresh" :loading="loading" @click="loadProject">刷新</el-button>
          <el-button v-if="allowedActions.has('project.edit')" :icon="Edit" @click="showEdit = true">编辑项目</el-button>
          <el-button v-if="allowedActions.has('project.archive')" type="danger" plain :icon="Lock" @click="showArchive = true">归档</el-button>
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
          <div><p class="sg-eyebrow">PROGRESS</p><h2>整体完成度</h2></div>
          <strong>{{ Number(overview?.overallProgress ?? project.overallProgress ?? 0).toFixed(0) }}%</strong>
          <el-progress :percentage="Number(overview?.overallProgress ?? project.overallProgress ?? 0)" :stroke-width="8" :show-text="false" color="var(--sg-accent)" />
        </div>
        <ProjectStatePanel v-if="overviewError" compact :title="overviewError.title" :message="overviewError.message" :retryable="overviewError.retryable" @retry="loadProject" />
        <div v-else class="overview-metrics"><el-card v-for="metric in metrics" :key="metric.label" shadow="never"><el-statistic :title="metric.label" :value="metric.value" /></el-card></div>
      </el-card>

      <ProjectMemberPanel
        :key="`members-${projectId}`"
        :project-id="projectId"
        :can-manage="allowedActions.has('member.manage')"
        :permissions="sessionStore.permissions"
      />

      <ProjectStoragePanel
        :key="`storage-${projectId}`"
        :project-id="projectId"
        :can-diagnose="canDiagnoseStorage"
        :can-retry-project="allowedActions.has('storage.retry')"
        :can-retry-operation="canRetryOperation"
      />

      <ProjectEditDialog v-if="showEdit" :project="project" @close="showEdit = false" @saved="handleSaved" @refresh="refreshAndCloseDialogs" />
      <ProjectArchiveDialog v-if="showArchive" :project="project" @close="showArchive = false" @archived="handleArchived" @refresh="refreshAndCloseDialogs" />
    </template>
  </section>
</template>

<style scoped>
.project-detail-page { display:grid; gap:20px; }
.back-link { width:max-content; color:var(--sg-text-muted); }
.back-link:hover { color:var(--sg-text); }
.detail-loading { min-height:360px; background:var(--sg-surface); border-color:var(--sg-border); border-radius:var(--sg-radius-lg); }.detail-loading :deep(.el-card__body){padding:30px}
.project-hero { background:linear-gradient(135deg,rgba(255,182,87,.08),transparent 38%),var(--sg-surface); border-color:var(--sg-border); border-radius:var(--sg-radius-lg); box-shadow:var(--sg-shadow); }.project-hero :deep(.el-card__body){padding:28px}
.project-hero__main { display:flex; gap:18px; align-items:flex-start; }
.project-hero__code { display:grid; width:62px; height:62px; flex:0 0 auto; color:var(--sg-on-accent); font-size:13px; font-weight:900; background:var(--sg-accent-surface); border-radius:16px; place-items:center; }
.project-hero__title-row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.project-hero h2,.project-hero p { margin:0; }.project-hero h2{font-size:28px}.project-hero p{max-width:760px;margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.7}
.project-hero__actions { display:flex; gap:9px; justify-content:flex-end; margin-top:-40px; }
.project-hero__meta { margin-top:28px; }.project-hero__meta :deep(.el-descriptions__body),.project-hero__meta :deep(.el-descriptions__cell){background:rgba(13,16,21,.92)!important;border-color:var(--sg-border)!important}.project-hero__meta :deep(.el-descriptions__label){color:var(--sg-text-muted);font-size:10px}.project-hero__meta :deep(.el-descriptions__content){color:var(--sg-text-secondary);font-size:12px}
.overview-section { background:var(--sg-surface);border-color:var(--sg-border);border-radius:var(--sg-radius-lg) }.overview-section :deep(.el-card__body){padding:24px}
.overview-progress { display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end }.overview-progress h2{margin:0;font-size:19px}.overview-progress>strong{color:var(--sg-accent);font-size:26px}.overview-progress>span{grid-column:1/-1;height:7px;overflow:hidden;background:rgba(255,255,255,.06);border-radius:99px}.overview-progress i{display:block;height:100%;background:linear-gradient(90deg,var(--sg-accent-strong),var(--sg-accent));border-radius:inherit}
.overview-progress>.el-progress{--el-fill-color-light:var(--sg-progress-track);grid-column:1/-1}.overview-metrics { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px }.overview-metrics>.el-card{background:rgba(255,255,255,.025);border-color:var(--sg-border);border-radius:10px}.overview-metrics :deep(.el-card__body){padding:15px}.overview-metrics :deep(.el-statistic__head){color:var(--sg-text-muted);font-size:10px}.overview-metrics :deep(.el-statistic__number){color:var(--sg-text);font-size:21px}
@media(max-width:980px){.project-hero__actions{margin-top:20px;justify-content:flex-start}.project-hero__meta,.overview-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.project-hero{padding:20px}.project-hero__main{flex-direction:column}.project-hero__meta,.overview-metrics{grid-template-columns:1fr}}
.project-hero__meta :deep(.el-descriptions__body),
.project-hero__meta :deep(.el-descriptions__cell) { background: var(--sg-surface-raised) !important; }
</style>
