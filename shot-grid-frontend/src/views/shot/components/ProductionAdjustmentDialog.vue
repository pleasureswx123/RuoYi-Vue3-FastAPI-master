<script setup>
import { RefreshLeft } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElCheckboxGroup, ElMessage, ElMessageBox, ElRadio } from 'element-plus'
import 'element-plus/es/components/checkbox-group/style/css'
import 'element-plus/es/components/radio/style/css'
import { getShotDetail } from '@/api/shot-grid/shots'
import { adjustShotProduction } from '@/api/shot-grid/tasks'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'
import ProjectDrawer from '@/views/project/components/ProjectDrawer.vue'
import ProductionAdjustmentField from './ProductionAdjustmentField.vue'
import ProductionAdjustmentPreview from './ProductionAdjustmentPreview.vue'
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
const form = reactive({ keys: [], mode: 'common', common: {}, individual: {}, reason: '', referenceDescription: '', referenceFileIds: [] })
const editableFields = adjustmentFields.filter(field => context.permissions.includes('*:*:*') || context.permissions.includes(field.permission))
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({ canEdit: () => !disabled.value, isCurrent: () => current() })
const fieldSections = computed(() => [
  { title: '任务安排', layout: 'schedule', keys: ['expectedRange', 'assigneeUserId', 'priority'] },
  { title: '制作内容', layout: 'content', keys: ['description', 'durationMs'] },
  { title: '镜头参数', layout: 'camera', keys: ['shotSize', 'cameraPosition', 'focalLength', 'cameraMovement'] },
  { title: '补充说明', keys: ['dialogue', 'soundEffect', 'colorReference', 'remark'] },
  { title: '参考内容', keys: ['referenceFileIds'] }
].map(section => ({ ...section, fields: section.keys.map(key => editableFields.find(field => field.key === key)).filter(Boolean) })).filter(section => section.fields.length))
async function confirmClose() {
  if (saving.value) return false
  if (!form.keys.length && !form.reason && !referenceAttachments.value.length) return true
  try {
    await ElMessageBox.confirm('本次修改尚未保存，关闭后将丢失。', '放弃未保存的修改？', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' })
    return !saving.value
  } catch { return false }
}
async function requestClose() { if (await confirmClose()) emit('close') }
const selectedFields = computed(() => editableFields.filter(field => form.keys.includes(field.key)))
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
  reason: [{ max: 500, message: '调整原因不能超过 500 字' }]
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
  formRef.value?.clearValidate()
  step.value = 0
}
async function advance() {
  if (disabled.value) return
  navigating.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    step.value = 2
      await nextTick(); formRef.value?.clearValidate()
  } finally { navigating.value = false }
}
function previous() { if (!disabled.value) { step.value = 0 } }
function valuesFor(row) { return form.mode === 'common' ? form.common : form.individual[row.shotId] }
function display(field, value) {
  if (field.type === 'references') return value?.map(file => file.originalName).join('、') || '无'
  if (field.type === 'range') return value?.length === 2 ? value.join(' 至 ').replaceAll('T', ' ') : '未设置'
  if (field.type === 'member') return context.members.find(member => member.userId === value)?.userName || String(value)
  if (field.type === 'priority') return { low: '低', normal: '普通', high: '高', urgent: '紧急' }[value]
  return String(value ?? '').trim() || '（清空）'
}
const preview = computed(() => rows.value.map(row => ({
  key: row.shotId, label: row.label,
  fields: selectedFields.value.map(field => ({
    key: field.key, label: field.label, isReference: field.type === 'references',
    beforeFiles: row.before.referenceFileIds,
    beforeDescription: row.before.referenceDescription,
    before: display(field, row.before[field.key]),
    after: display(field, valuesFor(row)[field.key]),
    changed: field.type === 'references'
      ? Boolean(referenceAttachments.value.length || form.referenceDescription.trim())
      : display(field, row.before[field.key]) !== display(field, valuesFor(row)[field.key])
  }))
})))
async function submit() {
  if (disabled.value || step.value !== 2) return
  if (!current()) { error.value = '项目或任务已变化，请关闭并刷新'; return }
  saving.value = true
  let requestSent = false
  try {
    const referenceIds = form.keys.includes('referenceFileIds') ? await uploadPendingReferenceFiles() : null
    if (!current()) return
    requestSent = true
    await adjustShotProduction(context.projectId, {
      reason: form.reason.trim(),
      items: rows.value.map(row => ({ shotId: row.shotId, taskId: row.taskId, lockVersion: row.taskLockVersion, shotLockVersion: row.lockVersion, changes: { ...adjustmentPatch(form.keys.filter(key => key !== 'referenceFileIds'), valuesFor(row)), ...(referenceIds?.length ? { referenceFileIds: referenceIds } : {}), ...(form.keys.includes('referenceFileIds') && form.referenceDescription.trim() ? { referenceDescription: form.referenceDescription.trim() } : {}) } }))
    })
    if (!current()) return
    ElMessage.success(`已调整 ${rows.value.length} 个制作任务`)
    emit('close', { saved: true })
  } catch (failure) {
    if (!current()) return
    if (!requestSent) { ElMessage.error(failure?.message || '参考文件上传失败，请重试'); return }
    const status = Number(failure?.httpStatus || failure?.status)
    if ([400, 422].includes(status)) ElMessage.error(failure?.message || '请检查修改内容')
    else error.value = [401, 403, 404, 409].includes(status) ? (failure?.message || '任务已变化') + '；本批未保存，请关闭并刷新后核对' : '提交结果未知，请关闭并刷新核对，勿重复保存'
  } finally { if (!disposed) saving.value = false }
}
</script>
<template>
  <ProjectDrawer :title="context.shots.length > 1 ? '批量编辑制作任务' : `编辑制作任务 · ${[context.shots[0]?.episodeCode, context.shots[0]?.sceneCode, context.shots[0]?.shotCode].filter(Boolean).join(' / ')}`" :description="`已选 ${context.shots.length} 个制作中镜头 · 保存后仍保持制作中`" wide :busy="saving" :close-guard="confirmClose" @close="emit('close')">
    <el-steps :active="step === 2 ? 1 : 0" finish-status="success" simple><el-step title="选择并编辑" /><el-step title="核对保存" /></el-steps>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="adjust-gap" />
    <el-form v-if="!loading && !error" ref="formRef" :model="form" :rules="rules" :disabled="disabled" label-position="top" class="adjust-form" size="default">
      <template v-if="step === 0">
        <el-alert title="勾选要修改的内容，即可在下方编辑；未勾选的内容保持原值。" type="info" :closable="false" />
        <el-form-item v-if="rows.length > 1" label="填写方式" prop="mode" class="adjust-gap"><el-radio-group v-model="form.mode"><el-radio value="common">统一填写</el-radio><el-radio value="individual">逐镜头填写</el-radio></el-radio-group></el-form-item>
        <p v-if="rows.length > 1 && form.mode === 'common'" class="adjust-references__hint">统一填写以第一个镜头为初始值，勾选字段的新值会应用于全部所选镜头。</p>
        <el-form-item prop="keys" class="adjust-selection-summary"><span>已选择 {{ form.keys.length }} 项修改内容</span></el-form-item>
        <el-checkbox-group v-model="form.keys" class="adjust-sections">
          <el-card v-for="section in fieldSections" :key="section.title" shadow="never" class="adjust-section">
            <template #header><strong>{{ section.title }}</strong></template>
            <div class="adjust-field-grid" :class="section.layout && `adjust-field-grid--${section.layout}`">
              <section v-for="field in section.fields" :key="field.key" class="adjust-edit-field" :class="{ 'is-selected': form.keys.includes(field.key), 'is-wide': field.key === 'referenceFileIds' }">
                <el-checkbox :value="field.key">{{ field.label }}</el-checkbox>
                <template v-if="field.type !== 'references'">
                  <template v-if="form.keys.includes(field.key)">
                    <el-form-item v-for="group in groups" :key="group.key" :label="form.mode === 'individual' ? group.label : undefined" :prop="group.path.join('.') + '.' + field.key" :rules="fieldRules(field)">
                      <ProductionAdjustmentField v-model="group.values[field.key]" :field="field" :members="context.members" />
                    </el-form-item>
                    <small v-if="field.type === 'text'" class="adjust-references__hint">留空将清空此项内容</small>
                  </template>
                  <p v-else class="adjust-current-value">{{ rows.length > 1 && form.mode === 'individual' ? '勾选后逐镜头编辑' : (display(field, form.common[field.key]) === '（清空）' ? '未填写' : display(field, form.common[field.key])) }}</p>
                </template>
                <template v-else>
                  <p class="adjust-current-value">追加参考说明或附件，保留已有资料。</p>
        <el-form-item v-if="form.keys.includes('referenceFileIds')" prop="referenceFileIds">
          <div class="adjust-references">
            <el-alert v-if="rows.length > 1" :title="`本次内容将追加到 ${rows.length} 个任务，保留已有说明和附件。`" type="info" :closable="false" />
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
                </template>
              </section>
            </div>
          </el-card>
        </el-checkbox-group>
        <el-form-item label="调整原因（选填）" prop="reason"><el-input v-model="form.reason" type="textarea" maxlength="500" show-word-limit placeholder="说明与制作人沟通后的调整原因" /></el-form-item>
      </template>
      <template v-else>
        <el-alert title="全部成功才保存；任一任务发生冲突，本批全部不保存。" type="info" :closable="false" />
        <p v-if="form.reason.trim()">调整原因：{{ form.reason }}</p>
        <ProductionAdjustmentPreview :shots="preview" :common="form.mode === 'common'" :added-files="referenceAttachments" :added-description="form.referenceDescription.trim()" />
      </template>
    </el-form>
    <p v-if="loading">正在核对制作任务…</p>
    <template #footer><footer class="adjust-actions"><el-button :disabled="saving" @click="requestClose">关闭</el-button><template v-if="!loading && !error"><el-button :icon="RefreshLeft" :disabled="disabled" @click="reset">重置</el-button><el-button v-if="step > 0" :disabled="disabled" @click="previous">返回编辑</el-button><el-button v-if="step < 2" type="primary" :disabled="disabled" @click="advance">下一步：核对修改</el-button><el-button v-else type="primary" :disabled="disabled" :loading="saving" @click="submit">确认保存（{{ rows.length }}）</el-button></template></footer></template>
  </ProjectDrawer>
