<script setup>
import { computed, reactive, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

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
const saving = ref(false)
const validationMessage = ref('')
const requestError = ref(null)

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

async function submit() {
  requestError.value = null
  validationMessage.value = Number.isInteger(Number(form.sortOrder)) && Number(form.sortOrder) >= 0 ? '' : '排序必须是非负整数'
  if (validationMessage.value) return
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
</script>

<template>
  <ProjectModal :title="isEdit ? '编辑制作分项' : `新增制作分项 · ${asset.assetName}`" description="制作分项是独立分配、提交图片版本和审核的最小生产单元。已有版本后主数据将失败关闭。" :busy="saving" @close="emit('close')">
    <form class="item-form" @submit.prevent="submit">
      <div v-if="validationMessage || requestError" class="item-form__error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ requestError?.title || '请检查表单' }}</strong><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新后重试</button></div></div>
      <label><span>制作分项</span><input v-model="form.productionItem" maxlength="240" :disabled="saving" placeholder="允许留空，提交版本前必须补齐" /></label>
      <label><span>分项说明</span><textarea v-model="form.description" rows="3" :disabled="saving" /></label>
      <label><span>排序</span><input v-model.number="form.sortOrder" type="number" min="0" step="1" :disabled="saving" /></label>
      <label><span>备注</span><textarea v-model="form.remark" rows="2" maxlength="500" :disabled="saving" /></label>
      <template v-if="!item?.task">
        <label><span>首次分配制作人</span><select v-model="form.assigneeUserId" :disabled="saving"><option value="">暂不分配</option><option v-for="member in members" :key="member.userId" :value="String(member.userId)">{{ memberLabel(member) }}</option></select></label>
        <label v-if="form.assigneeUserId"><span>首次任务要求</span><textarea v-model="form.taskDescription" rows="2" :disabled="saving" /></label>
      </template>
      <p v-else class="item-form__task-note">该分项已有任务；负责人变更必须使用“改派任务”，不会通过主数据编辑静默改派。</p>
      <footer><el-button :disabled="saving" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">{{ isEdit ? '保存分项' : '新增分项' }}</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.item-form{display:grid;gap:14px}.item-form label{display:grid;gap:6px}.item-form label span{color:var(--sg-text-muted);font-size:11px}.item-form input,.item-form select,.item-form textarea{width:100%;box-sizing:border-box;padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.item-form textarea{resize:vertical}.item-form__error{display:grid;grid-template-columns:auto 1fr;gap:10px;padding:14px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:10px}.item-form__error p{margin:4px 0;font-size:12px}.item-form__error code{font-size:10px}.item-form__error button{display:block;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.item-form__task-note{margin:0;padding:11px;color:var(--sg-accent);font-size:11px;background:var(--sg-accent-soft);border-radius:8px}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
