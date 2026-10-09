<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElCheckbox, ElCheckboxGroup, ElMessage, ElMessageBox } from 'element-plus'
import { adjustAssetProduction, getAssetDetail } from '@/api/shot-grid/assets'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ProjectDrawer from '@/views/project/components/ProjectDrawer.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close'])
const context = props.context
const single = context.targets.length === 1
const moreSettings = ref([])
const rows = ref([])
const loading = ref(true)
const saving = ref(false)
const validating = ref(false)
const error = ref('')
const step = ref(0)
const formRef = ref(null)
const form = reactive({ keys: [], mode: 'common', common: {}, individual: {}, reason: '', referenceDescription: '' })
const fields = [
  { key: 'requirements', label: '任务制作要求', max: 10000, permission: 'shotgrid:task:edit' },
  { key: 'priority', label: '优先级', permission: 'shotgrid:task:edit' },
  { key: 'description', label: '分项补充要求', permission: 'shotgrid:asset:edit' },
  { key: 'remark', label: '分项备注', max: 500, permission: 'shotgrid:asset:edit' },
  { key: 'references', label: '追加参考说明与附件', permission: 'shotgrid:asset:edit' }
].filter(field => context.permissions.includes('*:*:*') || context.permissions.includes(field.permission))
const disabled = computed(() => loading.value || saving.value || Boolean(error.value))
let disposed = false
const controller = new AbortController()
const current = () => !disposed && context.validateContext()
onBeforeUnmount(() => { disposed = true; controller.abort() })
const { referenceAttachments, addReferenceFile, removeReferenceFile, uploadPendingReferenceFiles } = useReviewReferenceAttachments({ canEdit: () => !disabled.value, isCurrent: current })
const rules = {
  keys: [{ type: 'array', min: 1, required: true, message: '请至少选择一项修改内容' }],
  reason: [{ max: 500, message: '调整原因最多 500 字' }],
  referenceDescription: [{ validator: (_rule, _value, done) => {
    if (!form.keys.includes('references')) return done()
    if (!form.referenceDescription.trim() && !referenceAttachments.value.length) return done(new Error('请填写参考说明或添加附件'))
    if (rows.value.some(row => [row.referenceDescription, form.referenceDescription.trim()].filter(Boolean).join('\n\n').length > 10000)) return done(new Error('追加后参考说明超过 10000 字'))
    if (rows.value.some(row => row.referenceFiles.length + referenceAttachments.value.length > 5)) return done(new Error('追加后参考附件超过 5 个'))
    done()
  } }]
}
const valuesFor = row => form.mode === 'common' ? form.common : form.individual[row.assetItemId]
const labelFor = key => fields.find(field => field.key === key)?.label
onMounted(async () => {
  try {
    for (const target of context.targets) {
      const { data: asset } = await getAssetDetail(context.projectId, target.assetId, { signal: controller.signal })
      if (!current()) return
      const item = asset.items.find(item => item.assetItemId === target.assetItemId)
      if (!item || !item.allowedActions?.includes('task.adjust') || item.task?.taskId !== target.task.taskId || item.task.lockVersion !== target.task.lockVersion || item.lockVersion !== target.lockVersion || asset.lockVersion !== target.asset.lockVersion) throw new Error('分项或任务已变化，请关闭刷新后重新选择')
      const { data: task } = await getTaskDetail(item.task.taskId, { signal: controller.signal })
      if (!current()) return
      if (task.lockVersion !== item.task.lockVersion) throw new Error('任务版本已变化，请关闭刷新')
      const before = { requirements: task.requirements || '', priority: task.priority, description: item.description || '', remark: item.remark || '' }
      rows.value.push({ ...target, before, referenceDescription: task.referenceDescription || '', referenceFiles: task.referenceFiles || [] })
      form.individual[target.assetItemId] = { ...before }
    }
    form.common = { ...rows.value[0]?.before }
  } catch (failure) { if (!disposed) error.value = failure?.message || '制作信息加载失败' }
  finally { if (!disposed) loading.value = false }
})
function singleKeys() {
  if (!rows.value.length) return []
  return fields.filter(field => field.key === 'references'
    ? form.referenceDescription.trim() || referenceAttachments.value.length
    : String(form.common[field.key] ?? '').trim() !== String(rows.value[0].before[field.key] ?? '').trim()).map(field => field.key)
}
async function saveSingle() {
  if (disabled.value || validating.value) return
  validating.value = true
  try {
    form.keys = singleKeys()
    if (!form.keys.length) { ElMessage.info('尚未修改内容'); return }
    if (!await formRef.value?.validate().catch(() => false)) return
    const clearing = form.keys.filter(key => key !== 'references' && rows.value[0].before[key] && !String(form.common[key] ?? '').trim())
    if (clearing.length && !await ElMessageBox.confirm(`将清空：${clearing.map(labelFor).join('、')}。是否保存？`, '确认清空内容', { type: 'warning' }).then(() => true).catch(() => false)) return
    if (current()) await save()
  } finally { validating.value = false }
}
async function confirmClose() {
  if (saving.value) return false
  return !(single ? singleKeys().length : form.keys.length) || await ElMessageBox.confirm('关闭后将放弃尚未保存的修改。', '放弃修改？', { type: 'warning' }).then(() => true).catch(() => false)
}
async function close() {
  if (await confirmClose()) emit('close')
}
async function next() {
  if (disabled.value || !await formRef.value?.validate().catch(() => false)) return
  step.value = 1
}
async function save() {
  if (disabled.value || (!single && step.value !== 1) || !current()) return
  saving.value = true
  let sent = false
  try {
    const ids = form.keys.includes('references') ? await uploadPendingReferenceFiles() : []
    if (!current()) return
    const items = rows.value.map(row => {
      const values = valuesFor(row)
      const changes = Object.fromEntries(form.keys.filter(key => key !== 'references').map(key => [key, String(values[key] ?? '').trim() || null]))
      if (form.keys.includes('references')) {
        if (form.referenceDescription.trim()) changes.referenceDescription = form.referenceDescription.trim()
        if (ids.length) changes.referenceFileIds = ids
      }
      return { assetId: row.assetId, assetItemId: row.assetItemId, taskId: row.task.taskId, lockVersion: row.task.lockVersion, assetLockVersion: row.asset.lockVersion, assetItemLockVersion: row.lockVersion, changes }
    })
    sent = true
    await adjustAssetProduction(context.projectId, { reason: form.reason.trim(), items })
    if (!current()) return
    ElMessage.success(`已保存 ${rows.value.length} 个分项的调整，制作状态不变`)
    emit('close', { saved: true })
  } catch (failure) {
    if (!current()) return
    if (!sent) { ElMessage.error(failure?.message || '附件上传失败，尚未保存'); return }
    const status = Number(failure?.httpStatus || failure?.status)
    error.value = [401, 403, 404, 409, 422].includes(status) ? `${failure?.message || '保存失败'}；本批未保存，请关闭并刷新核对` : '保存结果未知，请关闭刷新核对，勿重复发送'
  } finally { if (!disposed) saving.value = false }
}
</script>

