<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Lock, Refresh, UserFilled } from '@element-plus/icons-vue'

import { archiveShot, getEpisodePage, getShotDetail, listShotAssignees } from '@/api/shot-grid/shots'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { tagTypeFromTone } from '@/utils/tag'
import ProductionHistoryPanel from '@/components/production-history/ProductionHistoryPanel.vue'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'
import { directoryStatusMeta, formatShotDateTime, formatShotDuration, shotAssigneeName, shotErrorState, shotStatusMeta, shotStatusTagClass } from '@/views/shot/shotPresentation'
import { taskPriorityMeta, taskStatusMeta, taskVersionStatusMeta } from '@/views/task/taskPresentation'

const props = defineProps({
  targetProjectId: { type: [Number, String], default: null },
  targetShotId: { type: [Number, String], default: null },
  embedded: { type: Boolean, default: false }
})
const emit = defineEmits(['changed', 'deleted'])
const route = useRoute()
const router = useRouter()
const shot = ref(null)
const episodes = ref([])
const members = ref([])
const loading = ref(false)
const archiving = ref(false)
const errorState = ref(null)
const showEdit = ref(false)
const showAssign = ref(false)
const editContext = ref(null)
const assignContext = ref(null)
const historyRefreshKey = ref(0)
let controller = null
let loadGeneration = 0
let operationGeneration = 0
let disposed = false

const projectId = computed(() => {
  try { return assertPositiveId(props.targetProjectId ?? route.params.projectId, '项目') } catch { return null }
})
const shotId = computed(() => {
  try { return assertPositiveId(props.targetShotId ?? route.params.shotId, '镜头') } catch { return null }
})
const allowedActions = computed(() => new Set(shot.value?.allowedActions || []))

async function loadAllAssignees(targetProjectId, signal) {
  const rows = []
  let pageNum = 1
  let hasNext = true
  while (hasNext) {
    const response = await listShotAssignees(targetProjectId, { pageNum, pageSize: 100 }, { signal })
    rows.push(...(Array.isArray(response.rows) ? response.rows : []))
    hasNext = Boolean(response.hasNext) && pageNum < 100
    pageNum += 1
  }
  return rows
}

