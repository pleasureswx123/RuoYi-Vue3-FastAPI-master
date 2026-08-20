<script setup>
import { computed, reactive, ref } from 'vue'
import { archiveAsset, archiveAssetItem } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, required: true },
  item: { type: Object, default: null }
})
const emit = defineEmits(['close', 'archived', 'refresh'])
const targetIsItem = computed(() => Boolean(props.item?.assetItemId))
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: Number(props.asset.assetId),
  assetItemId: props.item?.assetItemId ? Number(props.item.assetItemId) : null,
  operationGeneration: Number(props.operationGeneration)
})
const archiveForm = ref(null)
const form = reactive({ reason: '' })
const saving = ref(false)
const requestError = ref(null)
const archiveRules = {
  reason: [{
    validator: (_rule, value, callback) => {
      if (!String(value || '').trim()) {
        callback(new Error('必须填写归档原因'))
        return
      }
      callback()
    },
    trigger: 'blur'
  }]
}

async function submit() {
  if (saving.value) return
  requestError.value = null
  const isValid = await archiveForm.value?.validate().catch(() => false)
  if (!isValid) return
  const normalizedReason = form.reason.trim()
  saving.value = true
  try {
    const response = targetIsItem.value
      ? await archiveAssetItem(operationContext.projectId, operationContext.assetItemId, {
          reason: normalizedReason,
          lockVersion: Number(props.item.lockVersion)
        })
      : await archiveAsset(operationContext.projectId, operationContext.assetId, {
          reason: normalizedReason,
          lockVersion: Number(props.asset.lockVersion)
        })
    emit('archived', response.data, operationContext)
  } catch (error) {
    requestError.value = assetErrorState(error, targetIsItem.value ? '制作分项归档失败' : '资产归档失败')
  } finally {
    saving.value = false
  }
}

function closeDialog() {
  if (saving.value) return
  archiveForm.value?.resetFields()
  archiveForm.value?.clearValidate()
  requestError.value = null
  emit('close')
}
</script>

<template>
  <ProjectModal :title="targetIsItem ? '归档制作分项' : '归档资产'" :description="targetIsItem ? `${asset.assetName} · ${item.productionItem || '未命名制作分项'}；历史任务与版本将继续保留。` : `${asset.assetName}；资产及历史版本将保留，归档后不再进入活动生产。`" :busy="saving" @close="closeDialog">
    <el-form ref="archiveForm" :model="form" :rules="archiveRules" class="archive-form" label-position="top" aria-label="资产归档表单">
      <el-alert title="请确认归档" description="请填写归档原因并确认目标；归档后历史记录仍会保留。" type="warning" show-icon :closable="false" />
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <el-form-item label="归档原因" prop="reason">
        <el-input v-model="form.reason" type="textarea" :rows="4" maxlength="500" show-word-limit :disabled="saving" placeholder="说明归档原因" />
      </el-form-item>
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="danger" :loading="saving" @click="submit">确认归档</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.archive-form{display:grid;gap:14px}.archive-form:deep(.el-form-item){margin-bottom:0}.archive-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.archive-form:deep(.el-textarea__inner){resize:vertical}.archive-form :deep(.el-alert__description){display:grid;gap:4px}.archive-form :deep(.el-alert code){font-size:10px}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
