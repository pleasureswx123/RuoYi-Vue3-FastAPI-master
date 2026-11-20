<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import { approvedVersion, finalDeliveryFiles } from '@/components/version/finalPresentation'
import NasOpenButton from '@/components/NasOpenButton.vue'
import FinalVersionTag from '@/components/version/FinalVersionTag.vue'
import { candidateFolderPath, requestLocalDemoFolder } from '@/utils/folderOpener'
import { getShotDetail } from '@/api/shot-grid/shots'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import { formatVersionDateTime, versionStatusMeta } from '@/components/version/versionPresentation'
import ReviewCandidateThumbnail from '@/views/review/components/ReviewCandidateThumbnail.vue'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ProtectedVersionPreview from '@/components/version/ProtectedVersionPreview.vue'
import ShotTaskFeedbackDialog from '@/components/version/ShotTaskFeedbackDialog.vue'
const versionSelectForm = ref(null)
const ShotFeedbackPanel = defineAsyncComponent(() => import('./ShotFeedbackPanel.vue'))
const props = defineProps({ previewOnLoad: Boolean, projectId: { type: Number, required: true }, shotId: { type: Number, default: 0 }, assetId: { type: Number, default: 0 }, assetItemId: { type: Number, default: 0 } })
const emit = defineEmits(['updated', 'feedback', 'work'])
const AssetRelationsPanel = defineAsyncComponent(() => import('@/views/asset/components/AssetRelationsPanel.vue'))
const relations = ref(null)
const isAsset = computed(() => props.assetItemId > 0)
const entityLabel = computed(() => isAsset.value ? '制作分项' : '镜头')
const asset = ref(null)
const directFeedback = ref(null)
const canFeedback = computed(() => isAsset.value ? allowed('shotgrid:note:add') && allowed('shotgrid:version:query') && ['task.review', 'task.appendIssue'].some(action => shot.value?.allowedActions?.includes(action)) : task.value?.allowedActions?.includes('task.feedback'))
async function addFeedback() {
  const context = scopeKey.value
  const versionId = selectedVersionId.value
  if (!canFeedback.value || Number(task.value?.latestVersion?.versionId) !== versionId || !(await canLeave())) return
  if (disposed || context !== scopeKey.value || selectedVersionId.value !== versionId) return
  if (isAsset.value) {
    emit('feedback', { asset: asset.value, item: shot.value, action: shot.value.allowedActions.includes('task.review') ? 'review' : 'append' })
    return
  }
  directFeedback.value?.open(props.projectId, [{ shotId: props.shotId, taskId: taskId.value, versionId,
    label: `${shot.value.episodeCode} / ${shot.value.sceneCode} / ${shot.value.shotCode} · ${version.value?.versionNumber || ''}`
  }], () => !disposed && context === scopeKey.value && selectedVersionId.value === versionId)
}
async function feedbackClosed(result) {
  if (result.changed || result.uncertain) { await reload(); emit('updated') }
}
const session = useSessionStore()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const shot = ref(null)
const task = ref(null)
const versions = ref([])
const selectedVersionId = ref(null)
const version = ref(null)
const candidateId = ref(null)
const tab = ref('results')
const showHistory = ref(false)
const approved = computed(() => approvedVersion(shot.value) || versions.value.find(item => item.versionStatus === 'final') || null)
const approvedId = computed(() => Number(approved.value?.versionId) || null)
const visibleVersions = computed(() => approvedId.value && !showHistory.value ? versions.value.filter(item => Number(item.versionId) === approvedId.value) : versions.value)
const isApproved = computed(() => Number(version.value?.versionId) === approvedId.value)
const delivery = computed(() => isApproved.value && Number(version.value?.finalDelivery?.versionId) === selectedVersionId.value ? version.value.finalDelivery : null)
const finalRow = computed(() => ({ ...shot.value, approvedVersion: approved.value ? { ...approved.value, ...(delivery.value ? { deliveryStatus: delivery.value.deliveryStatus, approvedTime: delivery.value.approvedTime } : {}), ...(isApproved.value && version.value ? { versionStatus: version.value.versionStatus } : {}) } : null }))
const finalOutputs = computed(() => isApproved.value ? candidates.value.filter(item => (delivery.value ? finalDeliveryFiles(delivery.value).some(file => Number(file.candidateId) === Number(item.candidateId)) : Number(item.candidateId) === Number(version.value?.selectedCandidateId))) : candidates.value)
const deliveryLabel = computed(() => delivery.value?.deliveryStatus === 'published' ? '定稿已归档' : delivery.value?.deliveryStatus === 'failed' ? '定稿整理失败，请联系管理人员处理' : ['pending', 'publishing'].includes(delivery.value?.deliveryStatus) ? '定稿整理中' : '归档状态待核对')
function finalFolder(output) {
  const file = output?.files?.find(item => item.role === 'review_media')
  const final = finalDeliveryFiles(delivery.value).find(item => Number(item.candidateId) === Number(output.candidateId))
  if (!file || !final || delivery.value.deliveryStatus !== 'published') return null
  const relativePath = final.finalNasRelativePath || (final.businessFileName ? `FINAL/${final.businessFileName}` : '')
  const finalPath = relativePath.replaceAll('/', '\\')
  const suffix = finalPath?.match(/(?:^|\\)(FINAL\\.+)$/i)?.[1]
  if (!suffix) return null
  return { ...output, files: [{ ...file, folderRelativePath: file.folderRelativePath ? `${file.folderRelativePath}\\FINAL` : '', nasPath: file.nasPath ? `${candidateFolderPath([file])}\\${suffix}` : '' }] }
}
function openFinalFolder(output) {
  const target = finalFolder(output)
  if (target) openFolder(target, true)
}