<template>
  <ProjectDrawer :title="single ? '制作要求与参考资料' : '批量制作要求与参考资料'" :description="single ? context.targets[0].displayLabel : `已选 ${context.targets.length} 个分项`" wide :busy="saving" :close-guard="confirmClose" @close="emit('close')">
    <el-skeleton v-if="loading" :rows="5" animated />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form v-if="!loading && !error" ref="formRef" :model="form" :rules="rules" :disabled="disabled" label-position="top" class="asset-adjust-form">
      <template v-if="single">
        <el-form-item v-if="fields.some(field => field.key === 'requirements')" label="制作要求" prop="common.requirements" :rules="[{ max: 10000, message: '最多 10000 字' }]"><el-input v-model="form.common.requirements" type="textarea" :rows="5" maxlength="10000" show-word-limit /></el-form-item>
        <template v-if="fields.some(field => field.key === 'references')">
          <el-text tag="strong">参考资料</el-text>
          <p v-if="rows[0]?.referenceDescription">{{ rows[0].referenceDescription }}</p>
          <ReviewReferenceInput v-if="rows[0]?.referenceFiles.length" :files="rows[0].referenceFiles" readonly purpose="制作参考" />
          <el-form-item label="补充参考说明与附件（追加保留已有资料）" prop="referenceDescription"><div class="asset-adjust-references"><el-input v-model="form.referenceDescription" type="textarea" :rows="2" maxlength="10000" placeholder="填写新增参考说明" /><ReviewReferenceInput :files="referenceAttachments" purpose="制作参考" :disabled="disabled" @add="addReferenceFile" @remove="removeReferenceFile" /></div></el-form-item>
        </template>
        <el-collapse v-model="moreSettings"><el-collapse-item title="更多信息" name="more">
          <el-alert title="分项补充要求和备注与“编辑分项信息”共用同一份内容，修改后会同步显示。" type="info" :closable="false" />
          <el-form-item v-for="field in fields.filter(field => ['priority', 'description', 'remark'].includes(field.key))" :key="field.key" :label="field.label" :prop="`common.${field.key}`" :rules="field.max ? [{ max: field.max, message: `最多 ${field.max} 字` }] : []">
            <el-select v-if="field.key === 'priority'" v-model="form.common.priority"><el-option v-for="(label, value) in { low: '低', normal: '普通', high: '高', urgent: '紧急' }" :key="value" :value="value" :label="label" /></el-select>
            <el-input v-else v-model="form.common[field.key]" type="textarea" :rows="3" :maxlength="field.max" show-word-limit />
          </el-form-item>
          <el-form-item label="调整原因（选填）" prop="reason"><el-input v-model="form.reason" maxlength="500" /></el-form-item>
        </el-collapse-item></el-collapse>
      </template>
      <template v-else-if="step === 0">
        <el-alert title="只修改勾选的字段。参考资料为追加，已有资料会保留；保存不会自动开工或提交版本。" type="info" :closable="false" />
        <el-form-item label="要修改的内容" prop="keys"><ElCheckboxGroup v-model="form.keys"><ElCheckbox v-for="field in fields" :key="field.key" :value="field.key">{{ field.label }}</ElCheckbox></ElCheckboxGroup></el-form-item>
        <el-form-item v-if="rows.length > 1" label="填写方式" prop="mode"><el-radio-group v-model="form.mode"><el-radio-button value="common">统一填写</el-radio-button><el-radio-button value="individual">逐分项填写</el-radio-button></el-radio-group></el-form-item>
        <el-card v-for="row in form.mode === 'common' ? rows.slice(0, 1) : rows" :key="row.assetItemId" shadow="never">
          <template #header>{{ form.mode === 'common' ? '应用于全部所选分项' : row.displayLabel }}</template>
          <template v-for="field in fields.filter(field => field.key !== 'references' && form.keys.includes(field.key))" :key="field.key">
            <el-form-item :label="field.label" :prop="form.mode === 'common' ? `common.${field.key}` : `individual.${row.assetItemId}.${field.key}`" :rules="field.max ? [{ max: field.max, message: `最多 ${field.max} 字` }] : []">
              <el-select v-if="field.key === 'priority'" v-model="valuesFor(row)[field.key]"><el-option v-for="(label, value) in { low: '低', normal: '普通', high: '高', urgent: '紧急' }" :key="value" :value="value" :label="label" /></el-select>
              <el-input v-else v-model="valuesFor(row)[field.key]" type="textarea" :rows="3" :maxlength="field.max" show-word-limit />
            </el-form-item>
          </template>
        </el-card>
        <el-form-item v-if="form.keys.includes('references')" label="追加参考说明与附件" prop="referenceDescription"><div class="asset-adjust-references"><el-input v-model="form.referenceDescription" type="textarea" :rows="3" maxlength="10000" placeholder="补充本次制作参考" /><ReviewReferenceInput :files="referenceAttachments" purpose="制作参考" :disabled="disabled" @add="addReferenceFile" @remove="removeReferenceFile" /></div></el-form-item>
        <el-form-item label="调整原因（选填）" prop="reason"><el-input v-model="form.reason" maxlength="500" /></el-form-item>
      </template>
      <template v-else>
        <el-alert title="本批统一保存，任一分项版本或权限校验失败，整批不会保存。请核对后确认。" type="info" :closable="false" />
        <el-card v-for="row in rows" :key="row.assetItemId" shadow="never"><template #header>{{ row.displayLabel }}</template><el-descriptions :column="1" border><el-descriptions-item v-for="key in form.keys.filter(key => key !== 'references')" :key="key" :label="labelFor(key)"><p class="asset-adjust-before">原：{{ row.before[key] || '未填写' }}</p><p>新：{{ valuesFor(row)[key] || '清空' }}</p></el-descriptions-item></el-descriptions></el-card>
        <el-alert v-if="form.keys.includes('references')" :title="`全部分项追加：${form.referenceDescription || '参考附件'}；${referenceAttachments.length} 个附件`" type="info" :closable="false" />
      </template>
    </el-form>
    <template #footer><el-button :disabled="saving" @click="close">取消</el-button><el-button v-if="!single && step === 1 && !error" :disabled="saving" @click="step = 0">返回编辑</el-button><el-button v-if="single" type="primary" :disabled="disabled" :loading="saving" @click="saveSingle">保存修改</el-button><el-button v-else-if="!step" type="primary" :disabled="disabled" @click="next">下一步：核对</el-button><el-button v-else type="primary" :disabled="disabled" :loading="saving" @click="save">确认保存</el-button></template>
  </ProjectDrawer>
</template>
<style scoped>
.asset-adjust-form,.asset-adjust-references{display:grid;gap:16px;width:100%}.asset-adjust-before{color:var(--sg-text-muted)}p{white-space:pre-wrap;overflow-wrap:anywhere}.asset-adjust-form :deep(.el-form-item){margin-bottom:12px}
</style>
