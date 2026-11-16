<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { assignAssetItemTask } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import AssetProductionInfo from './AssetProductionInfo.vue'
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
  taskDescription: props.item.task?.requirements || ''
})
const assignForm = ref(null)
const saving = ref(false)
let disposed = false
onBeforeUnmount(() => { disposed = true })
const requestError = ref(null)
const assignRules = {
  assigneeUserId: [{
    validator: (_rule, value, callback) => {
      if (!String(props.item.productionItem || '').trim()) {
        callback(new Error('请先编辑资产并填写制作分项，再分配或改派任务'))
        return
      }
      if (!props.members.some(member => Number(member.userId) === Number(value))) {
        callback(new Error('请选择有效制作人'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}

async function submit() {
  if (saving.value || disposed) return
  saving.value = true
  requestError.value = null
  try {
    const isValid = await assignForm.value?.validate().catch(() => false)
    if (!isValid || disposed) return
    const response = await assignAssetItemTask(operationContext.projectId, operationContext.assetItemId, {
      assigneeUserId: Number(form.assigneeUserId),
      taskDescription: form.taskDescription.trim() || null,
      taskLockVersion: props.item.task ? Number(props.item.task.lockVersion) : null
    })
    if (!disposed) emit('assigned', response.data, operationContext)
  } catch (error) {
    if (!disposed) requestError.value = assetErrorState(error, isReassign.value ? '资产任务改派失败' : '资产任务分配失败')
  } finally {
    if (!disposed) saving.value = false
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
  <ProjectModal :title="isReassign ? '改派制作人' : '分配制作人'" :description="`${asset.assetName} · ${item.productionItem || '未命名制作分项'}`" :busy="saving" @close="closeDialog">
    <el-form ref="assignForm" :model="form" :rules="assignRules" class="assign-form" size="large" label-position="top" aria-label="资产任务分配表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <el-form-item label="制作人" prop="assigneeUserId"><el-select v-model="form.assigneeUserId" filterable class="sg-select" placeholder="搜索或选择制作人" :disabled="saving"><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
      <el-form-item label="任务要求" prop="taskDescription"><el-input v-model="form.taskDescription" type="textarea" :rows="4" :disabled="saving" placeholder="说明图片交付要求" /></el-form-item>
      <el-collapse><el-collapse-item title="查看已有制作要求" name="requirements"><AssetProductionInfo :asset="asset" :item="item" /></el-collapse-item></el-collapse>
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ isReassign ? '确认改派' : '确认分配' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.assign-form{display:grid;gap:14px}.assign-form:deep(.el-form-item){margin-bottom:0}.assign-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.assign-form:deep(.el-select),.assign-form:deep(.el-date-editor){width:100%}.assign-form:deep(.el-textarea__inner){resize:vertical}.assign-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.assign-form :deep(.el-alert__description){display:grid;gap:4px}.assign-form :deep(.el-alert code){font-size:10px}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:620px){.assign-form__grid{grid-template-columns:1fr}}
</style>
