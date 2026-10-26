<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getVersionReviewContext, reopenVersionReview } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { createIdempotencyState } from '@/utils/idempotency'
const props = defineProps({ version: { type: Object, required: true } })
const emit = defineEmits(['reopened'])
const session = useSessionStore()
const allowed = computed(() => props.version.versionStatus === 'final' &&
  ['shotgrid:version:review', 'shotgrid:version:reopen'].every(code => session.permissions.includes('*:*:*') || session.permissions.includes(code)))
const visible = ref(false), loading = ref(false), busy = ref(false), error = ref(''), snapshot = ref(null), form = ref(null)
const model = ref({ reason: '' })
const rules = { reason: [{ required: true, whitespace: true, message: '请填写重新审核原因', trigger: 'blur' }, { max: 1000, message: '原因最多 1000 字', trigger: 'blur' }] }
const idempotency = createIdempotencyState('review-reopen')
let generation = 0, controller
function reset() { generation++; controller?.abort(); visible.value = false; snapshot.value = null; loading.value = false; busy.value = false; error.value = ''; model.value.reason = ''; form.value?.resetFields(); idempotency.reset() }
watch(() => props.version.versionId, reset)
onBeforeUnmount(reset)
async function open() {
  if (!allowed.value || loading.value || busy.value) return
  reset(); visible.value = true; loading.value = true
  const token = generation, versionId = props.version.versionId
  controller = new AbortController()
  try {
    const { data } = await getVersionReviewContext(versionId, { signal: controller.signal })
    if (token !== generation) return
    snapshot.value = { ...data, versionId }
    if (!data.canReopenReview) error.value = data.reopenBlockedReason || '当前状态不能重新审核'
  } catch (e) { if (token === generation) error.value = e.message || '加载审核状态失败' }
  finally { if (token === generation) loading.value = false }
}
async function submit() {
  if (busy.value || !allowed.value || !snapshot.value?.canReopenReview) return
  // 校验也属于提交过程，避免异步校验期间双击生成两次请求。
  busy.value = true
  const token = generation, state = snapshot.value
  const valid = await form.value?.validate().catch(() => false)
  if (token !== generation) return
  if (!valid || !allowed.value) { busy.value = false; return }
  const payload = { lockVersion: state.currentVersion.lockVersion, taskLockVersion: state.taskLockVersion,
    reviewCycle: state.currentVersion.reviewCycle, reason: model.value.reason.trim() }
  busy.value = true; error.value = ''
  try {
    const { data } = await reopenVersionReview(state.versionId, payload, idempotency.forPayload({ versionId: state.versionId, ...payload }))
    if (token !== generation) return
    visible.value = false
    ElMessage.success('已重新打开审核，原交付已失效；补充问题后可退回制作人修改')
    emit('reopened', data)
  } catch (e) {
    if (token !== generation) return
    error.value = e.message || '操作结果未确认，请使用相同内容重试或刷新核对'
    if (e.response?.status === 409) snapshot.value.canReopenReview = false
  } finally { if (token === generation) busy.value = false }
}
</script>
<template>
  <el-button v-if="allowed" type="warning" plain :loading="loading" @click="open">重新审核</el-button>
  <el-dialog v-model="visible" title="重新审核" width="520px" append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @closed="reset">
    <div v-loading="loading">
      <el-alert type="warning" :closable="false" title="确认后任务回到待审核，原交付立即失效。历史文件保留，NAS 有效清单异步同步；正式发送问题后制作人才进入修改。" />
      <el-descriptions :column="1" border><el-descriptions-item label="版本">{{ version.versionNumber || `V${version.versionNo}` }}</el-descriptions-item><el-descriptions-item label="当前审核周期">{{ snapshot?.currentVersion?.reviewCycle || 1 }}</el-descriptions-item></el-descriptions>
      <el-form ref="form" :model="model" :rules="rules" label-position="top" :disabled="busy || loading">
        <el-form-item label="重新审核原因" prop="reason"><el-input v-model="model.reason" type="textarea" :rows="4" maxlength="1000" show-word-limit /></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </div>
    <template #footer><el-button :disabled="busy" @click="visible = false">取消</el-button><el-button type="warning" :loading="busy" :disabled="loading || !snapshot?.canReopenReview" @click="submit">确认重新审核</el-button></template>
  </el-dialog>
</template>