</template>
<style scoped>
.adjust-preview-description{margin:0 0 8px;white-space:pre-wrap;overflow-wrap:anywhere}
.adjust-sections{display:grid;gap:16px}
.adjust-section{--el-card-padding:16px;border-radius:10px;border-color:var(--sg-border)}
.adjust-section :deep(.el-card__header){padding:12px 16px;background:var(--sg-surface-soft);font-size:14px}
.adjust-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.adjust-field-grid--schedule{grid-template-columns:minmax(0,2.4fr) minmax(0,1fr) minmax(0,0.8fr)}
.adjust-field-grid--content{grid-template-columns:minmax(0,3fr) minmax(0,1fr)}
.adjust-field-grid--camera{grid-template-columns:repeat(4,minmax(0,1fr))}
.adjust-edit-field{min-width:0;padding:12px;border:1px solid var(--sg-border);border-radius:8px}
.adjust-edit-field.is-selected{border-color:var(--sg-accent);background:var(--sg-surface-soft)}
.adjust-edit-field.is-wide{grid-column:1/-1}
.adjust-edit-field :deep(.el-checkbox){margin:0 0 6px;height:auto;min-height:24px}
.adjust-edit-field :deep(.el-form-item){margin-bottom:4px}
.adjust-edit-field :deep(.el-form-item__content),.adjust-edit-field :deep(.adjustment-field){min-width:0}
.adjust-edit-field :deep(.el-input-number),.adjust-edit-field :deep(.el-date-editor){width:100%;min-width:0;max-width:100%}
.adjust-current-value{margin:0;color:var(--sg-text-muted);font-size:12px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;max-height:82px;overflow:auto}
.adjust-selection-summary{margin:12px 0;color:var(--sg-text-muted)}
.adjust-form :deep(.el-input__inner),.adjust-form :deep(.el-textarea__inner),.adjust-form :deep(.el-checkbox__label),.adjust-form :deep(.el-form-item__label),.adjust-form :deep(.el-select__wrapper),.adjust-form :deep(.el-table){font-size:12px}
@media(max-width:700px){.adjust-field-grid--schedule,.adjust-field-grid--camera{grid-template-columns:repeat(2,minmax(0,1fr))}.adjust-field-grid--schedule>.adjust-edit-field:first-child{grid-column:1/-1}}
@media(max-width:480px){.adjust-field-grid{grid-template-columns:minmax(0,1fr)}}

