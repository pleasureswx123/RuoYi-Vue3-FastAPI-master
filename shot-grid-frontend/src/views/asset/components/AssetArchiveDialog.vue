<script setup>
import { computed, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

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
const reason = ref('')
const saving = ref(false)
const validationMessage = ref('')
const requestError = ref(null)

async function submit() {
  const normalizedReason = reason.value.trim()
  validationMessage.value = normalizedReason ? '' : '必须填写归档原因'
  requestError.value = null
  if (validationMessage.value) return
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
</script>

<template>
  <ProjectModal :title="targetIsItem ? '归档制作分项' : '归档资产'" :description="targetIsItem ? `${asset.assetName} · ${item.productionItem || '未命名制作分项'}；历史任务与版本不会被级联删除。` : `${asset.assetName}；资产及历史版本将保留，归档后不再进入活动生产。`" :busy="saving" @close="emit('close')">
    <form class="archive-form" @submit.prevent="submit">
      <div class="archive-form__warning"><el-icon><WarningFilled /></el-icon><span>这是受控业务动作，请填写可审计原因并确认目标。</span></div>
      <div v-if="validationMessage || requestError" class="archive-form__error" role="alert"><strong>{{ requestError?.title || '请检查归档条件' }}</strong><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新后重试</button></div>
      <label><span>归档原因</span><textarea v-model="reason" rows="4" maxlength="500" :disabled="saving" placeholder="说明归档原因" /></label>
      <footer><el-button :disabled="saving" @click="emit('close')">取消</el-button><el-button type="danger" native-type="submit" :loading="saving">确认归档</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.archive-form{display:grid;gap:14px}.archive-form__warning{display:flex;gap:9px;align-items:center;padding:12px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:9px}.archive-form__error{padding:13px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:9px}.archive-form__error p{margin:4px 0;font-size:12px}.archive-form__error code{font-size:10px}.archive-form__error button{display:block;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.archive-form label{display:grid;gap:6px}.archive-form label span{color:var(--sg-text-muted);font-size:11px}.archive-form textarea{width:100%;box-sizing:border-box;padding:10px 11px;color:var(--sg-text);resize:vertical;background:#11151a;border:1px solid var(--sg-border);border-radius:8px}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
