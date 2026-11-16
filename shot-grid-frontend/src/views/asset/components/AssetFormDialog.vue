<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'

import AssetRelationSelect from './AssetRelationSelect.vue'
import { createAsset, updateAsset } from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { assetErrorState } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  canLink: { type: Boolean, default: false },
  canAssign: { type: Boolean, default: false },
  initialType: { type: String, default: 'Character' },
  asset: { type: Object, default: null }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const isEdit = computed(() => Boolean(props.asset?.assetId))
const originalDescription = props.asset?.description ?? null
const descriptionLockedByConflict = ref(false)
const descriptionLocked = computed(() => isEdit.value && (
  descriptionLockedByConflict.value || props.asset?.descriptionLocked !== false
))
const descriptionLockHint = computed(() => descriptionLockedByConflict.value || props.asset?.descriptionLocked === true
  ? '已有制作分项开工，资产描述已锁定；仍可修改名称、排序和备注。'
  : '暂无法确认资产描述是否可编辑，请刷新后重试。')
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  assetId: props.asset?.assetId ? Number(props.asset.assetId) : null,
  operationGeneration: Number(props.operationGeneration)
})
let nextItemKey = 1
const form = reactive({
  assetType: props.asset?.assetType || (['Character', 'Environment', 'Prop'].includes(props.initialType) ? props.initialType : 'Character'),
  assetName: props.asset?.assetName || '',
  description: props.asset?.description || '',
  sortOrder: Number(props.asset?.sortOrder || 0),
  remark: props.asset?.remark || '',
  relatedAssetIds: [],
  items: isEdit.value ? [] : [newItem('基础设定')]
})
const moreSettings = ref([])
const itemPresets = computed(() => ({ Character: ['正面', '侧面', '背面', '表情'], Environment: ['全景', '近景', '细节'], Prop: ['整体', '多视图', '细节'] })[form.assetType] || [])
const hasItem = name => form.items.some(item => item.productionItem.trim() === name)
const assetForm = ref(null)
const saving = ref(false)
const continueAssign = ref(false)
const requestError = ref(null)
let disposed = false
onBeforeUnmount(() => { disposed = true })
const assetFormRules = {
  relatedAssetIds: [{ validator: (_rule, ids, done) => done(Array.isArray(ids) && ids.length <= 50 && ids.every(id => Number.isSafeInteger(id) && id > 0) && new Set(ids).size === ids.length ? undefined : new Error('请选择有效且不重复的关联资产（最多 50 项）')), trigger: 'change' }],
  assetType: [{ required: true, message: '请选择资产类型', trigger: 'change' }],
  assetName: [{
    validator: (_rule, value, callback) => {
      if (!String(value || '').trim()) {
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

function newItem(name = '') {
  const item = {
    localKey: nextItemKey++,
    productionItem: name,
    description: '',
    sortOrder: 0,
    remark: ''
  }
  item.formRules = {
    productionItem: [{
      validator: (_rule, value, callback) => {
        const normalized = String(value || '').trim()
        if (continueAssign.value && !normalized) { callback(new Error('请填写制作分项名称后再分配')); return }
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

function addItem(name = '') {
  if (saving.value || form.items.length >= 200 || (name && hasItem(name))) return
  form.items.push(newItem(name))
  assetForm.value?.clearValidate()
}

function removeItem(index) {
  if (form.items.length <= 1) return
  form.items.splice(index, 1)
  assetForm.value?.clearValidate()
}

function buildCreatePayload() {
  return {
    ...(form.relatedAssetIds.length ? { relatedAssetIds: [...form.relatedAssetIds] } : {}),
    assetType: form.assetType,
    assetName: form.assetName.trim(),
    description: optionalText(form.description),
    sortOrder: Number(form.sortOrder),
    remark: optionalText(form.remark),
    items: form.items.map(item => ({
      productionItem: optionalText(item.productionItem),
      description: optionalText(item.description),
      sortOrder: Number(item.sortOrder),
      remark: optionalText(item.remark)
    }))
  }
}

async function submit(nextAction = '') {
  if (saving.value || disposed) return
  if (nextAction === 'assign' && (!props.canAssign || isEdit.value)) return
  if (nextAction === 'assign' && form.items.length > 100) return
  saving.value = true
  continueAssign.value = nextAction === 'assign'
  requestError.value = null
  try {
    const isValid = await assetForm.value?.validate().catch(() => false)
    if (!isValid || disposed) return
    const response = isEdit.value
      ? await updateAsset(operationContext.projectId, operationContext.assetId, {
          assetName: form.assetName.trim(),
          description: optionalText(descriptionLocked.value ? originalDescription : form.description),
          sortOrder: Number(form.sortOrder),
          remark: optionalText(form.remark),
          lockVersion: Number(props.asset.lockVersion)
        })
      : await createAsset(operationContext.projectId, buildCreatePayload())
    if (!disposed) emit('saved', response.data, operationContext, nextAction === 'assign' ? 'assign' : '')
  } catch (error) {
    if (disposed) return
    requestError.value = assetErrorState(error, isEdit.value ? '资产修改失败' : '资产创建失败')
    if (requestError.value.status === 409 && requestError.value.errorKey === 'SG_ASSET_DESCRIPTION_LOCKED') {
      descriptionLockedByConflict.value = true
      form.description = originalDescription || ''
    }
  } finally {
    if (!disposed) saving.value = false
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
  <ProjectModal :title="isEdit ? `编辑资产 · ${asset.assetName}` : '新建资产'" :description="isEdit ? '' : '先填写资产名称和要制作的内容，创建后可直接分配制作人。'" :busy="saving" wide @close="closeDialog">
    <el-form ref="assetForm" :model="form" :rules="assetFormRules" class="asset-form" label-position="top" :disabled="saving" aria-label="资产信息表单">
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false"><span>{{ requestError.message }}</span><el-button v-if="requestError.status === 409" link type="danger" @click="emit('refresh')">刷新后重试</el-button></el-alert>
      <section class="asset-form__grid">
        <el-form-item label="资产名称" prop="assetName"><el-input v-model="form.assetName" maxlength="200" show-word-limit :disabled="saving" placeholder="例如：女主角、街道、飞船" /></el-form-item>
        <el-form-item label="资产分类" prop="assetType"><el-select v-model="form.assetType" :disabled="isEdit || saving"><el-option label="角色" value="Character" /><el-option label="场景" value="Environment" /><el-option label="道具" value="Prop" /></el-select></el-form-item>
        <el-form-item class="asset-form__wide" label="制作要求（选填）" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" :readonly="descriptionLocked" :disabled="saving" placeholder="描述这份资产的整体效果或共用要求" />
          <p v-if="descriptionLocked" class="asset-form__lock-hint">{{ descriptionLockHint }}</p>
        </el-form-item>
      </section>
      <section v-if="!isEdit" class="asset-items-editor">
        <header><div><strong>需要制作什么</strong><p>每项可以分别分配制作人、提交成果和记录反馈。</p></div><el-button :icon="Plus" :disabled="saving || form.items.length >= 200" @click="addItem()">添加分项</el-button></header>
        <div class="asset-item-presets" aria-label="常用制作分项"><span>快速添加</span><el-button v-for="name in itemPresets" :key="name" size="small" :disabled="saving || hasItem(name) || form.items.length >= 200" @click="addItem(name)">{{ name }}</el-button></div>
        <section v-for="(item,index) in form.items" :key="item.localKey" class="asset-item-editor">
          <div class="asset-item-main">
            <el-form-item label="制作分项" :prop="`items.${index}.productionItem`" :rules="item.formRules.productionItem"><el-input v-model="item.productionItem" maxlength="240" placeholder="例如：基础设定、正面、不同服装" /></el-form-item>
            <el-form-item label="补充要求（选填）" :prop="`items.${index}.description`"><el-input v-model="item.description" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="只对这一项的要求" /></el-form-item>
            <el-button link type="danger" :disabled="saving || form.items.length <= 1" :aria-label="`移除分项 ${index + 1}`" @click="removeItem(index)">移除</el-button>
          </div>
          <el-collapse class="asset-item-more"><el-collapse-item title="排序与备注" :name="item.localKey"><div class="asset-items-editor__grid">
            <el-form-item label="排序" :prop="`items.${index}.sortOrder`" :rules="item.formRules.sortOrder"><el-input-number v-model="item.sortOrder" :min="0" :step="1" step-strictly controls-position="right" /></el-form-item>
            <el-form-item label="备注" :prop="`items.${index}.remark`"><el-input v-model="item.remark" maxlength="500" /></el-form-item>
          </div></el-collapse-item></el-collapse>
        </section>
      </section>
      <el-form-item v-if="!isEdit && canLink" label="关联资产（选填）" prop="relatedAssetIds"><AssetRelationSelect v-model="form.relatedAssetIds" :project-id="projectId" :disabled="saving" /></el-form-item>
      <el-collapse v-model="moreSettings"><el-collapse-item title="更多信息" name="more"><div class="asset-form__grid">
        <el-form-item label="项目内排序" prop="sortOrder"><el-input-number v-model="form.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="saving" /></el-form-item>
        <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" :disabled="saving" placeholder="内部备注，可留空" /></el-form-item>
      </div></el-collapse-item></el-collapse>
      <footer><el-button :disabled="saving" @click="closeDialog">取消</el-button><el-button :type="!isEdit && canAssign ? 'default' : 'primary'" :loading="saving" @click="submit()">{{ isEdit ? '保存资产' : '创建资产' }}</el-button><el-tooltip v-if="!isEdit && canAssign" content="单次分配最多 100 个分项，更多分项请先创建后分批分配" :disabled="form.items.length <= 100"><span><el-button type="primary" :disabled="saving || form.items.length > 100" :loading="saving" @click="submit('assign')">创建并分配制作人</el-button></span></el-tooltip></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.asset-form{display:grid;gap:16px}.asset-form__grid,.asset-items-editor__grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:14px}.asset-form__wide{grid-column:1/-1}
.asset-form :deep(.el-form-item){min-width:0;margin-bottom:0}.asset-form :deep(.el-select),.asset-form :deep(.el-input-number){width:100%}
.asset-form__lock-hint{margin:6px 0 0;color:var(--sg-text-muted);font-size:12px}
.asset-items-editor{display:grid;gap:10px}.asset-items-editor header,footer{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.asset-items-editor header p{margin:4px 0 0;color:var(--sg-text-muted);font-size:12px}
.asset-item-presets{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.asset-item-presets>span{font-size:12px;color:var(--sg-text-muted)}.asset-item-presets .el-button{margin:0}
.asset-item-editor{padding:12px;border:1px solid var(--sg-border);border-radius:8px}.asset-item-main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.6fr) auto;align-items:end;gap:12px}
.asset-item-more{margin-top:6px}.asset-item-more :deep(.el-collapse-item__header){height:32px;font-size:12px;color:var(--sg-text-muted)}
.asset-form :deep(.el-collapse-item__content){padding:8px 0}.asset-form :deep(.el-form-item__error){position:static;line-height:1.5}
footer{justify-content:flex-end}@media(max-width:640px){.asset-form__grid,.asset-items-editor__grid,.asset-item-main{grid-template-columns:minmax(0,1fr)}.asset-item-main>.el-button{justify-self:end}}
</style>
