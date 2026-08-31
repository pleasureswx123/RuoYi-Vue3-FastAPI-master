<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Calendar } from '@element-plus/icons-vue'

import { assertPositiveId, getProjectDetail } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import { projectErrorState, projectRoleMeta, statusMeta } from '@/views/project/projectPresentation'
import ScheduleBoard from '@/views/schedule/ScheduleBoard.vue'
import { normalizeScheduleRouteQuery, scheduleRouteQueryEquals } from '@/views/schedule/scheduleRouteQuery'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const project = ref(null)
const loading = ref(false)
const errorState = ref(null)
let controller = null

const projectId = computed(() => {
  try { return assertPositiveId(route.params.projectId, '项目') } catch { return null }
})
const scheduleQuery = computed(() => normalizeScheduleRouteQuery(route.query))
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const isDirector = computed(() => project.value?.myProjectRole === 'director' || wildcard.value || hasPermission('shotgrid:project:all'))
const editableAllowed = computed(() => Boolean(
  project.value
  && isDirector.value
  && hasPermission('shotgrid:task:schedule')
  && !['completed', 'archived'].includes(project.value.projectStatus)
))

async function normalizeRouteQuery() {
  const normalized = normalizeScheduleRouteQuery(route.query)
  if (!scheduleRouteQueryEquals(route.query, normalized)) {
    await router.replace({ name: 'project-schedule', params: { projectId: projectId.value }, query: normalized })
  }
}

async function loadProject() {
  if (!projectId.value) {
    errorState.value = { title: '项目地址无效', message: '请从项目列表重新进入排期。', retryable: false }
    return
  }
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  errorState.value = null
  try {
    const response = await getProjectDetail(projectId.value, { signal: requestController.signal })
    project.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      project.value = null
      errorState.value = projectErrorState(error, '项目排期加载失败')
    }
  } finally {
    if (controller === requestController) loading.value = false
  }
}

function handleQueryChange(query) {
  router.replace({ name: 'project-schedule', params: { projectId: projectId.value }, query })
}

onMounted(() => {
  normalizeRouteQuery()
  loadProject()
})
watch(() => route.params.projectId, (next, previous) => {
  if (next !== previous) {
    normalizeRouteQuery()
    loadProject()
  }
})
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="sg-page project-schedule-page">
    <el-button class="back-link" link :icon="ArrowLeft" @click="router.push(`/projects/${projectId}/overview`)">返回项目详情</el-button>
    <header class="sg-page-heading project-schedule-heading">
      <div>
        <p class="sg-eyebrow">SCHEDULE</p>
        <h2 class="sg-page-title">{{ project?.projectName ? `${project.projectName} · 项目排期` : '项目排期' }}</h2>
        <p class="sg-page-description">按人员泳道或任务甘特查看自然时间排期；周末和节假日均连续计入。</p>
      </div>
      <div v-if="project" class="project-schedule-heading__meta">
        <el-tag effect="plain" type="primary"><el-icon><Calendar /></el-icon>{{ statusMeta(project.projectStatus).label }}</el-tag>
        <el-tag effect="plain" type="info">{{ projectRoleMeta(project.myProjectRole).label }}</el-tag>
        <el-tag v-if="!editableAllowed" effect="plain" type="warning">只读查看</el-tag>
      </div>
    </header>

    <ProjectStatePanel v-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadProject" />
    <el-card v-else-if="loading && !project" class="project-schedule-loading" shadow="never"><el-skeleton :rows="10" animated /></el-card>
    <ScheduleBoard
      v-else-if="project && projectId"
      :project-id="projectId"
      target-kind="all"
      :initial-mode="scheduleQuery.mode"
      :initial-scale="scheduleQuery.scale"
      :initial-group-by="scheduleQuery.groupBy"
      :initial-window-start="scheduleQuery.windowStart"
      :initial-window-end="scheduleQuery.windowEnd"
      :editable-allowed="editableAllowed"
      @query-change="handleQueryChange"
    />
  </section>
</template>

<style scoped>
.project-schedule-page { display: grid; gap: 18px; min-width: 0; }
.back-link { width: max-content; color: var(--sg-text-muted); }
.project-schedule-heading { align-items: flex-end; }
.project-schedule-heading__meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.project-schedule-heading__meta :deep(.el-tag__content) { display: inline-flex; gap: 5px; align-items: center; }
.project-schedule-loading { min-height: 480px; background: var(--sg-surface); border-color: var(--sg-border); }
.project-schedule-loading :deep(.el-card__body) { padding: 24px; }
@media (max-width: 760px) { .project-schedule-heading { align-items: flex-start; } }
</style>
