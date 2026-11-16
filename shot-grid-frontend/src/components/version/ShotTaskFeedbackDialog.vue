<script setup>
import { computed, onBeforeUnmount, reactive, ref, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { getVersionReviewContext, submitBatchFeedback, appendVersionIssue } from '@/api/shot-grid/reviews'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'

const emit = defineEmits(['closed', 'active-change'])
const visible = ref(false)
const loading = ref(false)
const sending = ref(false)
let validating = false
const finished = ref(false)
const error = ref('')
const uploadError = ref('')
const formRef = ref(null)
const form = reactive({ common: '', rows: [] })
let projectId = null
let generation = 0
let controller = null
let validateContext = () => true
let disposed = false
const current = token => !disposed && visible.value && generation === token && validateContext()
const disabled = computed(() => loading.value || sending.value || finished.value || Boolean(error.value))
const sentCount = computed(() => form.rows.filter(row => row.result === '已发送').length)
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({
  canEdit: () => !disabled.value, isCurrent: () => current(generation)
})
const combined = row => [form.common.trim(), row.content.trim()].filter(Boolean).join('\n\n')
const rules = { common: [{ max: 10000, message: '反馈最多 10000 字', trigger: 'blur' }] }
const rowRules = row => [{ validator: (_rule, _value, done) => {
  const content = combined(row)
  if (content.length > 10000) return done(new Error('共同反馈与单镜头补充合计不能超过 10000 字'))
  if (referenceAttachments.value.length && !content) return done(new Error('添加参考文件后，请填写反馈说明'))
  if (!content && !row.drafts.length && !row.currentIssues.length && !row.issues.some(issue => issue.result === 'still_present')) return done(new Error('请填写共同反馈或这颗镜头的反馈'))
  if (['rejected', 'final'].includes(row.status) && !content) return done(new Error('请填写要追加的反馈'))
  done()
}, trigger: 'blur' }]

async function open(project, targets, isCurrent = () => true) {
  if (visible.value || sending.value || !targets.length || targets.length > 100) return
  controller?.abort(); controller = new AbortController()
  const token = ++generation
  projectId = Number(project); validateContext = isCurrent
  resetReferenceAttachments()
  form.common = ''; form.rows = targets.map(target => ({ ...target, content: '', status: '', lockVersion: null, issues: [], drafts: [], currentIssues: [], draftsConfirmed: false, result: '待发送' }))
  error.value = ''; uploadError.value = ''; finished.value = false; loading.value = true; visible.value = true
  emit('active-change', true)
  try {
    for (const row of form.rows) {
      if (!current(token)) throw new Error('当前项目或镜头已变化，请关闭并重新选择')
      const [{ data: task }, { data: review }] = await Promise.all([
        getTaskDetail(row.taskId, { signal: controller.signal }),
        getVersionReviewContext(row.versionId, { signal: controller.signal })
      ])
      if (!current(token)) return
      const version = review?.currentVersion
      if (Number(task?.project?.projectId) !== projectId || Number(task?.taskId) !== Number(row.taskId) || task?.taskKind !== 'shot_video' ||
          Number(task.target?.shotId ?? task.target?.targetId) !== Number(row.shotId) || Number(task.latestVersion?.versionId) !== Number(row.versionId) ||
          Number(version?.versionId) !== Number(row.versionId) || !Number.isSafeInteger(version?.lockVersion) || version.lockVersion < 0 ||
          !task.allowedActions?.includes('task.feedback') || !['pending_review', 'rejected', 'final'].includes(version.versionStatus) || (version.versionStatus === 'rejected' && !review.canAppendIssues) ||
          task.taskStatus !== ({ pending_review: 'pending_review', rejected: 'revision', final: 'completed' })[version.versionStatus]) {
        throw new Error(`${row.label} 的归属或版本已变化，或已不能反馈；请关闭后刷新`)
      }
      row.status = version.versionStatus; row.lockVersion = version.lockVersion
      row.issues = row.status === 'pending_review' ? (review.carriedIssues || []).map(issue => ({ ...issue, result: '', comment: '' })) : []
      row.drafts = row.status === 'pending_review' ? review.currentVersionDrafts || [] : []
      row.currentIssues = review.currentVersionIssues || []
    }
  } catch (failure) { if (current(token)) error.value = failure.message || '反馈目标读取失败' }
  finally { if (!disposed && generation === token) { loading.value = false; if (!validateContext()) error.value = '当前项目或镜头已变化，请关闭并重新选择' } }
  await nextTick(); if (current(token)) formRef.value?.clearValidate()
}
function close() {
  if (sending.value || validating) return
  const result = { projectId, changed: sentCount.value > 0, uncertain: finished.value,
    completedShotIds: form.rows.filter(row => row.result === '已发送').map(row => Number(row.shotId)) }
  generation++; controller?.abort(); visible.value = false
  resetReferenceAttachments()
  emit('active-change', false); emit('closed', result)
}
function reset() {
  if (disabled.value || validating) return
  formRef.value?.resetFields(); form.common = ''; uploadError.value = ''
  resetReferenceAttachments()
  for (const row of form.rows) { row.content = ''; row.draftsConfirmed = false; row.issues.forEach(issue => { issue.result = ''; issue.comment = '' }) }
  formRef.value?.clearValidate()
}
async function send() {
  if (disabled.value || validating) return
  validating = true
  uploadError.value = ''
  const token = generation
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    if (!current(token)) { error.value = '当前项目或镜头已变化，请关闭并重新选择'; return }
    sending.value = true
    let referenceFileIds
    try { referenceFileIds = await uploadPendingReferenceFiles() }
    catch (failure) { if (current(token)) uploadError.value = failure.message || '参考文件上传失败，请重试'; return }
    for (const row of form.rows) {
      if (!current(token)) break
      row.result = '发送中'
      try {
        const content = combined(row)
        if (['rejected', 'final'].includes(row.status)) {
          await appendVersionIssue(row.versionId, { issueScope: 'version', content, referenceFileIds, lockVersion: row.lockVersion })
        } else {
          await submitBatchFeedback(projectId, { action: 'reject', content, referenceFileIds, items: [{
            versionId: row.versionId, lockVersion: row.lockVersion,
            drafts: row.drafts.map(draft => ({ draftId: draft.draftId, lockVersion: draft.lockVersion })),
            issueVerifications: row.issues.map(issue => ({ issueId: issue.issueId, result: issue.result, comment: issue.result === 'still_present' ? issue.comment.trim() : null }))
          }] })
        }
        if (disposed || generation !== token) return
        row.result = '已发送'
      } catch (failure) {
        if (disposed || generation !== token) return
        const status = Number(failure?.httpStatus || failure?.status || failure?.response?.status)
        row.result = [401, 403, 404, 409, 422].includes(status) ? `未发送：${failure.message || '请刷新核对'}` : '结果未知，请刷新核对，勿重复发送'
        break
      }
    }
    if (!disposed && generation === token) { form.rows.filter(row => row.result === '待发送').forEach(row => { row.result = '未执行' }); finished.value = true }
  } finally { validating = false; if (!disposed && generation === token) sending.value = false }
}
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort(); emit('active-change', false) })
defineExpose({ open })
</script>

