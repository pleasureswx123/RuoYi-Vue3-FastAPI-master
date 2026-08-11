<script setup>
import { computed, reactive, ref } from 'vue'
import { Plus, WarningFilled } from '@element-plus/icons-vue'

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
const saving = ref(false)
const validationMessage = ref('')
const requestError = ref(null)

function newItem() {
  return {
    localKey: nextItemKey++,
    productionItem: '',
    description: '',
    sortOrder: 0,
    assigneeUserId: '',
    taskDescription: '',
    remark: ''
  }
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

function addItem() {
  form.items.push(newItem())
}

function removeItem(index) {
  if (form.items.length <= 1) return
  form.items.splice(index, 1)
}

function validate() {
  if (!isEdit.value && !form.assetName.trim()) return '资产名称不能为空'
  if (!Number.isInteger(Number(form.sortOrder)) || Number(form.sortOrder) < 0) return '排序必须是非负整数'
  if (!isEdit.value) {
    if (!form.items.length) return '至少需要一个制作分项'
    const names = form.items.map(item => item.productionItem.trim().toLocaleLowerCase()).filter(Boolean)
    if (new Set(names).size !== names.length) return '同一资产内制作分项名称不能重复'
    if (form.items.some(item => !Number.isInteger(Number(item.sortOrder)) || Number(item.sortOrder) < 0)) return '制作分项排序必须是非负整数'
  }
  return ''
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
  validationMessage.value = validate()
  requestError.value = null
  if (validationMessage.value) return
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
</script>

<template>
  <ProjectModal :title="isEdit ? `编辑资产 · ${asset.assetName}` : '新建资产'" :description="isEdit ? '资产类型、名称和目录身份不可普通修改；此处保存非身份主数据完整快照。' : '创建资产时至少创建一个制作分项；制作人可稍后通过任务分配补充。'" :busy="saving" wide @close="emit('close')">
    <form class="asset-form" @submit.prevent="submit">
      <div v-if="validationMessage || requestError" class="asset-form__error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ requestError?.title || '请检查表单' }}</strong><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新后重试</button></div></div>

      <section class="asset-form__grid">
        <label><span>资产类型</span><select v-model="form.assetType" :disabled="isEdit || saving"><option value="Character">角色</option><option value="Environment">场景</option><option value="Prop">道具</option></select></label>
        <label><span>资产名称</span><input v-model="form.assetName" maxlength="200" :disabled="isEdit || saving" placeholder="例如：动力舱室内" /></label>
        <label><span>项目内排序</span><input v-model.number="form.sortOrder" type="number" min="0" step="1" :disabled="saving" /></label>
        <label class="asset-form__wide"><span>资产说明</span><textarea v-model="form.description" rows="3" :disabled="saving" placeholder="资产的稳定业务说明" /></label>
        <label class="asset-form__wide"><span>备注</span><textarea v-model="form.remark" rows="2" maxlength="500" :disabled="saving" placeholder="内部备注，可留空" /></label>
      </section>

      <section v-if="!isEdit" class="asset-items-editor">
        <header><div><strong>首批制作分项</strong><p>名称允许暂缺，但提交图片版本前必须补齐。</p></div><el-button :icon="Plus" :disabled="saving || form.items.length >= 200" @click="addItem">添加分项</el-button></header>
        <article v-for="(item,index) in form.items" :key="item.localKey">
          <div class="asset-items-editor__heading"><strong>分项 {{ index + 1 }}</strong><button type="button" :disabled="saving || form.items.length <= 1" @click="removeItem(index)">移除</button></div>
          <div class="asset-items-editor__grid">
            <label><span>制作分项</span><input v-model="item.productionItem" maxlength="240" :disabled="saving" placeholder="允许稍后补齐" /></label>
            <label><span>排序</span><input v-model.number="item.sortOrder" type="number" min="0" step="1" :disabled="saving" /></label>
            <label><span>主制作人</span><select v-model="item.assigneeUserId" :disabled="saving"><option value="">暂不分配</option><option v-for="member in members" :key="member.userId" :value="String(member.userId)">{{ memberLabel(member) }}</option></select></label>
            <label class="asset-items-editor__wide"><span>分项说明</span><textarea v-model="item.description" rows="2" :disabled="saving" /></label>
            <label class="asset-items-editor__wide"><span>首次任务要求</span><textarea v-model="item.taskDescription" rows="2" :disabled="saving || !item.assigneeUserId" /></label>
            <label class="asset-items-editor__wide"><span>备注</span><input v-model="item.remark" maxlength="500" :disabled="saving" /></label>
          </div>
        </article>
      </section>

      <footer><el-button :disabled="saving" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">{{ isEdit ? '保存资产' : '创建资产' }}</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.asset-form{display:grid;gap:18px}.asset-form__error{display:grid;grid-template-columns:auto 1fr;gap:10px;padding:14px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:10px}.asset-form__error p{margin:4px 0;font-size:12px}.asset-form__error code{font-size:10px}.asset-form__error button{display:block;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.asset-form__grid,.asset-items-editor__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.asset-form label,.asset-items-editor label{display:grid;gap:6px}.asset-form label span{color:var(--sg-text-muted);font-size:11px}.asset-form input,.asset-form select,.asset-form textarea{width:100%;box-sizing:border-box;padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.asset-form textarea{resize:vertical}.asset-form__wide,.asset-items-editor__wide{grid-column:1/-1}.asset-items-editor{display:grid;gap:12px}.asset-items-editor>header,.asset-items-editor__heading,footer{display:flex;gap:12px;align-items:center;justify-content:space-between}.asset-items-editor header p{margin:4px 0 0;color:var(--sg-text-muted);font-size:11px}.asset-items-editor article{padding:15px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:11px}.asset-items-editor__heading{margin-bottom:12px}.asset-items-editor__heading button{color:var(--sg-danger);cursor:pointer;background:transparent;border:0}.asset-items-editor__heading button:disabled{opacity:.35;cursor:not-allowed}footer{justify-content:flex-end}@media(max-width:760px){.asset-form__grid,.asset-items-editor__grid{grid-template-columns:1fr}.asset-form__wide,.asset-items-editor__wide{grid-column:auto}}
</style>
