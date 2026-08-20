<script setup>
import { computed, reactive, ref } from 'vue'
import { createAssetItem, updateAssetItem } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState, memberLabel } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, required: true },
  item: { type: Object, default: null },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const isEdit = computed(() => Boolean(props.item?.assetItemId))
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: Number(props.asset.assetId),
  assetItemId: props.item?.assetItemId ? Number(props.item.assetItemId) : null,
  operationGeneration: Number(props.operationGeneration)
})
const form = reactive({
  productionItem: props.item?.productionItem || '',
  description: props.item?.description || '',
  sortOrder: Number(props.item?.sortOrder || 0),
  assigneeUserId: props.item?.task?.assigneeUserId ? String(props.item.task.assigneeUserId) : '',
  taskDescription: props.item?.task?.requirements || '',
  remark: props.item?.remark || ''
})
const itemForm = ref(null)
const saving = ref(false)
const requestError = ref(null)
const itemRules = {
  productionItem: [{
    validator: (_rule, value, callback) => {
      if (form.assigneeUserId && !String(value || '').trim()) {
        callback(new Error('首次分配制作人前必须填写制作分项'))
        return
      }
      callback()
    },
    trigger: 'blur'
  }],
  sortOrder: [{
    validator: (_rule, value, callback) => {
      if (!Number.isInteger(Number(value)) || Number(value) < 0) {
        callback(new Error('排序必须是非负整数'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

async function submit() {
  if (saving.value) return
  requestError.value = null
  const isValid = await itemForm.value?.validate().catch(() => false)
  if (!isValid) return
  const common = {
    productionItem: optionalText(form.productionItem),
    description: optionalText(form.description),
    sortOrder: Number(form.sortOrder),
    remark: optionalText(form.remark)
  }
  saving.value = true
  try {
    const response = isEdit.value
      ? await updateAssetItem(operationContext.projectId, operationContext.assetItemId, {
          ...common,
          ...(!props.item.task && form.assigneeUserId ? {
            assigneeUserId: Number(form.assigneeUserId),
            taskDescription: optionalText(form.taskDescription)
          } : {}),
          lockVersion: Number(props.item.lockVersion)
        })
      : await createAssetItem(operationContext.projectId, operationContext.assetId, {
          ...common,
          assigneeUserId: form.assigneeUserId ? Number(form.assigneeUserId) : null,
          taskDescription: optionalText(form.taskDescription)
        })
    emit('saved', response.data, operationContext)
  } catch (error) {
    requestError.value = assetErrorState(error, isEdit.value ? '制作分项修改失败' : '制作分项创建失败')
  } finally {
    saving.value = false
  }
}

function closeDialog() {
  if (saving.value) return
  itemForm.value?.resetFields()
  itemForm.value?.clearValidate()
  requestError.value = null
  emit('close')
}
</script>

<template>
  <ProjectModal :title="isEdit ? '编辑制作分项' : `新增制作分项 · ${asset.assetName}`" description="制作分项是独立分配、提交图片版本和审核的最小生产单元；已有版本后，关键制作信息不可再修改。" :busy="saving" @close="closeDialog">
    <el-form ref="itemForm" :model="form" :rules="itemRules" class="item-form" size="large" label-position="top" aria-label="资产制作分项表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <el-form-item label="制作分项" prop="productionItem"><el-input v-model="form.productionItem" maxlength="240" :disabled="saving" placeholder="未分配时可留空；分配任务前必须填写" /></el-form-item>
      <el-form-item label="分项说明" prop="description"><el-input v-model="form.description" type="textarea" :rows="3" :disabled="saving" /></el-form-item>
      <el-form-item label="排序" prop="sortOrder"><el-input-number v-model="form.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="saving" /></el-form-item>
      <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit :disabled="saving" /></el-form-item>
      <template v-if="!item?.task">
        <el-form-item label="首次分配制作人" prop="assigneeUserId"><el-select v-model="form.assigneeUserId" class="sg-select" :placeholder="form.productionItem.trim() ? '暂不分配' : '请先填写制作分项'" :disabled="saving || !form.productionItem.trim()"><el-option label="暂不分配" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
        <el-form-item v-if="form.assigneeUserId" label="首次任务要求" prop="taskDescription"><el-input v-model="form.taskDescription" type="textarea" :rows="2" :disabled="saving" /></el-form-item>
      </template>
      <el-alert v-else title="该分项已有任务" description="如需更换负责人，请使用“改派任务”；编辑分项信息不会变更负责人。" type="info" show-icon :closable="false" />
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ isEdit ? '保存分项' : '新增分项' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.item-form{display:grid;gap:14px}.item-form:deep(.el-form-item){margin-bottom:0}.item-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.item-form:deep(.el-select),.item-form:deep(.el-input-number){width:100%}.item-form:deep(.el-textarea__inner){resize:vertical}.item-form :deep(.el-alert__description){display:grid;gap:4px}.item-form :deep(.el-alert code){font-size:10px}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
