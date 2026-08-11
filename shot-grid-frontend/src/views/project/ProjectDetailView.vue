<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Lock, Refresh } from '@element-plus/icons-vue'

import { assertPositiveId, getProjectDetail, getProjectOverview } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectArchiveDialog from '@/views/project/components/ProjectArchiveDialog.vue'
import ProjectEditDialog from '@/views/project/components/ProjectEditDialog.vue'
import ProjectMemberPanel from '@/views/project/components/ProjectMemberPanel.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProjectStoragePanel from '@/views/project/components/ProjectStoragePanel.vue'
import {
  formatDateTime,
  formatDuration,
  phaseLabel,
  projectErrorState,
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
    <button class="back-link" type="button" @click="router.push('/projects')"><el-icon><ArrowLeft /></el-icon> 返回项目列表</button>

    <ProjectStatePanel v-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadProject" />
    <div v-else-if="loading && !project" class="detail-loading" role="status">正在加载项目详情…</div>

    <template v-else-if="project">
      <header class="project-hero">
        <div class="project-hero__main">
          <div class="project-hero__code">{{ project.projectCode }}</div>
          <div>
            <div class="project-hero__title-row">
              <h2>{{ project.projectName }}</h2>
              <span class="status-chip" :data-tone="statusMeta(project.projectStatus).tone">{{ statusMeta(project.projectStatus).label }}</span>
            </div>
            <p>{{ project.projectDescription || '暂无项目描述' }}</p>
          </div>
        </div>
        <div class="project-hero__actions">
          <el-button :icon="Refresh" :loading="loading" @click="loadProject">刷新</el-button>
          <el-button v-if="allowedActions.has('project.edit')" :icon="Edit" @click="showEdit = true">编辑项目</el-button>
          <el-button v-if="allowedActions.has('project.archive')" type="danger" plain :icon="Lock" @click="showArchive = true">归档</el-button>
        </div>
        <dl class="project-hero__meta">
          <div><dt>项目类型</dt><dd>{{ project.projectTypeName }}</dd></div>
          <div><dt>画幅</dt><dd>{{ project.aspectRatio }}</dd></div>
          <div><dt>当前阶段</dt><dd>{{ phaseLabel(project.currentPhase) }}</dd></div>
          <div><dt>我的角色</dt><dd>{{ project.myProjectRole === 'director' ? '项目总监' : project.myProjectRole === 'creator' ? '制作人员' : '跨项目管理员' }}</dd></div>
          <div><dt>计划时长</dt><dd>{{ formatDuration(project.plannedDurationMs) }}</dd></div>
          <div><dt>交付日期</dt><dd>{{ project.deliveryDate || '未设置' }}</dd></div>
          <div><dt>存储状态</dt><dd :data-tone="storageMeta(project.storageStatus).tone">{{ storageMeta(project.storageStatus).label }}</dd></div>
          <div><dt>最后更新</dt><dd>{{ formatDateTime(project.updateTime) }}</dd></div>
        </dl>
      </header>

      <section class="overview-section">
        <div class="overview-progress">
          <div><p class="sg-eyebrow">PROGRESS</p><h2>整体完成度</h2></div>
          <strong>{{ Number(overview?.overallProgress ?? project.overallProgress ?? 0).toFixed(0) }}%</strong>
          <span><i :style="{ width: `${overview?.overallProgress ?? project.overallProgress ?? 0}%` }"></i></span>
        </div>
        <ProjectStatePanel v-if="overviewError" compact :title="overviewError.title" :message="overviewError.message" :retryable="overviewError.retryable" @retry="loadProject" />
        <div v-else class="overview-metrics"><article v-for="metric in metrics" :key="metric.label"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></article></div>
      </section>

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
.back-link { display:inline-flex; width:max-content; gap:7px; align-items:center; padding:0; color:var(--sg-text-muted); cursor:pointer; background:transparent; border:0; }
.back-link:hover { color:var(--sg-text); }
.detail-loading { display:grid; min-height:360px; color:var(--sg-text-muted); background:var(--sg-surface); border:1px solid var(--sg-border); border-radius:var(--sg-radius-lg); place-items:center; }
.project-hero { padding:28px; background:linear-gradient(135deg,rgba(255,182,87,.08),transparent 38%),var(--sg-surface); border:1px solid var(--sg-border); border-radius:var(--sg-radius-lg); box-shadow:var(--sg-shadow); }
.project-hero__main { display:flex; gap:18px; align-items:flex-start; }
.project-hero__code { display:grid; width:62px; height:62px; flex:0 0 auto; color:#17130e; font-size:13px; font-weight:900; background:var(--sg-accent); border-radius:16px; place-items:center; }
.project-hero__title-row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.project-hero h2,.project-hero p { margin:0; }.project-hero h2{font-size:28px}.project-hero p{max-width:760px;margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.7}
.status-chip { padding:5px 9px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.05);border-radius:999px}.status-chip[data-tone='success']{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone='warning']{color:var(--sg-accent);background:var(--sg-accent-soft)}
.project-hero__actions { display:flex; gap:9px; justify-content:flex-end; margin-top:-40px; }
.project-hero__meta { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px; margin:28px 0 0; overflow:hidden; background:var(--sg-border); border:1px solid var(--sg-border); border-radius:12px; }
.project-hero__meta div { padding:14px; background:rgba(13,16,21,.92); }.project-hero__meta dt{color:var(--sg-text-muted);font-size:10px}.project-hero__meta dd{margin:5px 0 0;color:var(--sg-text-secondary);font-size:12px}.project-hero__meta dd[data-tone='success']{color:var(--sg-success)}.project-hero__meta dd[data-tone='danger']{color:var(--sg-danger)}
.overview-section { padding:24px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg) }
.overview-progress { display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end }.overview-progress h2{margin:0;font-size:19px}.overview-progress>strong{color:var(--sg-accent);font-size:26px}.overview-progress>span{grid-column:1/-1;height:7px;overflow:hidden;background:rgba(255,255,255,.06);border-radius:99px}.overview-progress i{display:block;height:100%;background:linear-gradient(90deg,var(--sg-accent-strong),var(--sg-accent));border-radius:inherit}
.overview-metrics { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px }.overview-metrics article{padding:15px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.overview-metrics span,.overview-metrics strong{display:block}.overview-metrics span{color:var(--sg-text-muted);font-size:10px}.overview-metrics strong{margin-top:7px;font-size:21px}
@media(max-width:980px){.project-hero__actions{margin-top:20px;justify-content:flex-start}.project-hero__meta,.overview-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.project-hero{padding:20px}.project-hero__main{flex-direction:column}.project-hero__meta,.overview-metrics{grid-template-columns:1fr}}
</style>