.adjust-field-selection{margin-top:18px}
.adjust-field-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;width:100%;min-width:0}
.adjust-field-options :deep(.el-checkbox){width:100%;height:auto;min-height:42px;margin:0;padding:10px 12px;border-radius:6px}
.adjust-field-options :deep(.el-checkbox__label){white-space:normal;line-height:1.5;overflow-wrap:anywhere}
@media(max-width:640px){.adjust-field-options{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
@media(max-width:420px){.adjust-field-options{grid-template-columns:minmax(0,1fr)}}
.adjust-form{margin-top:18px}.adjust-group{margin:16px 0;padding:12px;border:1px solid var(--sg-border);border-radius:8px}.adjust-group h3{margin:0 0 14px;font-size:15px}.adjust-actions{display:flex;justify-content:flex-end;gap:8px;margin:0;flex-wrap:wrap}.adjust-gap{margin-top:14px}.adjust-form :deep(.el-table .cell){white-space:pre-wrap;overflow-wrap:anywhere}
.adjust-references{display:flex;flex-direction:column;gap:16px;width:100%;min-width:0;padding:12px 0 4px}
.adjust-references__section{width:100%;min-width:0}
.adjust-references__heading{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px;font-weight:500;line-height:1.6}
.adjust-references__hint{color:var(--sg-text-muted);font-size:12px;font-weight:400;line-height:1.6}
p.adjust-references__hint{margin:6px 0 0}
.adjust-form :deep(.el-form-item__error){position:static;width:100%;line-height:1.5;padding-top:6px}
</style>