<template>
  <el-dialog :model-value="visible" :title="form.rows.length > 1 ? '批量添加镜头反馈' : '添加镜头反馈'" width="min(900px, 94vw)" append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!sending" :show-close="!sending" :before-close="close">
    <el-alert title="核对镜头、场次和版本后发送。待审核或已通过镜头将进入待修改，已反馈镜头追加问题。逐镜头保存；中途失败会停止，已发送项保留。" type="info" :closable="false" />
    <el-table :data="form.rows" row-key="versionId" v-loading="loading" max-height="220" class="feedback-targets"><el-table-column prop="label" label="镜头 / 场次 / 版本" min-width="260" /><el-table-column prop="result" label="结果" min-width="180" /></el-table>
    <el-alert v-if="finished" :title="`已发送 ${sentCount} 颗，未完成 ${form.rows.length - sentCount} 颗。关闭后保留未完成镜头的勾选；结果未知的镜头请先核对反馈记录。`" :type="sentCount === form.rows.length ? 'success' : 'warning'" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="uploadError" :title="uploadError" type="error" :closable="false" />
    <el-form v-if="!loading && !error" ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="disabled" aria-label="镜头直接反馈表单">
      <el-form-item label="共同反馈（适用于全部所选镜头）" prop="common"><el-input v-model="form.common" type="textarea" :rows="3" maxlength="10000" show-word-limit placeholder="例如：这几个镜头的人物服装、光线需要统一" /></el-form-item>
      <ReviewReferenceInput :files="referenceAttachments" :disabled="disabled" @add="addReferenceFile" @remove="removeReferenceFile" />
      <el-card v-for="(row, index) in form.rows" :key="row.versionId" shadow="never" class="feedback-target-card">
        <template #header>{{ row.label }}</template>
        <el-form-item label="此镜头补充反馈（可选）" :prop="`rows.${index}.content`" :rules="rowRules(row)"><el-input v-model="row.content" type="textarea" :rows="2" maxlength="10000" show-word-limit /></el-form-item>
        <div v-if="row.issues.length" class="feedback-carried">已有问题需复核，不能以新增意见代替复核：</div>
        <div v-for="(issue, issueIndex) in row.issues" :key="issue.issueId" class="feedback-carried">
          <p>{{ issue.originVersionNumber }} · {{ issue.originCandidateNumber || '整体反馈' }} · {{ issue.content || '画面标注问题' }}</p><p>制作人说明：{{ issue.currentVersionResponse?.responseText || '未填写处理说明' }}</p>
          <ReviewReferenceFiles v-if="issue.referenceFiles?.length" :files="issue.referenceFiles" compact />
          <RouterLink v-if="issue.annotations || issue.mediaTimeMs != null" :to="{ name: 'version-detail', params: { versionId: issue.originVersionId } }" target="_blank" rel="noopener">查看原版本画面与标注（新标签页）</RouterLink>
          <el-form-item label="复核结论" :prop="`rows.${index}.issues.${issueIndex}.result`" :rules="[{ required: true, message: '请选择复核结论' }]"><el-radio-group v-model="issue.result"><el-radio-button value="resolved">已解决</el-radio-button><el-radio-button value="still_present">仍需修改</el-radio-button></el-radio-group></el-form-item>
          <el-form-item v-if="issue.result === 'still_present'" label="仍需修改的原因" :prop="`rows.${index}.issues.${issueIndex}.comment`" :rules="[{ required: true, whitespace: true, message: '请填写修改原因' }]"><el-input v-model="issue.comment" type="textarea" maxlength="1000" /></el-form-item>
        </div>
        <template v-if="row.drafts.length">
          <div v-for="draft in row.drafts" :key="draft.draftId" class="feedback-carried">
            <p>{{ draft.reviewerName || '审核人' }} · {{ draft.candidateId ? '文件反馈' : '整体反馈' }} · 已有草稿：{{ draft.content || '画面标注问题' }}</p>
            <ReviewReferenceFiles v-if="draft.referenceFiles?.length" :files="draft.referenceFiles" compact />
            <RouterLink v-if="draft.annotations || draft.mediaTimeMs != null" :to="{ name: 'review-detail', params: { reviewListId: draft.reviewListId } }" target="_blank" rel="noopener">查看草稿画面与标注（新标签页）</RouterLink>
          </div>
          <el-form-item :prop="`rows.${index}.draftsConfirmed`" :rules="[{ validator: (_rule, value, done) => done(value ? undefined : new Error('请确认已有草稿')) }]"><el-checkbox v-model="row.draftsConfirmed">确认同时发送以上已有草稿</el-checkbox></el-form-item>
        </template>
      </el-card>
    </el-form>
    <template #footer><el-button :disabled="sending" @click="close">{{ finished ? '关闭并刷新' : '取消' }}</el-button><el-button v-if="!finished" :disabled="disabled" @click="reset">重置</el-button><el-button v-if="!finished" type="primary" :loading="sending" :disabled="disabled" @click="send">确认发送反馈</el-button></template>
  </el-dialog>
</template>

<style scoped>
.feedback-targets,.feedback-target-card{margin:14px 0}.feedback-carried{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;margin:10px 0}
</style>