const loading = ref(false)
const versionLoading = ref(false)
const moreLoading = ref(false)
const error = ref('')
const versionError = ref('')
const moreError = ref('')
const taskError = ref('')
const hasMore = ref(false)
const versionPage = ref(1)
const feedback = ref(null)
const mediaVisible = ref(false)
const folderPreview = ref(null)
const desktop = window.__SHOTGRID_DESKTOP__ === true
const localFolderDemo = import.meta.env.DEV && ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname)
const folderButtonLabel = localFolderDemo ? '打开所在文件夹（本地模拟）' : '打开所在文件夹（演示）'
const versionIndex = computed(() => versions.value.findIndex(item => Number(item.versionId) === selectedVersionId.value))
function folderReason(output) {
  if (!canDownload.value) return '当前账号没有文件访问权限'
  if (!output.files?.some(file => file.role === 'review_media' && file.nasPath)) return '尚未提供原文件 NAS 路径'
  return candidateFolderPath(output.files) ? '' : '原文件路径不符合当前 NAS 配置，请联系管理员核对'
}
function openFolder(output, final = false) {
  if (!version.value || versionLoading.value || !canDownload.value) return
  if (localFolderDemo) {
    try {
      const relative = output.files?.find(file => file.role === 'review_media')?.folderRelativePath
      if (final && !relative) { ElMessage.warning('缺少定稿目录信息，请刷新或联系管理人员'); return }
      const opened = requestLocalDemoFolder(props.projectId, isAsset.value ? props.assetItemId : props.shotId, selectedVersionId.value, Number(output.candidateId || 0), isAsset.value ? props.assetId : 0, ...(relative ? [relative] : []))
      if (opened) ElMessage.info('已请求打开本地模拟文件夹，请允许浏览器打开 Shot Grid。文件夹内为演示副本，不是正式成果。')
      else ElMessage.warning('镜头或版本编号无效，请刷新后重试')
    } catch { ElMessage.warning('未能请求本地打开器，请检查本机是否安装') }
    return
  }
  // 非本机开发页面继续使用只读位置预览，不开放本地磁盘路径。
  folderPreview.value = { name: outputName(output), versionNumber: version.value.versionNumber,
    path: candidateFolderPath(output.files), reason: folderReason(output) }
}
function reviewFile(output) {
  return output.files?.find(item => item.role === 'review_media')
}
function outputName(output) {
  const file = reviewFile(output)
  return file?.businessFileName || file?.originalName || file?.name || output.candidateNumber || '成果文件'
}
async function toggleHistory() {
  if (!showHistory.value) { showHistory.value = true; return }
  await selectVersion(approvedId.value)
  if (selectedVersionId.value === approvedId.value) showHistory.value = false
}
async function adjacentVersion(offset) {
  if (versionLoading.value) return
  const item = versions.value[versionIndex.value + offset]
  if (item) await selectVersion(item.versionId)
}
let controller = null
let versionController = null
let moreController = null
let generation = 0
let disposed = false
const taskId = computed(() => Number(shot.value?.taskId || shot.value?.task?.taskId) || null)
const canList = computed(() => allowed('shotgrid:version:list'))
const canQuery = computed(() => allowed('shotgrid:version:query'))
const canDownload = computed(() => allowed('shotgrid:file:download'))
const candidates = computed(() => version.value?.candidates || [])
const candidate = computed(() => candidates.value.find(item => Number(item.candidateId) === candidateId.value) || candidates.value[0] || null)
const previewVersion = computed(() => version.value && candidate.value ? { ...version.value, files: candidate.value.files || [] } : version.value)
const referenceFiles = computed(() => [...new Map([...(shot.value?.referenceFiles || []), ...(task.value?.referenceFiles || [])].filter(file => /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name || file.fileName || file.originalName || '') || file.contentType?.startsWith('image/')).map(file => [file.fileId, file])).values()])
const referenceTexts = computed(() => [...new Set([asset.value?.description, shot.value?.description, shot.value?.referenceDescription, task.value?.requirements, task.value?.referenceDescription].filter(value => value?.trim()))])
const scopeKey = computed(() => `${props.projectId}:${isAsset.value ? `asset:${props.assetId}:${props.assetItemId}` : `shot:${props.shotId}`}`)
const permissionsKey = computed(() => session.permissions.join('|'))
const dirty = computed(() => Boolean(relations.value?.dirty || feedback.value?.dirty || feedback.value?.sending))
async function canLeave() {
  if (relations.value && !await relations.value.canLeave()) return false
  if (feedback.value?.sending) { ElMessage.warning('评论正在保存，请稍候'); return false }
  if (feedback.value?.dirty) {
    try { await ElMessageBox.confirm('评论还没有发送，离开后会丢失本次输入。确定离开？', '未发送的评论', { type: 'warning' }) }
    catch { return false }
  }
  return true
}
async function previewCandidate(id) {
  candidateId.value = Number(id)
  mediaVisible.value = true
}
function current(request, targetGeneration) {
  return !disposed && !request.signal.aborted && generation === targetGeneration
}
function assertTask(detail) {
  if (isAsset.value) {
    if (Number(detail?.taskId) !== taskId.value || Number(detail?.project?.projectId) !== props.projectId || detail?.target?.targetType !== 'asset_item' || Number(detail.target.assetId) !== props.assetId || Number(detail.target.assetItemId ?? detail.target.targetId) !== props.assetItemId) throw new Error('任务与当前制作分项不匹配，请刷新')
    return detail
  }
  if (Number(detail?.taskId) !== taskId.value || Number(detail?.project?.projectId) !== props.projectId ||
      detail?.target?.targetType !== 'shot' || Number(detail?.target?.shotId ?? detail?.target?.targetId) !== props.shotId) throw new Error('任务与当前镜头不匹配，请刷新')
  return detail
}
function assertVersion(detail, id) {
  if (Number(detail?.versionId) !== Number(id) || Number(detail?.taskId) !== taskId.value || Number(detail?.projectId) !== props.projectId) throw new Error('成果版本与当前任务不匹配，请刷新')
  return detail
}
function setVersion(detail) {
  if (JSON.stringify(version.value) === JSON.stringify(detail)) return
  const previousCandidate = Number(version.value?.versionId) === Number(detail.versionId) ? candidateId.value : null
  version.value = detail
  candidateId.value = detail.candidates?.some(item => Number(item.candidateId) === previousCandidate) ? previousCandidate : Number((isApproved.value && detail.finalDelivery?.candidateId) || detail.selectedCandidateId || detail.candidates?.find(item => item.isSelected)?.candidateId || detail.candidates?.[0]?.candidateId) || null
}
function validateVersions(rows) {
  if (rows.some(item => Number(item.taskId) !== taskId.value || Number(item.projectId) !== props.projectId)) throw new Error('版本列表与当前任务不匹配，请刷新')
  return rows
}
async function selectVersion(id) {
  const expectedGeneration = generation
  if (selectedVersionId.value && !(await canLeave())) return
  if (disposed || generation !== expectedGeneration) return
  versionController?.abort()
  version.value = null
  candidateId.value = null
  versionError.value = ''
  selectedVersionId.value = Number(id)
  if (approvedId.value && Number(id) !== approvedId.value) showHistory.value = true
  if (!canQuery.value || !id) return
  const request = new AbortController()
  versionController = request
  const targetGeneration = generation
  versionLoading.value = true
  try {
    const response = await getVersionDetail(id, { signal: request.signal })
    if (current(request, targetGeneration) && versionController === request) {
      const detail = assertVersion(response.data, id)
      setVersion(detail)
      if (!versions.value.some(item => Number(item.versionId) === Number(id))) versions.value.push(detail)
    }
  } catch (err) {
    if (current(request, targetGeneration)) versionError.value = err.message || '成果加载失败'
  } finally {
    if (versionController === request) versionLoading.value = false
  }
}
async function reload() {
  controller?.abort(); versionController?.abort(); moreController?.abort()
  const targetGeneration = ++generation
  const request = new AbortController()
  controller = request
  shot.value = null; asset.value = null; task.value = null; versions.value = []; version.value = null
  showHistory.value = false
  selectedVersionId.value = null; candidateId.value = null; versionPage.value = 1; hasMore.value = false
  error.value = ''; taskError.value = ''; moreError.value = ''; versionError.value = ''
  versionLoading.value = false; moreLoading.value = false
  loading.value = true
  try {
    if (!allowed(isAsset.value ? 'shotgrid:asset:query' : 'shotgrid:shot:query')) throw new Error(`当前账号没有${entityLabel.value}详情权限`)
    const response = await (isAsset.value ? getAssetDetail(props.projectId, props.assetId, { signal: request.signal }) : getShotDetail(props.projectId, props.shotId, { signal: request.signal }))
    if (!current(request, targetGeneration)) return
    if (isAsset.value) {
      const detail = response.data
      const item = detail?.items?.find(row => Number(row.assetItemId) === props.assetItemId)
      if (Number(detail?.projectId) !== props.projectId || Number(detail?.assetId) !== props.assetId || !item || Number(item.projectId) !== props.projectId || Number(item.assetId) !== props.assetId) throw new Error('制作分项归属已变化，请重新选择')
      asset.value = detail; shot.value = item
    } else {
      if (Number(response.data?.projectId) !== props.projectId || Number(response.data?.shotId) !== props.shotId) throw new Error('镜头归属已变化，请重新选择')
      shot.value = response.data
    }
    if (!taskId.value) return
    const [taskResult, versionsResult] = await Promise.allSettled([
      allowed('shotgrid:task:query') ? getTaskDetail(taskId.value, { signal: request.signal }) : Promise.resolve(null),
      canList.value ? getTaskVersions(taskId.value, { pageNum: 1, pageSize: 20, orderByColumn: 'versionNo', isAsc: 'descending' }, { signal: request.signal }) : Promise.resolve(null)
    ])
    if (!current(request, targetGeneration)) return
    if (taskResult.status === 'fulfilled' && taskResult.value) {
      task.value = assertTask(taskResult.value.data)
    } else if (taskResult.status === 'rejected') taskError.value = taskResult.reason.message || '任务状态加载失败'
    if (versionsResult.status === 'rejected') throw versionsResult.reason
    if (versionsResult.value) {
      versions.value = validateVersions(versionsResult.value.rows || [])
      hasMore.value = Boolean(versionsResult.value.hasNext)
      if (approvedId.value || versions.value.length) await selectVersion(approvedId.value || versions.value[0].versionId)
    }
  } catch (err) {
    if (current(request, targetGeneration)) error.value = err.message || '成果加载失败'
  } finally {
    if (controller === request) loading.value = false
  }
}
async function loadMoreVersions() {
  if (moreLoading.value || !hasMore.value || !canList.value || loading.value) return
  const request = new AbortController()
  moreController = request
  const targetGeneration = generation
  moreLoading.value = true; moreError.value = ''
  try {
    const response = await getTaskVersions(taskId.value, { pageNum: versionPage.value + 1, pageSize: 20, orderByColumn: 'versionNo', isAsc: 'descending' }, { signal: request.signal })
    if (!current(request, targetGeneration)) return
    const merged = new Map(versions.value.map(item => [Number(item.versionId), item]))
    validateVersions(response.rows || []).forEach(item => merged.set(Number(item.versionId), item))
    if (response.hasNext && merged.size === versions.value.length) throw new Error('版本记录已变化，请刷新后重试')
    versions.value = [...merged.values()]; versionPage.value++; hasMore.value = Boolean(response.hasNext)
  } catch (err) {
    if (current(request, targetGeneration)) moreError.value = err.message || '更多版本加载失败'
  } finally {
    if (moreController === request) moreLoading.value = false
  }
}

