<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElCheckboxGroup, ElMessage, ElRadio } from 'element-plus'
import 'element-plus/es/components/checkbox-group/style/css'
import 'element-plus/es/components/radio/style/css'
import { getShotDetail } from '@/api/shot-grid/shots'
import { adjustShotProduction } from '@/api/shot-grid/tasks'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import ProductionAdjustmentField from './ProductionAdjustmentField.vue'
import { adjustmentFields, adjustmentPatch, adjustmentValues } from './productionAdjustment'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close'])
const context = props.context
const copyValues = value => JSON.parse(JSON.stringify(value))
const loading = ref(true)
const saving = ref(false)
const navigating = ref(false)
const error = ref('')
const step = ref(0)
const formRef = ref(null)
const rows = ref([])
const conflicts = ref([])
const form = reactive({ keys: [], mode: 'common', common: {}, individual: {}, reason: '', referenceDescription: '', referenceFileIds: [], acknowledged: false })
const editableFields = adjustmentFields.filter(field => context.permissions.includes('*:*:*') || context.permissions.includes(field.permission))
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({ canEdit: () => !disabled.value, isCurrent: () => current() })
const selectedFields = computed(() => editableFields.filter(field => form.keys.includes(field.key)))
const valueFields = computed(() => selectedFields.value.filter(field => field.type !== 'references'))
const disabled = computed(() => loading.value || saving.value || navigating.value || Boolean(error.value))
const groups = computed(() => form.mode === 'common' ? [{ key: 'common', label: '统一设置（应用于全部所选镜头）', values: form.common, path: ['common'] }]
  : rows.value.map(row => ({ key: row.shotId, label: row.label, values: form.individual[row.shotId], path: ['individual', String(row.shotId)] })))