async function loadDetail() {
  const generation = ++loadGeneration
  controller?.abort()
  const targetProjectId = projectId.value
  const targetShotId = shotId.value
  shot.value = null
  episodes.value = []
  members.value = []
  closeEditDialog()
  closeAssignDialog()
  errorState.value = null
  if (!targetProjectId || !targetShotId) {
    loading.value = false
    errorState.value = { title: '镜头地址无效', message: '请返回镜头列表并重新打开该镜头。', retryable: false }
    return
  }
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  const isCurrentContext = () => (
    controller === requestController &&
    generation === loadGeneration &&
    !requestController.signal.aborted &&
    projectId.value === targetProjectId &&
    shotId.value === targetShotId
  )
  try {
    const [detailResponse, episodeResponse, memberResponse] = await Promise.all([
      getShotDetail(targetProjectId, targetShotId, { signal: requestController.signal }),
      getEpisodePage(targetProjectId, { pageNum: 1, pageSize: 100, lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' }, { signal: requestController.signal }),
      loadAllAssignees(targetProjectId, requestController.signal)
    ])
    if (!isCurrentContext()) return
    shot.value = detailResponse.data
    episodes.value = Array.isArray(episodeResponse.rows) ? episodeResponse.rows : []
    members.value = Array.isArray(memberResponse) ? memberResponse : []
    historyRefreshKey.value += 1
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && isCurrentContext()) {
      errorState.value = shotErrorState(error, '镜头详情加载失败')
    }
  } finally {
    if (controller === requestController && generation === loadGeneration) loading.value = false
  }
}

function openEditDialog() {
  if (loading.value || archiving.value || !shot.value) return
  editContext.value = Object.freeze({ projectId: projectId.value, shotId: shotId.value, operationGeneration: ++operationGeneration })
  showEdit.value = true
}

function closeEditDialog() {
  showEdit.value = false
  editContext.value = null
}

function openAssignDialog() {
  if (loading.value || archiving.value || !shot.value) return
  assignContext.value = Object.freeze({ projectId: projectId.value, shotId: shotId.value, operationGeneration: ++operationGeneration })
  showAssign.value = true
}

function closeAssignDialog() {
  showAssign.value = false
  assignContext.value = null
}

function isCurrentOperation(operationContext) {
  return (
    Number(operationContext?.projectId) === projectId.value &&
    Number(operationContext?.shotId) === shotId.value
  )
}

function isActiveOperation(activeContext, operationContext) {
  return (
    activeContext?.projectId === Number(operationContext?.projectId) &&
    activeContext?.shotId === Number(operationContext?.shotId) &&
    activeContext?.operationGeneration === Number(operationContext?.operationGeneration)
  )
}

function notifyDetachedOperation() {
  ElMessage.success('操作已完成，请返回原镜头查看最新结果。')
}

async function confirmArchive() {
  if (loading.value || archiving.value || !shot.value) return
  const targetProjectId = projectId.value
  const targetShotId = shotId.value
  const targetShot = shot.value
  if (!targetProjectId || !targetShotId) return
  try {
    await ElMessageBox.confirm('删除后镜头不再出现在活动列表；任务一旦开始将无法删除。确认继续？', `删除 ${targetShot.shotCode}`, { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' })
  } catch { return }
  if (
    loading.value ||
    projectId.value !== targetProjectId ||
    shotId.value !== targetShotId ||
    shot.value !== targetShot
  ) return
  archiving.value = true
  try {
    await archiveShot(targetProjectId, targetShotId, { lockVersion: targetShot.lockVersion })
    ElMessage.success('镜头已删除')
    if (projectId.value === targetProjectId && shotId.value === targetShotId) {
      if (props.embedded) emit('deleted', { projectId: targetProjectId, shotId: targetShotId })
      else await router.push({ path: '/shots', query: { projectId: targetProjectId } })
    }
  } catch (error) {
    const state = shotErrorState(error, '镜头删除失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409) await loadDetail()
  } finally { archiving.value = false }
}

async function handleSaved(_result, operationContext) {
  if (disposed) return
  if (!isActiveOperation(editContext.value, operationContext)) { notifyDetachedOperation(); return }
  closeEditDialog()
  if (!isCurrentOperation(operationContext)) { notifyDetachedOperation(); return }
  ElMessage.success('镜头已更新')
  await loadDetail()
  emit('changed', { projectId: projectId.value, shotId: shotId.value })
}

async function handleAssigned(_result, operationContext) {
  if (disposed) return
  if (!isActiveOperation(assignContext.value, operationContext)) { notifyDetachedOperation(); return }
  closeAssignDialog()
  if (!isCurrentOperation(operationContext)) { notifyDetachedOperation(); return }
  ElMessage.success(operationContext.wasReassign ? '镜头任务已改派' : '镜头任务已创建并分配')
  await loadDetail()
  emit('changed', { projectId: projectId.value, shotId: shotId.value })
}

onMounted(loadDetail)
watch(
  () => [props.targetProjectId, props.targetShotId, route.params.projectId, route.params.shotId],
  loadDetail
)
onBeforeUnmount(() => { disposed = true; loadGeneration += 1; controller?.abort() })
</script>

<template>
  <section class="sg-page shot-detail-page" :class="{ 'shot-detail-page--embedded': embedded }">
    <el-button v-if="!embedded" class="back-link" link :icon="ArrowLeft" @click="router.push({ path: '/shots', query: { projectId } })">返回镜头列表</el-button>
    <ProjectStatePanel v-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadDetail" />
    <el-card v-else-if="loading && !shot" class="detail-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="8" /></el-card>
    <template v-else-if="shot">
      <el-card class="shot-overview" shadow="never">
        <header class="shot-hero">
          <ProtectedThumbnail class="shot-hero__thumbnail" :thumbnail="shot.thumbnail" :video="shot.proxyMedia" :alt="`${shot.shotCode} 缩略图`" />
          <div class="shot-hero__main"><p class="sg-eyebrow">{{ shot.episodeCode }} / {{ shot.sceneCode }}</p><div><h2>{{ shot.shotCode }}</h2><el-tag class="shot-status-tag" :class="shotStatusTagClass(shot.status)" :type="tagTypeFromTone(shotStatusMeta(shot.status).tone)" size="small" effect="light" round>{{ shotStatusMeta(shot.status).label }}</el-tag></div><small>本场第 {{ shot.sequencePosition }} 镜 · {{ formatShotDuration(shot.durationMs) }}</small></div>
          <div class="shot-hero__actions"><el-button :icon="Refresh" :loading="loading" :disabled="archiving" @click="loadDetail">刷新</el-button><el-button v-if="allowedActions.has('task.assign')" :icon="UserFilled" :disabled="loading || archiving" @click="openAssignDialog">{{ shot.task ? '改派任务' : '分配任务' }}</el-button><el-button v-if="allowedActions.has('shot.edit')" :icon="Edit" :disabled="loading || archiving" @click="openEditDialog">编辑镜头</el-button><el-button v-if="allowedActions.has('shot.archive')" type="danger" plain :icon="Lock" :loading="archiving" :disabled="loading" @click="confirmArchive">删除</el-button></div>
        </header>
        <section class="shot-overview__production" aria-labelledby="shot-production-title">
          <header>
            <div><p class="sg-eyebrow">PRODUCTION</p><h3 id="shot-production-title">制作信息</h3></div>
            <el-tag v-if="shot.directoryStatus === 'failed'" :type="tagTypeFromTone(directoryStatusMeta(shot.directoryStatus).tone)" size="small" effect="plain" round>{{ directoryStatusMeta(shot.directoryStatus).label }}</el-tag>
          </header>
          <ShotProductionInfo :shot="shot" />
        </section>
      </el-card>

      <ProductionHistoryPanel
        :project-id="projectId"
        :subject-id="shotId"
        subject-type="shot"
        :refresh-key="historyRefreshKey"
      />

      <section class="detail-grid">
        <el-card class="detail-card" shadow="never"><p class="sg-eyebrow">TASK</p><h3>镜头视频任务</h3><template v-if="shot.task"><div class="task-person"><strong>{{ shotAssigneeName(shot.task.assignee, members) }}</strong></div><el-descriptions class="compact-fields" :column="2" border><el-descriptions-item label="任务状态"><el-tag :type="tagTypeFromTone(taskStatusMeta(shot.task.taskStatus, 'shot_video').tone)" size="small" effect="light" round>{{ taskStatusMeta(shot.task.taskStatus, 'shot_video').label }}</el-tag></el-descriptions-item><el-descriptions-item label="优先级"><el-tag :type="tagTypeFromTone(taskPriorityMeta(shot.task.priority).tone)" size="small" effect="plain" round>{{ taskPriorityMeta(shot.task.priority).label }}</el-tag></el-descriptions-item><el-descriptions-item label="截止日期">{{ shot.task.dueDate || '未设置' }}</el-descriptions-item></el-descriptions></template><el-empty v-else class="detail-empty" :image-size="48" description="尚未分配主制作人" /></el-card>

        <el-card class="detail-card" shadow="never"><p class="sg-eyebrow">VERSION</p><h3>最新版本与反馈</h3><template v-if="shot.latestVersion"><strong class="version-number">{{ shot.latestVersion.versionNumber }}</strong><p>{{ shot.latestVersion.businessFileName }}</p><el-tag :type="tagTypeFromTone(taskVersionStatusMeta(shot.latestVersion.status).tone)" size="small" effect="light" round>{{ taskVersionStatusMeta(shot.latestVersion.status).label }}</el-tag></template><el-empty v-else class="detail-empty" :image-size="48" description="尚未提交正式版本" /><blockquote v-if="shot.latestFeedback">{{ shot.latestFeedback.content }}<small>{{ formatShotDateTime(shot.latestFeedback.createTime) }}</small></blockquote></el-card>

        <el-card class="detail-card detail-card--wide" shadow="never"><p class="sg-eyebrow">ASSETS</p><h3>关联资产</h3><div v-if="shot.assets.length" class="asset-tags"><el-tag v-for="asset in shot.assets" :key="asset.assetId" :type="tagTypeFromTone(String(asset.assetType || '').toLowerCase())" size="small" effect="plain" round>{{ asset.assetType === 'Environment' ? '场景' : asset.assetType === 'Character' ? '角色' : '道具' }} · {{ asset.assetName }}</el-tag></div><el-empty v-else class="detail-empty" :image-size="48" description="尚未关联正式资产；未知场景会保留为待匹配需求" /></el-card>

        <el-card class="detail-card detail-card--wide" shadow="never"><p class="sg-eyebrow">AUDIT</p><h3>审计摘要</h3><el-descriptions class="compact-fields" :column="4" border><el-descriptions-item label="创建人">{{ shot.createBy }}</el-descriptions-item><el-descriptions-item label="创建时间">{{ formatShotDateTime(shot.createTime) }}</el-descriptions-item><el-descriptions-item label="更新人">{{ shot.updateBy }}</el-descriptions-item><el-descriptions-item label="更新时间">{{ formatShotDateTime(shot.updateTime) }}</el-descriptions-item></el-descriptions></el-card>
      </section>

      <ShotFormDialog v-if="showEdit && editContext" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :episodes="episodes" :shot="shot" @close="closeEditDialog" @saved="handleSaved" @refresh="loadDetail" />
      <ShotAssignDialog v-if="showAssign && assignContext" :project-id="assignContext.projectId" :operation-generation="assignContext.operationGeneration" :shot="shot" :members="members" @close="closeAssignDialog" @assigned="handleAssigned" @refresh="loadDetail" />
    </template>
  </section>
</template>

<style scoped>
.shot-detail-page {
  display: grid;
  gap: 18px;
  color: var(--sg-text);
}

.shot-detail-page--embedded {
  padding: 0;
}

.back-link {
  display: inline-flex;
  width: max-content;
  gap: 7px;
  align-items: center;
  padding: 0;
  color: var(--sg-text-muted);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.back-link:hover {
  color: var(--sg-text);
}

.detail-loading {
  display: grid;
  min-height: 360px;
  color: var(--sg-text-muted);
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-lg);
  place-items: center;
}

.detail-loading.el-card {
  display: block;
  padding: 0;
}

.detail-loading:deep(.el-card__body) {
  width: 100%;
  box-sizing: border-box;
  padding: 30px;
}

.shot-overview.el-card {
  overflow: hidden;
  background: var(--sg-surface);
  border-color: var(--sg-border);
  border-radius: var(--sg-radius-lg);
}

.shot-overview:deep(.el-card__body) {
  padding: 0;
}

.shot-hero {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) auto;
  gap: 22px;
  align-items: center;
  padding: 22px;
  background:
    linear-gradient(135deg, var(--sg-accent-soft), transparent 38%),
    var(--sg-surface);
}

.shot-hero__thumbnail {
  display: grid;
  overflow: hidden;
  aspect-ratio: 16 / 9;
  color: var(--sg-on-media);
  font-size: 30px;
  background: var(--sg-media-stage-bg);
  border-radius: 12px;
  place-items: center;
}

.shot-hero__thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shot-hero__main > div {
  display: flex;
  gap: 10px;
  align-items: center;
}

.shot-hero h2,
.shot-hero p {
  margin: 0;
}

.shot-hero h2 {
  font-size: 27px;
}

.shot-hero__main small {
  display: block;
  margin-top: 8px;
  color: var(--sg-text-muted);
}

.shot-hero__actions {
  display: flex;
  max-width: 310px;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.shot-overview__production {
  padding: 18px 22px 22px;
  border-top: 1px solid var(--sg-border);
}

.shot-overview__production > header {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.shot-overview__production h3,
.shot-overview__production p {
  margin: 0;
}

.shot-overview__production h3 {
  margin-top: 2px;
  font-size: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.detail-card.el-card {
  padding: 0;
  background: var(--sg-surface);
  border-color: var(--sg-border);
  border-radius: var(--sg-radius-md);
}

.detail-card:deep(.el-card__body) {
  padding: 21px;
}

.detail-card--wide {
  grid-column: 1 / -1;
}

.detail-card header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.detail-card h3,
.detail-card p {
  margin: 0;
}

.detail-card h3 {
  margin-bottom: 17px;
  font-size: 17px;
}

.compact-fields.el-descriptions {
  display: block;
  margin: 0;
  overflow: hidden;
  background: transparent;
}

.compact-fields.el-descriptions {
  border-radius: 9px;
}

.compact-fields:deep(.el-descriptions__body),
.compact-fields:deep(.el-descriptions__table) {
  background: transparent;
}

.compact-fields:deep(.el-descriptions__cell) {
  padding: 13px !important;
  background: var(--sg-surface-raised) !important;
  border-color: var(--sg-border) !important;
}

.compact-fields:deep(.el-descriptions__label) {
  color: var(--sg-text-muted) !important;
  font-size: 10px;
}

.compact-fields:deep(.el-descriptions__content) {
  color: var(--sg-text-secondary) !important;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  word-break: break-word;
}

.task-person {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--sg-accent-soft);
  border-radius: 9px;
}

.detail-empty.el-empty {
  min-height: 138px;
  padding: 10px;
  color: var(--sg-text-muted);
  background: var(--sg-fill-subtle);
  border: 1px dashed var(--sg-border);
  border-radius: 10px;
}

.version-number {
  display: block;
  color: var(--sg-accent);
  font-size: 24px;
}

.detail-card:deep(.el-card__body) > .version-number + p {
  margin: 8px 0;
  overflow-wrap: anywhere;
  color: var(--sg-text-secondary);
  font-size: 11px;
}

.detail-card blockquote {
  margin: 16px 0 0;
  padding: 12px;
  color: var(--sg-text-secondary);
  font-size: 12px;
  background: var(--sg-fill-subtle);
  border-left: 2px solid var(--sg-accent);
}

blockquote small {
  display: block;
  margin-top: 7px;
  color: var(--sg-text-muted);
}

.asset-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 980px) {
  .shot-hero {
    grid-template-columns: 140px 1fr;
  }

  .shot-hero__actions {
    grid-column: 1 / -1;
    max-width: none;
    justify-content: flex-start;
  }
}

@media (max-width: 650px) {
  .shot-hero,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .shot-hero__thumbnail {
    max-width: 240px;
  }

  .detail-card--wide {
    grid-column: auto;
  }

}
</style>