watch(loading, value => { if (!value && props.previewOnLoad && approvedId.value) previewApproved() })
watch([scopeKey, permissionsKey], () => { mediaVisible.value = false; folderPreview.value = null; reload() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort(); versionController?.abort(); moreController?.abort() })
async function previewApproved() {
  const expectedGeneration = generation
  const id = approvedId.value
  if (!canDownload.value || !canQuery.value || !id || !await canLeave()) return
  if (disposed || expectedGeneration !== generation) return
  await selectVersion(id)
  if (!disposed && expectedGeneration === generation && selectedVersionId.value === id && isApproved.value && !versionError.value && version.value) mediaVisible.value = true
}
defineExpose({ canLeave, reload, dirty, previewApproved })
</script>

<template>
  <section class="shot-sidebar" :aria-label="`${entityLabel}侧边栏内容`">
    <div v-if="shot" class="shot-sidebar__identity">{{ isAsset ? `${asset.assetName} / ${shot.productionItem || '未命名分项'}` : `${shot.episodeCode} / ${shot.sceneCode} / ${shot.shotCode}` }}</div>
    <el-button v-if="isAsset && task?.allowedActions?.includes('version.add')" type="primary" size="small" @click="emit('work', taskId)">提交成果</el-button>
    <el-skeleton v-if="loading" :rows="5" animated />
    <el-alert v-else-if="error" :title="error" type="error" :closable="false"><el-button @click="reload">重新加载</el-button></el-alert>
    <el-tabs v-else v-model="tab" stretch class="shot-sidebar__tabs">
      <el-tab-pane label="成果展示" name="results">
        <el-alert v-if="!canList" title="当前账号没有版本列表权限" type="info" :closable="false" />
        <el-empty v-else-if="!versions.length" :image-size="48" :description="`这个${entityLabel}还没有提交成果`" />
        <div v-if="approvedId" class="final-summary"><FinalVersionTag :row="finalRow" /><el-button size="small" text @click="toggleHistory">{{ showHistory ? '收起历史版本' : '历史版本' }}</el-button><el-button size="small" text :disabled="versionLoading" @click="selectVersion(approvedId)">刷新定稿</el-button></div>
        <el-alert v-if="approvedId && !visibleVersions.length && versionError" :title="versionError" type="error" :closable="false"><el-button @click="selectVersion(approvedId)">重试</el-button></el-alert>
        <el-alert v-if="approvedId && !visibleVersions.length && !canQuery" title="当前账号没有版本详情权限" type="info" :closable="false" />
        <el-card v-for="item in visibleVersions" :key="item.versionId" class="result-version-card" shadow="never" :class="{ 'is-selected': selectedVersionId === Number(item.versionId) }">
          <template #header><div class="result-version-header"><el-button text type="primary" :aria-label="`查看成果 ${item.versionNumber}`" @click="selectVersion(item.versionId)">{{ item.versionNumber }}</el-button><el-tag size="small" :type="tagTypeFromTone(versionStatusMeta(item.versionStatus).tone)">{{ versionStatusMeta(item.versionStatus).label }}</el-tag></div></template>
          <div class="submission-meta">{{ item.submitterName || '—' }} · {{ formatVersionDateTime(item.submittedTime) }}</div>
          <div v-if="Number(item.versionId) === approvedId" class="submission-meta">通过日期：{{ formatVersionDateTime(approved?.approvedTime || delivery?.approvedTime) }}<template v-if="isApproved"> · {{ deliveryLabel }}</template></div>
          <p class="submission-content">{{ item.changelog || '未填写提交内容' }}</p>
          <template v-if="Number(item.versionId) === selectedVersionId">
            <el-skeleton v-if="versionLoading" :rows="2" animated />
            <el-alert v-else-if="versionError" :title="versionError" type="error" :closable="false"><el-button @click="selectVersion(item.versionId)">重试</el-button></el-alert>
            <el-alert v-else-if="!canQuery" title="当前账号没有版本详情权限" type="info" :closable="false" />
            <div v-else class="candidate-grid">
              <section v-for="output in finalOutputs" :key="output.candidateId" class="candidate-file">
                <el-button class="candidate-tile" :disabled="!canDownload" :aria-label="`预览候选 ${output.candidateNumber}`" @click="previewCandidate(output.candidateId)"><ReviewCandidateThumbnail :version-id="item.versionId" :candidate="output" :can-preview="canDownload" /><span>{{ output.candidateNumber }}</span></el-button>
                <div class="candidate-file__info"><el-text size="small" class="candidate-file__name">{{ outputName(output) }}</el-text><el-text v-if="output.candidateNote" size="small">{{ output.candidateNote }}</el-text>
                  <el-button v-if="isApproved" size="small" :icon="FolderOpened" :disabled="!canDownload || !finalFolder(output) || localFolderDemo && !finalFolder(output)?.files[0]?.folderRelativePath" @click="openFinalFolder(output)">打开定稿文件夹{{ localFolderDemo ? '（本地模拟）' : '（演示）' }}</el-button>
                  <NasOpenButton v-else-if="desktop" text :project-id="projectId" :task-id="taskId" :version-id="item.versionId"
                    :file-id="reviewFile(output)?.fileId" :disabled="!canDownload || !reviewFile(output)?.fileId" />
                  <el-tooltip v-else :content="localFolderDemo ? '打开本机的模拟成果副本，不连接 NAS' : '当前为演示，仅查看位置，不会实际打开文件夹'"><span><el-button size="small" :icon="FolderOpened" :disabled="!canDownload" :aria-label="`打开 ${output.candidateNumber} 所在文件夹（${localFolderDemo ? '本地模拟' : '演示'}）`" @click="openFolder(output)">{{ folderButtonLabel }}</el-button></span></el-tooltip>
                </div>
              </section>
              <el-alert v-if="isApproved && !finalOutputs.length" title="定稿文件信息暂不可用，请刷新后重试" type="warning" :closable="false" /><template v-if="!isApproved && !candidates.length && version"><el-button :disabled="!canDownload" @click="mediaVisible = true">查看成果</el-button>
                <NasOpenButton v-if="desktop" text :project-id="projectId" :task-id="taskId" :version-id="item.versionId"
                  :file-id="reviewFile(version)?.fileId" :disabled="!canDownload || !reviewFile(version)?.fileId" />
                <el-button v-else :icon="FolderOpened" :disabled="!canDownload" @click="openFolder(version)">{{ folderButtonLabel }}</el-button></template>
            </div>
          </template>
        </el-card>
        <el-alert v-if="moreError" :title="moreError" type="error" :closable="false" />
        <el-button v-if="hasMore && (!approvedId || showHistory)" :loading="moreLoading" @click="loadMoreVersions">{{ moreError ? '重试加载' : '更早版本' }}</el-button>
      </el-tab-pane>
      <el-tab-pane label="反馈说明" name="feedback" lazy>
        <el-button v-if="canFeedback" type="primary" size="small" :disabled="Number(task?.latestVersion?.versionId) !== selectedVersionId" @click="addFeedback">添加反馈</el-button>
        <el-text v-if="canFeedback && Number(task?.latestVersion?.versionId) !== selectedVersionId" type="info" size="small">请选择最新版本添加反馈</el-text>
        <el-form ref="versionSelectForm" v-if="versions.length" :model="{ versionId: selectedVersionId }" label-position="top" size="small">
          <el-form-item label="查看版本" prop="versionId"><el-select :model-value="selectedVersionId" aria-label="反馈版本" @change="selectVersion"><el-option v-for="item in versions" :key="item.versionId" :value="Number(item.versionId)" :label="`${item.versionNumber} · ${formatVersionDateTime(item.submittedTime)}`" /></el-select></el-form-item>
        </el-form>
        <el-button v-if="hasMore" text size="small" :loading="moreLoading" @click="loadMoreVersions">加载更早版本</el-button>
        <el-alert v-if="moreError" :title="moreError" type="error" :closable="false" />
        <ShotFeedbackPanel v-if="taskId && selectedVersionId && canQuery" ref="feedback" :key="`${taskId}:${selectedVersionId}`" :project-id="projectId" :task-id="taskId" :version-id="selectedVersionId" :can-read="allowed('shotgrid:note:list')" :can-comment="allowed('shotgrid:note:comment')" />
        <el-empty v-else :image-size="48" :description="canQuery ? '提交成果后可查看反馈' : '当前账号没有版本详情权限'" />
      </el-tab-pane>
      <el-tab-pane label="制作参考" name="references" lazy>
        <AssetRelationsPanel v-if="!isAsset" :project-id="projectId" :shot-id="shotId" />
        <el-alert v-if="taskError" :title="taskError" type="warning" :closable="false" />
        <p v-for="(text, index) in referenceTexts" :key="index" class="reference-text">{{ text }}</p>
        <ReviewReferenceFiles v-if="referenceFiles.length" :files="referenceFiles" compact />
        <el-empty v-if="!referenceTexts.length && !referenceFiles.length" :image-size="48" :description="`这个${entityLabel}暂无制作参考`" />
      </el-tab-pane>
      <el-tab-pane v-if="isAsset" label="关联资产" name="relations" lazy><AssetRelationsPanel ref="relations" :project-id="projectId" :asset-id="assetId" @updated="emit('updated')" /></el-tab-pane>
    </el-tabs>
    <el-dialog v-model="mediaVisible" :title="candidate?.candidateNumber || version?.versionNumber || '成果预览'" width="min(900px, 92vw)" append-to-body destroy-on-close>
      <div class="version-switcher"><el-button size="small" :disabled="versionLoading || versionIndex <= 0" @click="adjacentVersion(-1)">较新版本</el-button><el-text>{{ version?.versionNumber || '加载中' }} · {{ candidate?.candidateNumber || '' }}</el-text><el-button size="small" :disabled="versionLoading || versionIndex < 0 || versionIndex >= versions.length - 1" @click="adjacentVersion(1)">上一版本</el-button><el-button v-if="hasMore" text size="small" :loading="moreLoading" @click="loadMoreVersions">加载更早版本</el-button></div>
      <el-skeleton v-if="versionLoading" :rows="3" animated />
      <el-alert v-if="versionError" :title="versionError" type="error" :closable="false"><el-button @click="selectVersion(selectedVersionId)">重试</el-button></el-alert>
      <ProtectedVersionPreview v-if="mediaVisible && previewVersion" :key="`${selectedVersionId}:${candidateId}`" :version="previewVersion" :can-preview="canDownload" />
    </el-dialog>
    <el-dialog :model-value="Boolean(folderPreview)" title="文件夹位置预览（演示）" width="min(520px, 92vw)" append-to-body destroy-on-close @update:model-value="value => { if (!value) folderPreview = null }">
      <template v-if="folderPreview"><el-alert title="当前仅演示入口，不会打开文件夹或连接 NAS。" type="info" :closable="false" />
        <el-descriptions :column="1" border class="folder-preview"><el-descriptions-item label="版本">{{ folderPreview.versionNumber }}</el-descriptions-item><el-descriptions-item label="文件">{{ folderPreview.name }}</el-descriptions-item><el-descriptions-item label="已记录位置">{{ folderPreview.path || folderPreview.reason }}</el-descriptions-item></el-descriptions>
      </template>
      <template #footer><el-button @click="folderPreview = null">关闭预览</el-button></template>
    </el-dialog>
    <ShotTaskFeedbackDialog ref="directFeedback" @closed="feedbackClosed" />
  </section>
