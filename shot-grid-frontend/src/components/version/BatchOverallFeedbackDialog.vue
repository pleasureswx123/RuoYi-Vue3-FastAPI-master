<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { rejectBatchWithOverallFeedback } from '@/api/shot-grid/reviews'
import { reviewErrorState } from '@/views/review/reviewPresentation'

const emit = defineEmits(['saved'])
const visible = ref(false)
const busy = ref(false)
const formRef = ref(null)
const targets = ref([])
const projectId = ref(null)
const form = reactive({ content: '' })
const rules = { content: [{ required: true, whitespace: true, message: '请填写整体反馈意见', trigger: 'blur' }] }
function open(project, shots) {
  if (busy.value) return
  projectId.value = project
  targets.value = shots.map(shot => ({ versionId: shot.latestVersion.versionId, label: `${shot.shotCode} · ${shot.latestVersion.versionNumber}` }))
  form.content = ''
  visible.value = true
}
function reset() {
  formRef.value?.resetFields()
  targets.value = []
}
async function save() {
  if (busy.value || !await formRef.value?.validate().catch(() => false)) return
  if (busy.value) return
  busy.value = true
  const project = projectId.value
  try {
    await rejectBatchWithOverallFeedback(project, { versionIds: targets.value.map(item => item.versionId), content: form.content.trim() })
    ElMessage.success(`已为 ${targets.value.length} 个任务发送整体反馈并退回修改`)
    visible.value = false
    emit('saved', { projectId: project })
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '退回失败，请刷新确认任务状态后再操作').message)
  } finally { busy.value = false }
}
defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" title="批量整体反馈并退回" width="580px" append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @closed="reset">
    <el-alert :title="`为 ${targets.length} 个待审核任务发送同一份整体反馈，任务将全部变为修改中。`" type="info" :closable="false" show-icon />
    <p>有未处理草稿或上轮问题待复核的任务，请先进入任务逐个审核。</p>
    <div class="batch-feedback-targets"><el-tag v-for="item in targets" :key="item.versionId" size="small">{{ item.label }}</el-tag></div>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="busy">
      <el-form-item label="整体反馈意见" prop="content"><el-input v-model="form.content" type="textarea" :rows="6" maxlength="10000" show-word-limit placeholder="填写适用于所选任务的整体反馈意见" /></el-form-item>
    </el-form>
    <template #footer><el-button :disabled="busy" @click="visible = false">取消</el-button><el-button type="primary" :loading="busy" @click="save">发送意见并退回修改</el-button></template>
  </el-dialog>
</template>

<style scoped>
.batch-feedback-targets { display: flex; flex-wrap: wrap; gap: 6px; max-height: 160px; overflow: auto; margin: 14px 0; }
</style>
