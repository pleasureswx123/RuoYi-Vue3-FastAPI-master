<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getTaskIssues } from '@/api/shot-grid/reviews'
import { useVersionRealtime } from '@/composables/useVersionRealtime'
import IssueCommentThread from '@/components/review/IssueCommentThread.vue'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import { formatVersionDateTime } from '@/components/version/versionPresentation'

const props = defineProps({ projectId: Number, taskId: Number, versionId: Number, canRead: Boolean, canComment: Boolean })
const issues = ref([])
const loading = ref(false)
const error = ref('')
const threads = ref([])
const refreshKey = ref(0)
let controller = null
let generation = 0
let disposed = false
async function load() {
  controller?.abort()
  if (!props.canRead) { loading.value = false; return }
  const request = new AbortController(); controller = request
  const current = generation
  loading.value = true; error.value = ''
  try {
    const response = await getTaskIssues(props.taskId, {}, { signal: request.signal })
    if (disposed || current !== generation || request.signal.aborted || controller !== request) return
    const rows = response.data || []
    if (rows.some(item => Number(item.projectId) !== props.projectId)) throw new Error('反馈归属不匹配，请刷新')
    // 原问题不改绑：在来源版和有处理记录的版本中展示，评论始终写回来源版。
    issues.value = rows.filter(item => Number(item.originVersionId) === props.versionId || Number(item.pendingVersionId) === props.versionId ||
      item.responses?.some(response => Number(response.versionId) === props.versionId) ||
      item.verifications?.some(check => Number(check.checkedVersionId) === props.versionId))
    refreshKey.value++
  } catch (err) {
    if (!disposed && current === generation && !request.signal.aborted) error.value = err.message || '反馈读取失败'
  } finally { if (controller === request) loading.value = false }
}
watch(() => [props.projectId, props.taskId, props.versionId, props.canRead], () => {
  generation++; issues.value = []; error.value = ''; threads.value = []; load()
}, { immediate: true })
useVersionRealtime(computed(() => props.canRead ? props.versionId : null), load)
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort() })
const dirty = computed(() => threads.value.some(item => item?.dirty))
const sending = computed(() => threads.value.some(item => item?.sending))
function progress(issue) {
  if (issue.status === 'resolved') return { label: '已解决', type: 'success' }
  const response = issue.responses?.at(-1)
  if (response?.versionId && !issue.verifications?.some(check => Number(check.checkedVersionId) === Number(response.versionId))) return { label: '已提交修改，待确认', type: 'warning' }
  return { label: '待修改', type: 'danger' }
}
function history(issue) {
  return [
    ...(issue.responses || []).map(item => ({ key: `response:${item.responseId}`, time: item.createTime, title: `${item.versionNumber || '后续版本'} · ${item.responderName || '制作人'}提交处理说明`, content: item.responseText })),
    ...(issue.verifications || []).map(item => ({ key: `check:${item.verificationId}`, time: item.createTime, title: `${item.checkedVersionNumber} · ${item.reviewerName || '审核人'}确认${item.result === 'resolved' ? '已解决' : '仍需修改'}`, content: item.comment }))
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
}
defineExpose({ dirty, sending })
</script>

<template>
  <section class="shot-feedback-list">
    <el-alert v-if="!canRead" title="当前账号没有反馈查看权限" type="info" :closable="false" />
    <template v-else>
      <el-skeleton v-if="loading && !issues.length" :rows="3" animated />
      <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button text @click="load">重新加载</el-button></el-alert>
      <el-empty v-else-if="!loading && !issues.length" :image-size="48" description="这个版本暂无反馈" />
      <el-card v-for="issue in issues" :key="issue.issueId" shadow="never" class="feedback-card">
        <template #header><div class="feedback-meta"><strong>{{ issue.originCandidateNumber || `${issue.originVersionNumber || '来源版本'} · 整体反馈` }}</strong><el-tag size="small" :type="progress(issue).type">{{ progress(issue).label }}</el-tag></div><div class="feedback-author">{{ issue.reviewerName || '审核人' }} · {{ formatVersionDateTime(issue.createTime) }}</div></template>
        <p class="feedback-content">{{ issue.content || '此条反馈包含画面标注，请在审核详情查看。' }}</p>
        <ReviewReferenceFiles v-if="issue.referenceFiles?.length" :files="issue.referenceFiles" compact />
        <el-collapse v-if="history(issue).length" class="feedback-history"><el-collapse-item :title="`处理记录（${history(issue).length}）`" :name="issue.issueId"><el-timeline><el-timeline-item v-for="entry in history(issue)" :key="entry.key" :timestamp="formatVersionDateTime(entry.time)"><strong>{{ entry.title }}</strong><p v-if="entry.content" class="feedback-content">{{ entry.content }}</p></el-timeline-item></el-timeline></el-collapse-item></el-collapse>
        <el-text v-if="canComment" size="small" type="info">评论用于沟通；处理状态以提交修改和审核确认为准。</el-text>
        <IssueCommentThread ref="threads" :project-id="projectId" :version-id="Number(issue.originVersionId)" :issue-id="issue.issueId" :can-comment="canComment" :refresh-key="refreshKey" />
      </el-card>
    </template>
  </section>
</template>

<style scoped>
.feedback-card { margin-bottom: 12px; }.feedback-card :deep(.el-card__header),.feedback-card :deep(.el-card__body) { padding: 12px; }
.feedback-meta { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 13px; }.feedback-author { margin-top: 6px; color: var(--sg-text-muted); font-size: 12px; }
.feedback-content { margin: 0 0 8px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
.feedback-history { margin: 8px 0; }.feedback-history :deep(.el-timeline) { padding-left: 12px; }.feedback-meta { flex-wrap: wrap; }
</style>