</template>

<style scoped>
.final-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.shot-sidebar { min-width: 0; }.shot-sidebar__identity { color: var(--sg-text-muted); font-size: 12px; margin-bottom: 8px; }
.folder-preview { margin-top: 16px; overflow-wrap: anywhere; }
.shot-sidebar__tabs :deep(.el-tabs__header) { margin-bottom: 12px; }.shot-sidebar__tabs :deep(.el-tabs__item) { padding: 0 12px; }
.result-version-card { margin-bottom: 12px; }.result-version-card.is-selected { border-color: var(--sg-accent); }
.result-version-card :deep(.el-card__header),.result-version-card :deep(.el-card__body) { padding: 10px 12px; }
.result-version-header { display: flex; align-items: center; justify-content: space-between; }.result-version-header .el-button { padding: 0; height: 22px; }
.submission-meta { color: var(--sg-text-muted); font-size: 12px; }.submission-content,.reference-text { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; font-size: 13px; }
.candidate-grid { display: grid; gap: 10px; }.candidate-file { display: flex; align-items: flex-start; gap: 10px; padding-top: 10px; border-top: 1px solid var(--sg-border); }.candidate-file__info { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; flex: 1; }.candidate-file__name { overflow-wrap: anywhere; }.candidate-file__info .el-button { margin-left: 0; }.candidate-tile { display: block; width: 84px; flex-shrink: 0; height: auto; margin: 0; padding: 6px; white-space: normal; }.candidate-tile :deep(> span) { display: grid; width: 100%; gap: 5px; font-size: 12px; }.version-switcher { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
</style>
