<script setup>
import { onBeforeUnmount, reactive, ref } from 'vue'

import { deleteAssetItem } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, required: true },
  item: { type: Object, required: true }
})
const emit = defineEmits(['close', 'deleted', 'refresh'])
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: Number(props.asset.assetId),
  assetItemId: Number(props.item.assetItemId),
  lockVersion: Number(props.item.lockVersion),
  operationGeneration: Number(props.operationGeneration)
})
const targetName = `${props.asset.assetName} · ${props.item.productionItem || '未命名制作分项'}`
const deleteForm = ref(null)
const form = reactive({ reason: '' })
const saving = ref(false)
const requestError = ref(null)
let disposed = false
const rules = {
  reason: [{
    validator: (_rule, value, callback) => {
      callback(String(value || '').trim() ? undefined : new Error('请填写删除原因'))
    },
    trigger: 'blur'
  }]
}

async function submit() {
  if (saving.value || disposed) return
  saving.value = true
  requestError.value = null
  try {
    const valid = await deleteForm.value?.validate().catch(() => false)
    if (!valid || disposed) return
    const response = await deleteAssetItem(operationContext.projectId, operationContext.assetItemId, {
      reason: form.reason.trim(),
      lockVersion: operationContext.lockVersion
    })
    if (!disposed) emit('deleted', response.data, operationContext)
  } catch (error) {
    if (!disposed) requestError.value = assetErrorState(error, '制作分项删除失败')
  } finally {
    saving.value = false
  }
}

function closeDialog() {
  if (saving.value) return
  deleteForm.value?.resetFields()
  deleteForm.value?.clearValidate()
  requestError.value = null
  emit('close')
}

onBeforeUnmount(() => { disposed = true })
</script>

<template>
  <ProjectModal title="删除制作分项" :description="targetName" :busy="saving" @close="closeDialog">
    <el-form ref="deleteForm" :model="form" :rules="rules" class="delete-item-form" label-position="top" aria-label="删除制作分项表单">
      <el-alert title="请确认删除此分项" description="仅允许删除尚未开始制作、没有版本或待处理提交的分项。资产和其他分项不受影响，操作记录会保留。" type="warning" show-icon :closable="false" />
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false">
        <span>{{ requestError.message }}</span>
        <el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button>
      </el-alert>
      <el-form-item label="删除原因" prop="reason">
        <el-input v-model="form.reason" type="textarea" :rows="3" maxlength="500" show-word-limit :disabled="saving" placeholder="说明删除原因，例如：新增后不再需要" />
      </el-form-item>
      <footer>
        <el-button :disabled="saving" @click="closeDialog">取消</el-button>
        <el-button type="danger" :loading="saving" :disabled="saving" @click="submit">确认删除</el-button>
      </footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.delete-item-form { display: grid; gap: 14px; }
.delete-item-form :deep(.el-form-item) { margin-bottom: 0; }
.delete-item-form :deep(.el-alert__description) { display: grid; gap: 4px; }
footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
