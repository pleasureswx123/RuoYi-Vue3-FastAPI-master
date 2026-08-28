<script setup>
import { computed, reactive, ref } from 'vue'
import { createAssetItem, updateAssetItem } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, required: true },
  item: { type: Object, default: null }
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
  remark: props.item?.remark || ''
})
const itemForm = ref(null)
const saving = ref(false)
const requestError = ref(null)
const itemRules = {
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
          lockVersion: Number(props.item.lockVersion)
        })
      : await createAssetItem(operationContext.projectId, operationContext.assetId, common)
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
  <ProjectModal :title="isEdit ? '编辑制作分项' : `新增制作分项 · ${asset.assetName}`" :description="isEdit ? '制作分项是独立分配、提交图片版本和审核的最小生产单元；管理人员确认开工后，制作信息不可再修改。' : '先新增未分配制作分项；保存后再通过“分配任务”选择制作人并创建任务。'" :busy="saving" @close="closeDialog">
    <el-form ref="itemForm" :model="form" :rules="itemRules" class="item-form" size="large" label-position="top" aria-label="资产制作分项表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <el-descriptions :column="1" border aria-label="所属资产信息">
        <el-descriptions-item label="资产">{{ asset.assetName }}</el-descriptions-item>
        <el-descriptions-item label="资产描述">{{ asset.description || '暂无资产描述' }}</el-descriptions-item>
      </el-descriptions>
      <el-form-item label="制作分项" prop="productionItem"><el-input v-model="form.productionItem" maxlength="240" :disabled="saving" placeholder="未分配时可留空；分配任务前必须填写" /></el-form-item>
      <el-form-item label="分项补充要求" prop="description"><el-input v-model="form.description" type="textarea" :rows="3" :disabled="saving" placeholder="仅填写该分项独有的要求，可留空；资产描述由所有分项共用" /></el-form-item>
      <el-form-item label="排序" prop="sortOrder"><el-input-number v-model="form.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="saving" /></el-form-item>
      <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit :disabled="saving" /></el-form-item>
      <el-alert v-if="item?.task" title="该分项已有任务" description="如需更换负责人，请使用“改派任务”；编辑分项信息不会变更负责人。" type="info" show-icon :closable="false" />
      <el-alert v-else title="保存后状态：未分配" description="保存制作分项不会创建任务；请通过分项对应的“分配任务”完成委派。" type="info" show-icon :closable="false" />
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ isEdit ? '保存分项' : '新增分项' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.item-form{display:grid;gap:14px}.item-form:deep(.el-form-item){margin-bottom:0}.item-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.item-form:deep(.el-select),.item-form:deep(.el-input-number){width:100%}.item-form:deep(.el-textarea__inner){resize:vertical}.item-form :deep(.el-alert__description){display:grid;gap:4px}.item-form :deep(.el-alert code){font-size:10px}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
