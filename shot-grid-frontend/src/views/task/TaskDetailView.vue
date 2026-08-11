<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTask, startTask } from '@/api/shot-grid/tasks'
import { getTaskVersion, getVersionMediaPolicy, getVersionSubmission, initializeVersionSubmission, listTaskVersions, retryVersionSubmission, uploadProtectedVersionFile, versionFileUrl } from '@/api/shot-grid/versions'
import { formatBytes, validateSelectedMedia, versionMediaErrorMessage } from '@/utils/versionMedia'

const ProtectedImagePreview = defineAsyncComponent(() => import('@/components/media/ProtectedImagePreview.vue'))
const ProtectedVideoPreview = defineAsyncComponent(() => import('@/components/media/ProtectedVideoPreview.vue'))

const props = defineProps({ taskId: { type: String, required: true } })
const route = useRoute(), projectId = String(route.query.projectId || ''), task = ref(null), reason = ref('')
let pageController = new AbortController()
async function load() {
  const [taskData, versionData, policies] = await Promise.all([
    getTask(projectId, props.taskId, { signal: pageController.signal }),
    listTaskVersions(projectId, props.taskId, { signal: pageController.signal }),
    getVersionMediaPolicy(projectId, props.taskId)
  ])
  task.value = taskData
  mediaPolicies.value = policies
  versions.value = versionData
  if (versionData.length) await selectVersion(versionData[0].versionId)
}
async function start() { await startTask(projectId, props.taskId, { reason: reason.value || null }); await load() }
const selectedFile = ref(null), submitting = ref(false), polling = ref(0), mediaPolicies = ref(null), fileHint = ref('')
const submission = ref(null), form = reactive({ changelog: '' }), uploadPercent = ref(0)
const versions = ref([]), selectedVersion = ref(null)
let versionController
const primaryFile = computed(() => selectedVersion.value?.files?.find(item => item.isPrimary) || selectedVersion.value?.files?.[0])
const mediaSource = computed(() => primaryFile.value ? {
  projectId,
  url: versionFileUrl(projectId, props.taskId, selectedVersion.value.versionId, primaryFile.value.fileId)
} : null)
async function selectVersion(versionId) {
  versionController?.abort()
  versionController = new AbortController()
  selectedVersion.value = await getTaskVersion(projectId, props.taskId, versionId, { signal: versionController.signal })
}
const mediaPolicy = computed(() => task.value?.taskKind === 'shot_video' ? mediaPolicies.value?.shotVideo : mediaPolicies.value?.assetImage)
function chooseFile(file) {
  selectedFile.value = file.raw
  uploadPercent.value = 0
  fileHint.value = validateSelectedMedia(file.raw, mediaPolicy.value) || ''
}
function stopPolling() { if (polling.value) window.clearTimeout(polling.value); polling.value = 0 }
async function refreshSubmission() {
  if (!submission.value?.submissionId) return
  submission.value = await getVersionSubmission(projectId, props.taskId, submission.value.submissionId)
  if (!['committed', 'failed'].includes(submission.value.status) && !submission.value.errorKey) polling.value = window.setTimeout(refreshSubmission, 1500)
  else if (submission.value.status === 'committed') await load()
}
async function submitVersion() {
  if (!selectedFile.value || !form.changelog.trim()) return ElMessage.warning('请选择文件并填写修改说明')
  if (fileHint.value) return ElMessage.warning(fileHint.value)
  submitting.value = true
  try {
    const uploaded = await uploadProtectedVersionFile(selectedFile.value, value => { uploadPercent.value = value })
    submission.value = await initializeVersionSubmission(projectId, props.taskId, {
      fileId: uploaded.fileId, changelog: form.changelog.trim(),
      idempotencyKey: crypto.randomUUID()
    })
    await refreshSubmission()
  } catch (error) {
    ElMessage.error(versionMediaErrorMessage(error))
  } finally { submitting.value = false }
}
async function retrySubmission() {
  submission.value = await retryVersionSubmission(projectId, props.taskId, submission.value.submissionId)
  await refreshSubmission()
}
onMounted(load)
onBeforeUnmount(() => { stopPolling(); pageController.abort(); versionController?.abort() })
const actionLabels = { assigned: '分配', reassigned: '改派', started: '开始任务' }
const stageLabels = { uploaded: '上传完成，等待 Worker', nas_publishing: '正在发布到 NAS', nas_published: 'NAS 发布完成', database_committing: '正在正式入库', completed: '版本提交完成', failed: '提交失败' }
</script>
<template>
  <section class="page"><span class="eyebrow">TASK / {{ taskId }}</span><template v-if="task"><h1>{{ task.taskName }}</h1><p class="lead">状态：{{ task.taskStatus }} · 负责人 #{{ task.assigneeUserId }}</p><div v-if="task.taskStatus === 'not_started'" class="task-actions"><el-input v-model="reason" placeholder="代操作时填写原因"/><el-button type="success" @click="start">开始任务</el-button></div>
  <template v-if="['in_progress', 'revision'].includes(task.taskStatus)"><h2>提交审核版本</h2><div class="version-submit"><el-alert v-if="mediaPolicy" type="info" :closable="false" :title="`服务端限制：${mediaPolicy.extensions.join(' / ')}；${mediaPolicy.mimeTypes.join(' / ')}；最大 ${formatBytes(mediaPolicy.maxSizeBytes)}；${mediaPolicy.encodings.join(' / ')}；不超过 ${mediaPolicy.maxWidth}×${mediaPolicy.maxHeight}${mediaPolicy.maxDurationSeconds ? `、${mediaPolicy.maxDurationSeconds} 秒` : ''}；${mediaPolicy.generateProxy ? '生成代理文件' : '不生成代理文件'}`"/><el-upload :auto-upload="false" :limit="1" :accept="mediaPolicy?.extensions.join(',')" :on-change="chooseFile"><el-button>选择审核媒体</el-button></el-upload><el-alert v-if="fileHint" type="warning" :closable="false" :title="`${fileHint}（前端提示非权威，最终以服务端内容校验为准）`"/><el-input v-model="form.changelog" type="textarea" maxlength="5000" show-word-limit placeholder="本轮修改说明"/><el-button type="primary" :loading="submitting" @click="submitVersion">上传并提交</el-button></div></template>
  <el-card v-if="submission" class="submission-status"><template #header>版本 V{{ String(submission.reservedVersionNo).padStart(3, '0') }}</template><el-steps :active="submission.stage === 'completed' ? 3 : submission.stage === 'database_committing' ? 2 : submission.stage?.startsWith('nas_') ? 1 : 0" finish-status="success"><el-step title="受保护上传"/><el-step title="NAS 发布"/><el-step title="正式入库"/></el-steps><el-progress v-if="uploadPercent < 100" :percentage="uploadPercent"/><p>{{ stageLabels[submission.stage] }}；进度仅随服务端真实状态更新。</p><el-alert v-if="submission.errorMessage" :title="submission.errorMessage" type="error" show-icon/><el-button v-if="submission.retryable" @click="retrySubmission">重试当前提交</el-button></el-card>
  <template v-if="versions.length"><h2>版本历史</h2><div class="version-strip" role="list" aria-label="任务版本"><button v-for="version in versions" :key="version.versionId" :class="{active:selectedVersion?.versionId === version.versionId}" @click="selectVersion(version.versionId)">V{{ String(version.versionNo).padStart(3, '0') }}<small>{{ version.versionStatus }}</small></button></div><el-card v-if="selectedVersion" class="version-detail"><template #header>V{{ String(selectedVersion.versionNo).padStart(3, '0') }} · 历史快照（只读）</template><component :is="primaryFile?.mediaType?.startsWith('video/') ? ProtectedVideoPreview : ProtectedImagePreview" v-if="primaryFile" :source="mediaSource" :alt="primaryFile.businessFileName"/><el-empty v-else description="该版本没有可预览文件"/><dl><dt>提交说明</dt><dd>{{ selectedVersion.changelog }}</dd><dt>提交时间</dt><dd>{{ selectedVersion.submittedTime }}</dd></dl></el-card></template>
  <h2>任务历史</h2><el-timeline><el-timeline-item v-for="item in task.history" :key="item.historyId" :timestamp="item.createTime"><strong>{{ actionLabels[item.action] || item.action }}</strong><span> · 操作人 #{{ item.actorUserId }}</span><el-tag v-if="item.delegated" type="warning">代操作</el-tag><p v-if="item.detail?.reason">原因：{{ item.detail.reason }}</p></el-timeline-item></el-timeline></template></section>
</template>
<style scoped>.task-actions{display:flex;gap:12px;max-width:600px;margin:20px 0}.el-tag{margin-left:8px}.version-submit{display:grid;gap:12px;max-width:720px}.submission-status,.version-detail{margin:24px 0;max-width:900px}.submission-status p{margin:18px 0}.version-strip{display:flex;gap:8px;overflow:auto;padding:4px}.version-strip button{display:grid;gap:3px;min-width:92px;padding:10px;border:1px solid #374151;border-radius:6px;background:transparent;color:inherit;cursor:pointer}.version-strip button.active{border-color:#409eff;background:#18283a}.version-strip small{opacity:.7}.version-detail dl{display:grid;grid-template-columns:90px 1fr;gap:8px;margin-top:18px}.version-detail dd{margin:0;white-space:pre-wrap}</style>
