<script setup>
import { computed, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'

import { createAsset, updateAsset } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState, memberLabel } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  asset: { type: Object, default: null },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const isEdit = computed(() => Boolean(props.asset?.assetId))
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: props.asset?.assetId ? Number(props.asset.assetId) : null,
  operationGeneration: Number(props.operationGeneration)
})
let nextItemKey = 1
const form = reactive({
  assetType: props.asset?.assetType || 'Character',
  assetName: props.asset?.assetName || '',
  description: props.asset?.description || '',
  sortOrder: Number(props.asset?.sortOrder || 0),
  remark: props.asset?.remark || '',
  items: isEdit.value ? [] : [newItem()]
})
const assetForm = ref(null)
const saving = ref(false)
const requestError = ref(null)
const assetFormRules = {
  assetType: [{ required: true, message: '请选择资产类型', trigger: 'change' }],
  assetName: [{
    validator: (_rule, value, callback) => {
      if (!isEdit.value && !String(value || '').trim()) {
        callback(new Error('资产名称不能为空'))
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

function newItem() {
  const item = {
    localKey: nextItemKey++,
    productionItem: '',
    description: '',
    sortOrder: 0,
    assigneeUserId: '',
    taskDescription: '',
    remark: ''
  }
  item.formRules = {
    productionItem: [{
      validator: (_rule, value, callback) => {
        const normalized = String(value || '').trim()
        if (item.assigneeUserId && !normalized) {
          callback(new Error('分配主制作人前必须填写对应制作分项'))
          return
        }
        if (normalized) {
          const normalizedName = normalized.toLocaleLowerCase()
          const duplicated = form.items.some(candidate => (
            candidate.localKey !== item.localKey && candidate.productionItem.trim().toLocaleLowerCase() === normalizedName
          ))
          if (duplicated) {
            callback(new Error('同一资产内制作分项名称不能重复'))
            return
          }
        }
        callback()
      },
      trigger: 'blur'
    }],
    sortOrder: [{
      validator: (_rule, value, callback) => {
        if (!Number.isInteger(Number(value)) || Number(value) < 0) {
          callback(new Error('制作分项排序必须是非负整数'))
          return
        }
        callback()
      },
      trigger: 'change'
    }]
  }
  return item
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

function addItem() {
  form.items.push(newItem())
  assetForm.value?.clearValidate()
}

function removeItem(index) {
  if (form.items.length <= 1) return
  form.items.splice(index, 1)
  assetForm.value?.clearValidate()
}

function buildCreatePayload() {
  return {
    assetType: form.assetType,
    assetName: form.assetName.trim(),
    description: optionalText(form.description),
    sortOrder: Number(form.sortOrder),
    remark: optionalText(form.remark),
    items: form.items.map(item => ({
      productionItem: optionalText(item.productionItem),
      description: optionalText(item.description),
      sortOrder: Number(item.sortOrder),
      assigneeUserId: item.assigneeUserId ? Number(item.assigneeUserId) : null,
      taskDescription: optionalText(item.taskDescription),
      remark: optionalText(item.remark)
    }))
  }
}

async function submit() {
  if (saving.value) return
  requestError.value = null
  const isValid = await assetForm.value?.validate().catch(() => false)
  if (!isValid) return
  saving.value = true
  try {
    const response = isEdit.value
      ? await updateAsset(operationContext.projectId, operationContext.assetId, {
          description: optionalText(form.description),
          sortOrder: Number(form.sortOrder),
          remark: optionalText(form.remark),
          lockVersion: Number(props.asset.lockVersion)
        })
      : await createAsset(operationContext.projectId, buildCreatePayload())
    emit('saved', response.data, operationContext)
  } catch (error) {
    requestError.value = assetErrorState(error, isEdit.value ? '资产修改失败' : '资产创建失败')
  } finally {
    saving.value = false
  }
}

function closeDialog() {
  if (saving.value) return
  assetForm.value?.resetFields()
  assetForm.value?.clearValidate()
  requestError.value = null
  emit('close')
}
</script>

<template>
  <ProjectModal :title="isEdit ? `编辑资产 · ${asset.assetName}` : '新建资产'" :description="isEdit ? '资产类型、名称和目录身份不可普通修改；此处保存非身份主数据完整快照。' : '创建资产时至少创建一个制作分项；制作人可稍后通过任务分配补充。'" :busy="saving" wide @close="closeDialog">
    <el-form ref="assetForm" :model="form" :rules="assetFormRules" class="asset-form" size="large" label-position="top" aria-label="资产主数据表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><code v-if="requestError.errorKey">{{ requestError.errorKey }}</code><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>

      <section class="asset-form__grid">
        <el-form-item label="资产类型" prop="assetType"><el-select v-model="form.assetType" class="sg-select" :disabled="isEdit || saving"><el-option label="角色" value="Character" /><el-option label="场景" value="Environment" /><el-option label="道具" value="Prop" /></el-select></el-form-item>
        <el-form-item label="资产名称" prop="assetName"><el-input v-model="form.assetName" maxlength="200" show-word-limit :disabled="isEdit || saving" placeholder="例如：动力舱室内" /></el-form-item>
        <el-form-item label="项目内排序" prop="sortOrder"><el-input-number v-model="form.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="saving" /></el-form-item>
        <el-form-item class="asset-form__wide" label="资产说明" prop="description"><el-input v-model="form.description" type="textarea" :rows="3" :disabled="saving" placeholder="资产的稳定业务说明" /></el-form-item>
        <el-form-item class="asset-form__wide" label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit :disabled="saving" placeholder="内部备注，可留空" /></el-form-item>
      </section>

      <el-card v-if="!isEdit" class="asset-items-editor" shadow="never">
        <template #header><header><div><strong>首批制作分项</strong><p>未分配的分项名称允许暂缺；选择制作人前必须填写完整。</p></div><el-button :icon="Plus" :disabled="saving || form.items.length >= 200" @click="addItem">添加分项</el-button></header></template>
        <el-card v-for="(item,index) in form.items" :key="item.localKey" class="asset-item-editor" shadow="never">
          <template #header><div class="asset-items-editor__heading"><strong>分项 {{ index + 1 }}</strong><el-button link type="danger" :disabled="saving || form.items.length <= 1" @click="removeItem(index)">移除</el-button></div></template>
          <div class="asset-items-editor__grid">
            <el-form-item label="制作分项" :prop="`items.${index}.productionItem`" :rules="item.formRules.productionItem"><el-input v-model="item.productionItem" maxlength="240" :disabled="saving" placeholder="允许稍后补齐" /></el-form-item>
            <el-form-item label="排序" :prop="`items.${index}.sortOrder`" :rules="item.formRules.sortOrder"><el-input-number v-model="item.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="saving" /></el-form-item>
            <el-form-item label="主制作人" :prop="`items.${index}.assigneeUserId`"><el-select v-model="item.assigneeUserId" class="sg-select" :placeholder="item.productionItem.trim() ? '暂不分配' : '请先填写制作分项'" :disabled="saving || !item.productionItem.trim()"><el-option label="暂不分配" value="" /><el-option v-for="member in members" :key="member.userId" :label="memberLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
            <el-form-item class="asset-items-editor__wide" label="分项说明" :prop="`items.${index}.description`"><el-input v-model="item.description" type="textarea" :rows="2" :disabled="saving" /></el-form-item>
            <el-form-item class="asset-items-editor__wide" label="首次任务要求" :prop="`items.${index}.taskDescription`"><el-input v-model="item.taskDescription" type="textarea" :rows="2" :disabled="saving || !item.assigneeUserId" /></el-form-item>
            <el-form-item class="asset-items-editor__wide" label="备注" :prop="`items.${index}.remark`"><el-input v-model="item.remark" maxlength="500" :disabled="saving" /></el-form-item>
          </div>
        </el-card>
      </el-card>

      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ isEdit ? '保存资产' : '创建资产' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.asset-form{display:grid;gap:18px}.asset-form :deep(.el-alert__description){display:grid;gap:4px}.asset-form :deep(.el-alert code){font-size:10px}.asset-form__grid,.asset-items-editor__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.asset-form:deep(.el-form-item){min-width:0;margin-bottom:0}.asset-form:deep(.el-form-item__label){color:var(--sg-text-muted);font-size:11px}.asset-form:deep(.el-select),.asset-form:deep(.el-input-number){width:100%}.asset-form:deep(.el-textarea__inner){resize:vertical}.asset-form__wide,.asset-items-editor__wide{grid-column:1/-1}.asset-items-editor{background:rgba(255,255,255,.015);border-color:var(--sg-border)}.asset-items-editor:deep(>.el-card__header){padding:14px 16px;border-bottom-color:var(--sg-border)}.asset-items-editor:deep(>.el-card__body){display:grid;gap:12px;padding:14px}.asset-items-editor header,.asset-items-editor__heading,footer{display:flex;gap:12px;align-items:center;justify-content:space-between}.asset-items-editor header p{margin:4px 0 0;color:var(--sg-text-muted);font-size:11px}.asset-item-editor{background:rgba(255,255,255,.025);border-color:var(--sg-border);border-radius:11px}.asset-item-editor:deep(.el-card__header){padding:10px 14px;border-bottom-color:var(--sg-border)}.asset-item-editor:deep(.el-card__body){padding:14px}.asset-items-editor__heading{width:100%}footer{justify-content:flex-end}@media(max-width:760px){.asset-form__grid,.asset-items-editor__grid{grid-template-columns:1fr}.asset-form__wide,.asset-items-editor__wide{grid-column:auto}}
</style>
