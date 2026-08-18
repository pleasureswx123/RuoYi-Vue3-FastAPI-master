<script setup>
import { computed, reactive, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

import { assignAssetItemTask } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState, memberLabel } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, required: true },
  item: { type: Object, required: true },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'assigned', 'refresh'])
const isReassign = computed(() => Boolean(props.item.task?.taskId))
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: Number(props.asset.assetId),
  assetItemId: Number(props.item.assetItemId),
  operationGeneration: Number(props.operationGeneration),
  wasReassign: Boolean(props.item.task?.taskId)
})
const form = reactive({
  assigneeUserId: props.item.task?.assigneeUserId ? String(props.item.task.assigneeUserId) : '',
  taskDescription: props.item.task?.requirements || '',
  priority: props.item.task?.priority || 'normal',
  dueDate: props.item.task?.dueDate || ''
})
const saving = ref(false)
const validationMessage = ref('')
const requestError = ref(null)

async function submit() {
  validationMessage.value = !String(props.item.productionItem || '').trim()
    ? '请先编辑资产并填写制作分项，再分配或改派任务'
    : form.assigneeUserId ? '' : '请选择唯一主制作人'
  requestError.value = null
  if (validationMessage.value) return
  saving.value = true
  try {
    const response = await assignAssetItemTask(operationContext.projectId, operationContext.assetItemId, {
      assigneeUserId: Number(form.assigneeUserId),
      taskDescription: form.taskDescription.trim() || null,
      priority: form.priority,
      dueDate: form.dueDate || null,
      taskLockVersion: props.item.task ? Number(props.item.task.lockVersion) : null
    })
    emit('assigned', response.data, operationContext)
  } catch (error) {
    requestError.value = assetErrorState(error, isReassign.value ? '资产任务改派失败' : '资产任务分配失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ProjectModal :title="isReassign ? '改派资产任务' : '分配资产任务'" :description="`${asset.assetName} · ${item.productionItem || '未命名制作分项'}；制作分项名称完整后才能进入任务分配。`" :busy="saving" @close="emit('close')">
    <form class="assign-form" @submit.prevent="submit">
      <div v-if="validationMessage || requestError" class="assign-form__error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ requestError?.title || '请检查任务分配' }}</strong><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新后重试</button></div></div>
      <label><span>唯一主制作人</span><el-select v-model="form.assigneeUserId" class="sg-select" placeholder="请选择" :disabled="saving"><el-option label="请选择" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></label>
      <label><span>任务要求</span><textarea v-model="form.taskDescription" rows="4" :disabled="saving" placeholder="说明图片交付要求" /></label>
      <div class="assign-form__grid"><label><span>优先级</span><el-select v-model="form.priority" class="sg-select" :disabled="saving"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></label><label><span>截止日期</span><input v-model="form.dueDate" type="date" :disabled="saving" /></label></div>
      <p v-if="isReassign" class="assign-form__notice">改派将携带当前任务锁版本；存在任何未正式提交的版本发布记录时，后端会拒绝改派。</p>
      <footer><el-button :disabled="saving" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">{{ isReassign ? '确认改派' : '确认分配' }}</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.assign-form{display:grid;gap:14px}.assign-form label{display:grid;gap:6px}.assign-form label span{color:var(--sg-text-muted);font-size:11px}.assign-form input,.assign-form select,.assign-form textarea{width:100%;box-sizing:border-box;padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.assign-form textarea{resize:vertical}.assign-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.assign-form__notice{margin:0;padding:11px;color:var(--sg-accent);font-size:11px;background:var(--sg-accent-soft);border-radius:8px}.assign-form__error{display:grid;grid-template-columns:auto 1fr;gap:10px;padding:14px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:10px}.assign-form__error p{margin:4px 0;font-size:12px}.assign-form__error code{font-size:10px}.assign-form__error button{display:block;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:620px){.assign-form__grid{grid-template-columns:1fr}}
</style>
