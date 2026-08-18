<script setup>
import { computed, reactive, ref } from 'vue'
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
const assignForm = ref(null)
const saving = ref(false)
const requestError = ref(null)
const assignRules = {
  assigneeUserId: [{
    validator: (_rule, value, callback) => {
      if (!String(props.item.productionItem || '').trim()) {
        callback(new Error('请先编辑资产并填写制作分项，再分配或改派任务'))
        return
      }
      if (!value) {
        callback(new Error('请选择唯一主制作人'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  priority: [{ required: true, message: '请选择任务优先级', trigger: 'change' }]
}

async function submit() {
  if (saving.value) return
  requestError.value = null
  const isValid = await assignForm.value?.validate().catch(() => false)
  if (!isValid) return
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

function closeDialog() {
  if (saving.value) return
  assignForm.value?.resetFields()
  assignForm.value?.clearValidate()
  requestError.value = null
  emit('close')
}
</script>

<template>
  <ProjectModal :title="isReassign ? '改派资产任务' : '分配资产任务'" :description="`${asset.assetName} · ${item.productionItem || '未命名制作分项'}；制作分项名称完整后才能进入任务分配。`" :busy="saving" @close="closeDialog">
    <el-form ref="assignForm" :model="form" :rules="assignRules" class="assign-form" size="large" label-position="top" aria-label="资产任务分配表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><code v-if="requestError.errorKey">{{ requestError.errorKey }}</code><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <el-form-item label="唯一主制作人" prop="assigneeUserId"><el-select v-model="form.assigneeUserId" class="sg-select" placeholder="请选择" :disabled="saving"><el-option label="请选择" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
      <el-form-item label="任务要求" prop="taskDescription"><el-input v-model="form.taskDescription" type="textarea" :rows="4" :disabled="saving" placeholder="说明图片交付要求" /></el-form-item>
      <div class="assign-form__grid"><el-form-item label="优先级" prop="priority"><el-select v-model="form.priority" class="sg-select" :disabled="saving"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item><el-form-item label="截止日期" prop="dueDate"><el-date-picker v-model="form.dueDate" type="date" value-format="YYYY-MM-DD" placeholder="请选择截止日期" :disabled="saving" /></el-form-item></div>
      <el-alert v-if="isReassign" title="改派并发约束" description="改派将携带当前任务锁版本；存在任何未正式提交的版本发布记录时，后端会拒绝改派。" type="warning" show-icon :closable="false" />
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ isReassign ? '确认改派' : '确认分配' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.assign-form{display:grid;gap:14px}.assign-form:deep(.el-form-item){margin-bottom:0}.assign-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.assign-form:deep(.el-select),.assign-form:deep(.el-date-editor){width:100%}.assign-form:deep(.el-textarea__inner){resize:vertical}.assign-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.assign-form :deep(.el-alert__description){display:grid;gap:4px}.assign-form :deep(.el-alert code){font-size:10px}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:620px){.assign-form__grid{grid-template-columns:1fr}}
</style>
