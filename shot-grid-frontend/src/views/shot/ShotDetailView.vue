<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Lock, Refresh, UserFilled } from '@element-plus/icons-vue'

import { archiveShot, getEpisodePage, getShotDetail, listShotAssignees } from '@/api/shot-grid/shots'
import { assertPositiveId } from '@/api/shot-grid/projects'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import { directoryStatusMeta, formatShotDateTime, formatShotDuration, shotErrorState, shotStatusMeta } from '@/views/shot/shotPresentation'

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
    errorState.value = { title: '镜头地址无效', message: '项目 ID 和镜头 ID 必须为正整数。', retryable: false }
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
  ElMessage.success('操作已完成；当前镜头未自动刷新。')
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
    <button v-if="!embedded" class="back-link" type="button" @click="router.push({path:'/shots',query:{projectId}})"><el-icon><ArrowLeft /></el-icon> 返回镜头列表</button>
    <ProjectStatePanel v-if="errorState" :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadDetail" />
    <div v-else-if="loading && !shot" class="detail-loading">正在加载镜头详情…</div>
    <template v-else-if="shot">
      <header class="shot-hero">
        <ProtectedThumbnail class="shot-hero__thumbnail" :thumbnail="shot.thumbnail" :video="shot.proxyMedia" :alt="`${shot.shotCode} 缩略图`" />
        <div class="shot-hero__main"><p class="sg-eyebrow">{{ shot.episodeCode }} / {{ shot.sceneCode }}</p><div><h2>{{ shot.shotCode }}</h2><span class="status-chip" :data-tone="shotStatusMeta(shot.status).tone">{{ shotStatusMeta(shot.status).label }}</span></div><p>{{ shot.description }}</p><small>成片顺序 {{ shot.sortOrder }} · {{ formatShotDuration(shot.durationMs) }}</small></div>
        <div class="shot-hero__actions"><el-button :icon="Refresh" :loading="loading" :disabled="archiving" @click="loadDetail">刷新</el-button><el-button v-if="allowedActions.has('task.assign')" :icon="UserFilled" :disabled="loading || archiving" @click="openAssignDialog">{{ shot.task ? '改派任务' : '分配任务' }}</el-button><el-button v-if="allowedActions.has('shot.edit')" :icon="Edit" :disabled="loading || archiving" @click="openEditDialog">编辑镜头</el-button><el-button v-if="allowedActions.has('shot.archive')" type="danger" plain :icon="Lock" :loading="archiving" :disabled="loading" @click="confirmArchive">删除</el-button></div>
      </header>

      <section class="detail-grid">
        <article class="detail-card detail-card--wide"><header><div><p class="sg-eyebrow">PRODUCTION</p><h3>制作信息</h3></div><span :data-tone="directoryStatusMeta(shot.directoryStatus).tone">{{ directoryStatusMeta(shot.directoryStatus).label }}</span></header><dl class="detail-fields"><div><dt>景别</dt><dd>{{ shot.shotSize || '—' }}</dd></div><div><dt>机位</dt><dd>{{ shot.cameraPosition || '—' }}</dd></div><div><dt>镜头运动</dt><dd>{{ shot.cameraMovement || '—' }}</dd></div><div><dt>焦段</dt><dd>{{ shot.focalLength || '—' }}</dd></div><div><dt>台词 / 对白</dt><dd>{{ shot.dialogue || '—' }}</dd></div><div><dt>音效</dt><dd>{{ shot.soundEffect || '—' }}</dd></div><div><dt>色调参考</dt><dd>{{ shot.colorReference || '—' }}</dd></div><div><dt>备注</dt><dd>{{ shot.remark || '—' }}</dd></div></dl></article>

        <article class="detail-card"><p class="sg-eyebrow">TASK</p><h3>唯一镜头视频任务</h3><template v-if="shot.task"><div class="task-person"><strong>{{ shot.task.assignee.nickName }}</strong></div><dl class="compact-fields"><div><dt>任务状态</dt><dd>{{ shotStatusMeta(shot.status).label }}</dd></div><div><dt>优先级</dt><dd>{{ {low:'低',normal:'普通',high:'高',urgent:'紧急'}[shot.task.priority] }}</dd></div><div><dt>截止日期</dt><dd>{{ shot.task.dueDate || '未设置' }}</dd></div><div><dt>任务锁版本</dt><dd>{{ shot.task.lockVersion }}</dd></div></dl></template><div v-else class="detail-empty">尚未分配主制作人，因此没有生成任务。</div></article>

        <article class="detail-card"><p class="sg-eyebrow">VERSION</p><h3>最新版本与反馈</h3><template v-if="shot.latestVersion"><strong class="version-number">{{ shot.latestVersion.versionNumber }}</strong><p>{{ shot.latestVersion.businessFileName }}</p><span>{{ shot.latestVersion.status === 'final' ? '最终版本' : shot.latestVersion.status === 'rejected' ? '已退回' : '待审核' }}</span></template><div v-else class="detail-empty">尚未提交正式版本。</div><blockquote v-if="shot.latestFeedback">{{ shot.latestFeedback.content }}<small>{{ formatShotDateTime(shot.latestFeedback.createTime) }}</small></blockquote></article>

        <article class="detail-card detail-card--wide"><p class="sg-eyebrow">ASSETS</p><h3>关联资产</h3><div v-if="shot.assets.length" class="asset-tags"><span v-for="asset in shot.assets" :key="asset.assetId" :data-type="asset.assetType">{{ asset.assetType === 'Environment' ? '场景' : asset.assetType === 'Character' ? '角色' : '道具' }} · {{ asset.assetName }}</span></div><div v-else class="detail-empty">尚未关联正式资产；镜头导入中的未知场景会保留为待匹配需求，不会隐式创建资产。</div></article>

        <article class="detail-card detail-card--wide"><p class="sg-eyebrow">AUDIT</p><h3>审计摘要</h3><dl class="compact-fields compact-fields--four"><div><dt>创建人</dt><dd>{{ shot.createBy }}</dd></div><div><dt>创建时间</dt><dd>{{ formatShotDateTime(shot.createTime) }}</dd></div><div><dt>更新人</dt><dd>{{ shot.updateBy }}</dd></div><div><dt>更新时间</dt><dd>{{ formatShotDateTime(shot.updateTime) }}</dd></div></dl></article>
      </section>

      <ShotFormDialog v-if="showEdit && editContext" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :episodes="episodes" :members="members" :shot="shot" @close="closeEditDialog" @saved="handleSaved" @refresh="loadDetail" />
      <ShotAssignDialog v-if="showAssign && assignContext" :project-id="assignContext.projectId" :operation-generation="assignContext.operationGeneration" :shot="shot" :members="members" @close="closeAssignDialog" @assigned="handleAssigned" @refresh="loadDetail" />
    </template>
  </section>