const rules = {
  referenceFileIds: [{ validator: (_rule, _value, done) => {
    if (!referenceAttachments.value.length && !form.referenceDescription.trim()) return done(new Error('请填写参考说明或添加参考资料，或返回取消勾选参考内容'))
    if (rows.value.some(row => [row.before.referenceDescription, form.referenceDescription.trim()].filter(Boolean).join('\n\n').length > 10000)) return done(new Error('追加后有任务的参考说明超过 10000 字，请缩短说明'))
    if (rows.value.some(row => row.before.referenceFileIds.length + referenceAttachments.value.length > 5)) return done(new Error('追加后有任务超过 5 个参考文件，请减少上传数量'))
    done()
  } }],
  keys: [{ type: 'array', required: true, min: 1, message: '请至少选择一个要修改的字段' }],
  reason: [{ required: true, whitespace: true, message: '请填写调整原因', trigger: 'blur' }, { max: 500, message: '调整原因不能超过 500 字' }]
}
const controller = new AbortController()
let disposed = false
onBeforeUnmount(() => { disposed = true; controller.abort() })
const current = () => !disposed && context.validateContext()
const fieldRuleCache = new Map()
function fieldRules(field) {
  if (fieldRuleCache.has(field.key)) return fieldRuleCache.get(field.key)
  const rules = [{ validator: (_rule, value, done) => {
    let message = ''
    if (field.type === 'range' && (!Array.isArray(value) || value.length !== 2 || value.some(item => !item || !Number.isFinite(new Date(item).getTime())) || new Date(value[1]) <= new Date(value[0]))) message = '请选择完整且结束晚于开始的计划时间'
    if (field.type === 'member' && !context.members.some(member => member.userId === value)) message = '请选择有效制作人'
    if (field.type === 'priority' && !['low', 'normal', 'high', 'urgent'].includes(value)) message = '请选择优先级'
    if (field.type === 'number' && (!Number.isSafeInteger(value) || value < 0)) message = '时长必须为非负整数毫秒'
    if (field.max && String(value || '').length > field.max) message = `最多 ${field.max} 字`
    done(message ? new Error(message) : undefined)
  }, trigger: 'change' }]
  fieldRuleCache.set(field.key, rules)
  return rules
}
onMounted(async () => {
  try {
    for (const shot of context.shots) {
      const { data } = await getShotDetail(context.projectId, shot.shotId, { signal: controller.signal })
      if (!current()) return
      if (!data?.allowedActions?.includes('task.adjust') || data.task?.taskId !== shot.taskId || data.task.lockVersion !== shot.taskLockVersion || data.lockVersion !== shot.lockVersion) throw new Error('任务或制作信息已变化，请关闭并刷新后重新选择')
      const { data: taskDetail } = await getTaskDetail(shot.taskId, { signal: controller.signal })
      if (!current()) return
      if (taskDetail.lockVersion !== shot.taskLockVersion) throw new Error('任务已变化，请关闭并刷新')
      const values = adjustmentValues(data)
      values.referenceDescription = taskDetail.referenceDescription || ''
      values.referenceFileIds = taskDetail.referenceFiles || []
      const row = { ...shot, label: [shot.episodeCode, shot.sceneCode, shot.shotCode].filter(Boolean).join(' / '), before: values }
      rows.value.push(row)
      form.individual[shot.shotId] = copyValues(values)
    }
    if (rows.value.length) form.common = copyValues(rows.value[0].before)
  } catch (failure) { if (!disposed) error.value = failure?.message || '加载失败，请重新打开' }
  finally { if (!disposed) loading.value = false }
})
function reset() {
  if (disabled.value) return
  formRef.value?.resetFields()
  resetReferenceAttachments()
  form.keys = []; form.reason = ''; form.referenceDescription = ''; form.mode = 'common'
  form.common = copyValues({ ...rows.value[0].before, expectedRange: [...rows.value[0].before.expectedRange] })
  for (const row of rows.value) form.individual[row.shotId] = { ...row.before, expectedRange: [...row.before.expectedRange] }
  conflicts.value = []; form.acknowledged = false
  formRef.value?.clearValidate()
  step.value = 0
}
async function advance() {
  if (disabled.value) return
  navigating.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    step.value += 1
    conflicts.value = []; form.acknowledged = false
    await nextTick(); formRef.value?.clearValidate()
  } finally { navigating.value = false }
}
function previous() { if (!disabled.value) { step.value -= 1; conflicts.value = []; form.acknowledged = false } }
function valuesFor(row) { return form.mode === 'common' ? form.common : form.individual[row.shotId] }
function display(field, value) {
  if (field.type === 'references') return value?.map(file => file.originalName).join('、') || '无'
  if (field.type === 'range') return value?.length === 2 ? value.join(' 至 ').replaceAll('T', ' ') : '未设置'
  if (field.type === 'member') return context.members.find(member => member.userId === value)?.userName || String(value)
  if (field.type === 'priority') return { low: '低', normal: '普通', high: '高', urgent: '紧急' }[value]
  return String(value ?? '').trim() || '（清空）'
}
const preview = computed(() => rows.value.flatMap(row => selectedFields.value.map((field, index) => ({
  key: `${row.shotId}-${field.key}`, label: row.label, field: field.label,
  shotRowSpan: index === 0 ? selectedFields.value.length : 0,
  before: (field.type === 'references' ? row.before.referenceDescription + '\n' : '') + display(field, row.before[field.key]), after: (field.type === 'references' ? [row.before.referenceDescription, form.referenceDescription.trim()].filter(Boolean).join('\n\n') + '\n' : '') + display(field, field.type === 'references' ? [...row.before.referenceFileIds, ...referenceAttachments.value] : valuesFor(row)[field.key])
}))))
function previewSpan({ row, columnIndex }) {
  if (columnIndex === 0) return [row.shotRowSpan, row.shotRowSpan ? 1 : 0]
  return [1, 1]
}
async function submit() {
  if (disabled.value || step.value !== 2) return
  if (!current()) { error.value = '项目或任务已变化，请关闭并刷新'; return }
  if (conflicts.value.length && !form.acknowledged) { ElMessage.warning('请核对并确认人员排期重叠'); return }
  saving.value = true
  let requestSent = false
  try {
    const referenceIds = form.keys.includes('referenceFileIds') ? await uploadPendingReferenceFiles() : null
    if (!current()) return
    requestSent = true
    await adjustShotProduction(context.projectId, {
      reason: form.reason.trim(), overlapAcknowledged: form.acknowledged, expectedConflicts: conflicts.value,
      items: rows.value.map(row => ({ shotId: row.shotId, taskId: row.taskId, lockVersion: row.taskLockVersion, shotLockVersion: row.lockVersion, changes: { ...adjustmentPatch(form.keys.filter(key => key !== 'referenceFileIds'), valuesFor(row)), ...(referenceIds?.length ? { referenceFileIds: referenceIds } : {}), ...(form.keys.includes('referenceFileIds') && form.referenceDescription.trim() ? { referenceDescription: form.referenceDescription.trim() } : {}) } }))
    })
    if (!current()) return
    ElMessage.success(`已调整 ${rows.value.length} 个制作任务`)
    emit('close', { saved: true })
  } catch (failure) {
    if (!current()) return
    if (!requestSent) { ElMessage.error(failure?.message || '参考文件上传失败，请重试'); return }
    if (failure?.errorKey === 'SG_ADJUST_OVERLAP' && Array.isArray(failure?.details?.conflicts)) {
      conflicts.value = failure.details.conflicts; form.acknowledged = false
      if (!conflicts.value.length) ElMessage.warning('原排期冲突已消失，请再次确认保存')
    } else {
      const status = Number(failure?.httpStatus || failure?.status)
      if ([400, 422].includes(status)) ElMessage.error(failure?.message || '请检查修改内容')
      else error.value = [401, 403, 404, 409].includes(status) ? (failure?.message || '任务已变化') + '；本批未保存，请关闭并刷新后核对' : '提交结果未知，请关闭并刷新核对，勿重复保存'
    }
  } finally { if (!disposed) saving.value = false }
}
</script>
<template>
  <ProjectModal :title="context.shots.length > 1 ? '批量调整制作任务' : '调整制作任务'" :description="`已选 ${context.shots.length} 个制作中镜头 · 保存后仍保持制作中`" wide :busy="saving" @close="emit('close')">
    <el-steps :active="step" finish-status="success" simple><el-step title="选择字段" /><el-step title="填写新值" /><el-step title="核对保存" /></el-steps>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="adjust-gap" />
    <el-form v-if="!loading && !error" ref="formRef" :model="form" :rules="rules" :disabled="disabled" label-position="top" class="adjust-form">
      <template v-if="step === 0">
        <el-alert title="只修改勾选字段，其余内容保持原值。镜头编号、存储目录与实际开工时间保持固定。" type="info" :closable="false" />
        <el-form-item label="需要调整的内容" prop="keys" class="adjust-field-selection">
          <el-checkbox-group v-model="form.keys" class="adjust-field-options">
            <el-checkbox v-for="field in editableFields" :key="field.key" :value="field.key" border>{{ field.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </template>
      <template v-else-if="step === 1">
        <el-form-item v-if="rows.length > 1 && valueFields.length" label="填写方式" prop="mode"><el-radio-group v-model="form.mode"><el-radio value="common">统一填写</el-radio><el-radio value="individual">逐镜头填写</el-radio></el-radio-group></el-form-item>
        <el-alert v-if="valueFields.length" title="勾选的文字字段留空表示清空；未勾选的字段不会修改。统一填写初始展示第一个镜头的值，请核对后保存。" type="warning" :closable="false" />
        <section v-for="group in valueFields.length ? groups : []" :key="group.key" class="adjust-group"><h3>{{ group.label }}</h3>
          <el-form-item v-for="field in valueFields" :key="field.key" :label="field.label" :prop="group.path.join('.') + '.' + field.key" :rules="fieldRules(field)"><ProductionAdjustmentField v-model="group.values[field.key]" :field="field" :members="context.members" /></el-form-item>
        </section>
        <el-form-item v-if="form.keys.includes('referenceFileIds')" label="参考内容（可选）" prop="referenceFileIds">
          <div class="adjust-references">
            <el-alert :title="`本次内容将追加到 ${rows.length} 个任务，保留已有说明和附件。`" type="info" :closable="false" />
            <section class="adjust-references__section" aria-label="各镜头附件数量">
              <div class="adjust-references__heading"><span>应用范围</span><span class="adjust-references__hint">每个任务最多 5 个附件</span></div>
              <el-table :data="rows" row-key="shotId" size="small" :max-height="200">
                <el-table-column prop="label" label="镜头" min-width="180" />
                <el-table-column label="已有附件" width="90" align="center"><template #default="{ row }">{{ row.before.referenceFileIds.length }} 个</template></el-table-column>
                <el-table-column label="追加后" width="110" align="center"><template #default="{ row }"><el-tag :type="row.before.referenceFileIds.length + referenceAttachments.length > 5 ? 'danger' : 'info'" size="small" effect="plain">{{ row.before.referenceFileIds.length + referenceAttachments.length }} / 5</el-tag></template></el-table-column>
              </el-table>
            </section>
            <section class="adjust-references__section" aria-label="填写参考说明">
              <div class="adjust-references__heading"><span>参考说明</span><span class="adjust-references__hint">可只填说明或只上传附件</span></div>
              <el-input v-model="form.referenceDescription" type="textarea" :rows="3" maxlength="10000" show-word-limit aria-label="参考说明" placeholder="例如：参考画面的暖色光线，重点关注人物转身时的动作节奏" />
              <p class="adjust-references__hint">追加后，每个任务的参考说明累计不超过 10000 字。</p>
            </section>
            <section class="adjust-references__section" aria-label="添加参考附件">
              <div class="adjust-references__heading"><span>参考附件</span><span class="adjust-references__hint">本次新增 {{ referenceAttachments.length }} 个</span></div>
              <ReviewReferenceInput :files="referenceAttachments" :disabled="disabled" purpose="调整" @add="addReferenceFile" @remove="removeReferenceFile" />
            </section>
          </div>
        </el-form-item>
        <el-form-item label="调整原因" prop="reason"><el-input v-model="form.reason" type="textarea" maxlength="500" show-word-limit placeholder="说明与制作人沟通后的调整原因" /></el-form-item>
      </template>
      <template v-else>
        <el-alert title="全部成功才保存；任一任务发生冲突，本批全部不保存。" type="info" :closable="false" />
        <p>调整原因：{{ form.reason }}</p>
        <el-table :data="preview" :span-method="previewSpan" row-key="key" max-height="420"><el-table-column prop="label" label="镜头" width="160" /><el-table-column prop="field" label="修改字段" width="110" /><el-table-column prop="before" label="原值" /><el-table-column prop="after" label="新值" /></el-table>
        <template v-if="conflicts.length"><el-alert title="调整后存在人员排期重叠，请核对以下任务" type="warning" :closable="false" class="adjust-gap" /><p v-for="conflict in conflicts" :key="conflict.taskId">{{ rows.find(row => row.taskId === conflict.taskId)?.label }} 与任务 {{ conflict.conflictTaskIds.join('、') }} 时间重叠</p><el-form-item prop="acknowledged"><el-checkbox v-model="form.acknowledged">已核对，仍按此安排保存</el-checkbox></el-form-item></template>
      </template>
    </el-form>
    <p v-if="loading">正在核对制作任务…</p>
    <footer class="adjust-actions"><el-button :disabled="saving" @click="emit('close')">关闭</el-button><template v-if="!loading && !error"><el-button :disabled="disabled" @click="reset">重置</el-button><el-button v-if="step > 0" :disabled="disabled" @click="previous">上一步</el-button><el-button v-if="step < 2" type="primary" :disabled="disabled" @click="advance">{{ step === 0 ? '下一步：填写新值' : '下一步：核对修改' }}</el-button><el-button v-else type="primary" :disabled="disabled || (conflicts.length > 0 && !form.acknowledged)" :loading="saving" @click="submit">确认保存（{{ rows.length }}）</el-button></template></footer>
  </ProjectModal>
</template>
<style scoped>
.adjust-field-selection{margin-top:18px}
.adjust-field-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;width:100%;min-width:0}
.adjust-field-options :deep(.el-checkbox){width:100%;height:auto;min-height:42px;margin:0;padding:10px 12px;border-radius:6px}
.adjust-field-options :deep(.el-checkbox__label){white-space:normal;line-height:1.5;overflow-wrap:anywhere}
@media(max-width:640px){.adjust-field-options{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
@media(max-width:420px){.adjust-field-options{grid-template-columns:minmax(0,1fr)}}
.adjust-form{margin-top:18px}.adjust-group{margin:16px 0;padding:12px;border:1px solid var(--sg-border);border-radius:8px}.adjust-group h3{margin:0 0 14px;font-size:15px}.adjust-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px;flex-wrap:wrap}.adjust-gap{margin-top:14px}.adjust-form :deep(.el-table .cell){white-space:pre-wrap;overflow-wrap:anywhere}
.adjust-references{display:flex;flex-direction:column;gap:16px;width:100%;min-width:0;padding-bottom:4px}
.adjust-references__section{width:100%;min-width:0}
.adjust-references__heading{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px;font-weight:500;line-height:1.6}
.adjust-references__hint{color:var(--sg-text-muted);font-size:12px;font-weight:400;line-height:1.6}
p.adjust-references__hint{margin:6px 0 0}
.adjust-form :deep(.el-form-item__error){position:static;width:100%;line-height:1.5;padding-top:6px}
</style>
