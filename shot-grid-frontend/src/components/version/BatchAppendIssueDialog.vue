<script setup>
import { RefreshLeft } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { appendVersionIssue, getVersionReviewContext } from '@/api/shot-grid/reviews'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close'])
const context = props.context
const loading = ref(true)
const busy = ref(false)
const finished = ref(false)
const error = ref('')
const formRef = ref(null)
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({
  canEdit: () => !loading.value && !busy.value && !finished.value && !error.value,
  isCurrent: () => current()
})
const form = reactive({ content: '', referenceFiles: referenceAttachments })
const rows = ref(context.targets.map(target => ({ ...target, lockVersion: null, result: '待发送', success: false })))
const successCount = computed(() => rows.value.filter(row => row.success).length)
const rules = { content: [
  { required: true, whitespace: true, message: '请填写追加问题', trigger: 'blur' },
  { max: 10000, message: '追加问题不能超过 10000 字', trigger: 'blur' }
] }
let disposed = false
const controller = new AbortController()
onBeforeUnmount(() => { disposed = true; controller.abort() })
const current = () => !disposed && context.validateContext()

onMounted(async () => {
  try {
    // 固定列表中的版本，不因刷新而把同一条意见转发给下一版。
    for (const row of rows.value) {
      if (!current()) throw new Error('所选任务已变化，请关闭并刷新后重新选择')
      const { data } = await getVersionReviewContext(row.versionId, { signal: controller.signal })
      if (disposed) return
      const version = data?.currentVersion
      if (!current() || !data?.canAppendIssues || version?.versionId !== row.versionId ||
          version.versionStatus !== 'rejected' || !Number.isSafeInteger(version.lockVersion) || version.lockVersion < 0) {
        throw new Error(`${row.label} 已不能追加问题，请关闭并刷新后重新选择`)
      }
      row.lockVersion = version.lockVersion
    }
  } catch (failure) {
    if (!disposed) error.value = failure?.message || '版本核对失败，请关闭后重试'
  } finally { if (!disposed) loading.value = false }
})

function close() {
  if (!busy.value) emit('close')
}
function reset() {
  if (busy.value || finished.value) return
  formRef.value?.resetFields()
  form.content = ''
  resetReferenceAttachments()
  formRef.value?.clearValidate()
}
async function send() {
  if (loading.value || busy.value || finished.value || error.value) return
  busy.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false) || disposed) return
    if (!current()) { error.value = '所选任务已变化，请关闭并刷新后重新选择'; return }
    const content = form.content.trim()
    let referenceFileIds
    try { referenceFileIds = await uploadPendingReferenceFiles() } catch (failure) {
      if (current()) ElMessage.error(failure?.message || '参考文件上传失败，请重试；尚未追加问题')
      return
    }
    if (!current()) { if (!disposed) error.value = '所选任务已变化，请关闭并刷新后重新选择'; return }
    for (const row of rows.value) {
      if (!current()) break
      row.result = '正在发送'
      try {
        // 每次使用打开弹窗时取得的锁号；请求不确定时禁止自动重试。
        await appendVersionIssue(row.versionId, { issueScope: 'version', content, referenceFileIds, lockVersion: row.lockVersion })
        if (disposed) return
        row.success = true
        row.result = '已追加并发送'
      } catch (failure) {
        if (disposed) return
        const status = Number(failure?.httpStatus || failure?.status)
        const rejected = [401, 403, 404, 409, 422].includes(status)
        row.result = rejected ? failure?.message || '发送失败，请刷新后核对' : '发送结果未知，请刷新并查看已有问题，勿直接重复发送'
        if (![409, 422].includes(status)) break
      }
    }
    if (!disposed) {
      rows.value.filter(row => row.result === '待发送').forEach(row => { row.result = '未执行，请刷新后重新选择' })
      finished.value = true
    }
  } finally { busy.value = false }
}
</script>

<template>
  <ProjectModal title="批量追加发送问题" :description="`已选择 ${rows.length} 个待修改任务`" :busy="busy" wide @close="close">
    <el-alert title="同一份问题将逐项追加到所选版本并立即发送给制作人，任务保持待修改。已发送项会保留；制作人已提交下一版的任务不能再追加。" type="info" show-icon :closable="false" />
    <el-table v-loading="loading" :data="rows" row-key="versionId" max-height="300" class="batch-issue-targets">
      <el-table-column label="镜头 / 版本" prop="label" min-width="220" />
      <el-table-column label="发送结果" prop="result" min-width="260" />
    </el-table>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert v-if="finished" :title="`已发送 ${successCount} / ${rows.length} 项，请核对各项结果。关闭后刷新列表。`" :type="successCount === rows.length ? 'success' : 'warning'" show-icon :closable="false" />
    <el-form v-if="!loading && !error" ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="busy || finished" class="batch-issue-form" aria-label="批量追加问题表单">
      <el-form-item label="追加问题（适用于全部所选版本）" prop="content"><el-input v-model="form.content" type="textarea" :rows="5" maxlength="10000" show-word-limit placeholder="填写制作人需要处理的共同问题；单个候选或画面问题请进入任务分别追加" /></el-form-item>
      <el-form-item label="参考内容（可选）" prop="referenceFiles"><ReviewReferenceInput :files="referenceAttachments" :disabled="busy || finished" @add="addReferenceFile" @remove="removeReferenceFile" /></el-form-item>
      <p class="batch-issue-hint">参考内容会随追加问题一并发送给全部所选版本。</p>
    </el-form>
    <footer class="batch-issue-actions">
      <el-button :disabled="busy" @click="close">{{ finished || error ? '关闭并刷新' : '取消' }}</el-button>
      <template v-if="!loading && !error && !finished"><el-button :icon="RefreshLeft" :disabled="busy" @click="reset">重置</el-button><el-button type="primary" :loading="busy" :disabled="busy" @click="send">追加并发送（{{ rows.length }}）</el-button></template>
    </footer>
  </ProjectModal>
</template>

<style scoped>
.batch-issue-targets{margin:16px 0}.batch-issue-form{margin-top:18px}.batch-issue-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:18px}
.batch-issue-hint{color:var(--sg-text-muted);font-size:12px}
</style>