</template>

<style scoped>
.shot-detail-page{display:grid;gap:18px}.shot-detail-page--embedded{padding:0}.back-link{display:inline-flex;width:max-content;gap:7px;align-items:center;padding:0;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0}.back-link:hover{color:var(--sg-text)}.detail-loading{display:grid;min-height:360px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg);place-items:center}.shot-hero{display:grid;grid-template-columns:180px minmax(0,1fr) auto;gap:22px;align-items:center;padding:22px;background:linear-gradient(135deg,rgba(255,182,87,.07),transparent 38%),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg)}.shot-hero__thumbnail{display:grid;overflow:hidden;aspect-ratio:16/9;color:var(--sg-text-muted);font-size:30px;background:linear-gradient(135deg,#202630,#11151b);border-radius:12px;place-items:center}.shot-hero__thumbnail img{width:100%;height:100%;object-fit:cover}.shot-hero__main>div{display:flex;gap:10px;align-items:center}.shot-hero h2,.shot-hero p{margin:0}.shot-hero h2{font-size:27px}.shot-hero__main>p:not(.sg-eyebrow){margin-top:8px;color:var(--sg-text-secondary);font-size:13px;line-height:1.6}.shot-hero__main small{display:block;margin-top:8px;color:var(--sg-text-muted)}.shot-hero__actions{display:flex;max-width:310px;gap:8px;justify-content:flex-end;flex-wrap:wrap}.status-chip{padding:5px 8px;font-size:10px;background:rgba(255,255,255,.05);border-radius:999px}.status-chip[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.status-chip[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.status-chip[data-tone=danger]{color:var(--sg-danger);background:rgba(255,107,107,.09)}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.detail-card{padding:21px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.detail-card--wide{grid-column:1/-1}.detail-card header{display:flex;align-items:flex-start;justify-content:space-between}.detail-card h3,.detail-card p{margin:0}.detail-card h3{margin-bottom:17px;font-size:17px}.detail-card header span{font-size:11px}.detail-card header span[data-tone=success]{color:var(--sg-success)}.detail-card header span[data-tone=danger]{color:var(--sg-danger)}.detail-card header span[data-tone=warning]{color:var(--sg-accent)}.detail-fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:0;overflow:hidden;background:var(--sg-border);border:1px solid var(--sg-border);border-radius:10px}.detail-fields div,.compact-fields div{padding:13px;background:rgba(13,16,21,.92)}dt{color:var(--sg-text-muted);font-size:10px}dd{margin:5px 0 0;color:var(--sg-text-secondary);font-size:12px;white-space:pre-wrap}.task-person{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;padding:12px;background:var(--sg-accent-soft);border-radius:9px}.task-person span{color:var(--sg-accent);font-size:11px}.compact-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:0;overflow:hidden;background:var(--sg-border);border-radius:9px}.compact-fields--four{grid-template-columns:repeat(4,minmax(0,1fr))}.detail-empty{padding:22px;color:var(--sg-text-muted);font-size:12px;text-align:center;background:rgba(255,255,255,.02);border:1px dashed var(--sg-border);border-radius:10px}.version-number{display:block;color:var(--sg-accent);font-size:24px}.detail-card>.version-number+p{margin:8px 0;overflow-wrap:anywhere;color:var(--sg-text-secondary);font-size:11px}.detail-card blockquote{margin:16px 0 0;padding:12px;color:var(--sg-text-secondary);font-size:12px;background:rgba(255,255,255,.025);border-left:2px solid var(--sg-accent)}blockquote small{display:block;margin-top:7px;color:var(--sg-text-muted)}.asset-tags{display:flex;gap:8px;flex-wrap:wrap}.asset-tags span{padding:7px 9px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.04);border-radius:8px}.asset-tags span[data-type=Environment]{color:#80bfff;background:rgba(128,191,255,.08)}.asset-tags span[data-type=Character]{color:var(--sg-accent);background:var(--sg-accent-soft)}@media(max-width:980px){.shot-hero{grid-template-columns:140px 1fr}.shot-hero__actions{grid-column:1/-1;max-width:none;justify-content:flex-start}.detail-fields{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.shot-hero,.detail-grid{grid-template-columns:1fr}.shot-hero__thumbnail{max-width:240px}.detail-card--wide{grid-column:auto}.detail-fields,.compact-fields,.compact-fields--four{grid-template-columns:1fr}}
</style>
