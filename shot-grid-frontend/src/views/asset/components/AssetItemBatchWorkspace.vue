<script setup>
import { createIdempotencyState } from '@/utils/idempotency'
import { versionSummaryLabel } from '@/components/version/versionPresentation'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batchAssignAssetItemTasks, getAssetDetail, listAssetAssignees } from '@/api/shot-grid/assets'
import { getProjectDetail } from '@/api/shot-grid/projects'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { useSessionStore } from '@/store/modules/session'
import { canScheduleAssetItem } from '../assetItemActions'
import { tagTypeFromTone } from '@/utils/tag'
import { formatTaskDateTime } from '@/views/task/taskPresentation'
import { assetStatusMeta, memberLabel } from '../assetPresentation'
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'
import BatchOverallFeedbackDialog from '@/components/version/BatchOverallFeedbackDialog.vue'
import BatchAppendIssueDialog from '@/components/version/BatchAppendIssueDialog.vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import AssetProductionAdjustmentDialog from './AssetProductionAdjustmentDialog.vue'

const props = defineProps({ itemStatus: { type: String, default: '' }, projectId: { type: Number, required: true }, contextKey: { type: String, required: true } })
const emit = defineEmits(['changed', 'active-change'])
const session = useSessionStore()
const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const attempted = ref(false)
const rows = ref([])
const selected = ref([])
const members = ref([])
const project = ref(null)
const mode = ref('')
const entryAction = ref('')
const showUnavailable = ref(false)
const selectionNotice = ref('')
const formRef = ref(null)
const tableRef = ref(null)
const feedback = ref(null)
const feedbackOpen = ref(false)
const details = ref(null)
const adjustment = ref(null)
const append = ref(null)
const form = reactive({ commonAssignee: '', commonRange: [], reason: '', rows: [] })
let generation = 0
let disposed = false
let controller
const permitted = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const manager = computed(() => project.value && !['completed', 'archived'].includes(project.value.projectStatus) && (project.value.myProjectRole === 'director' || permitted('shotgrid:project:all')))
const blocked = computed(() => loading.value || busy.value || Boolean(error.value) || attempted.value)
const childOpen = computed(() => feedbackOpen.value || Boolean(adjustment.value) || Boolean(append.value))
const current = token => !disposed && visible.value && token === generation
function eligible(row, action) {
  if (!manager.value || row.asset.lifecycleStatus !== 'active' || row.lifecycleStatus !== 'active') return false
  if (action === 'schedule') return canScheduleAssetItem(row.asset, row, permitted('shotgrid:task:schedule'))
  const permission = { assign: 'shotgrid:task:assign', adjust: 'shotgrid:task:edit', review: 'shotgrid:version:review', append: 'shotgrid:version:review' }[action]
  if (!permitted(permission)) return false
  if (action === 'adjust' && !permitted('shotgrid:task:query')) return false
  if (['review', 'append'].includes(action) && (!permitted('shotgrid:note:add') || !permitted('shotgrid:version:query'))) return false
  return Boolean(row.allowedActions?.includes({ assign: 'task.assign', adjust: 'task.adjust', review: 'task.review', append: 'task.appendIssue' }[action]))
}
const available = action => !blocked.value && !childOpen.value && selected.value.length > 0 && selected.value.length <= 100 && selected.value.every(row => eligible(row, action))
const actionOptions = [
  { key: 'assign', label: '分配制作人', next: '选择制作人' },
  { key: 'schedule', label: '设置排期', next: '填写排期' },
  { key: 'adjust', label: '制作要求与参考资料', next: '制作要求与参考资料' },
  { key: 'review', label: '审核反馈', next: '填写反馈' },
  { key: 'append', label: '追加问题', next: '追加问题' }
]
const activeAction = computed(() => actionOptions.find(action => action.key === entryAction.value))
const drawerTitle = computed(() => activeAction.value?.label || '制作分项批量操作')
const eligibleRows = computed(() => rows.value.filter(row => entryAction.value ? eligible(row, entryAction.value) : actionOptions.some(action => eligible(row, action.key))))
const displayRows = computed(() => !entryAction.value || showUnavailable.value ? rows.value : eligibleRows.value)
const unavailableCount = computed(() => rows.value.length - eligibleRows.value.length)
const assetCount = computed(() => new Set(rows.value.map(row => row.assetId)).size)
const canSelect = row => !blocked.value && !mode.value && !childOpen.value && (entryAction.value ? eligible(row, entryAction.value) : actionOptions.some(action => eligible(row, action.key)))
function unavailableReason(row) {
  if (!entryAction.value || eligible(row, entryAction.value)) return ''
  if (row.lifecycleStatus !== 'active' || row.asset.lifecycleStatus !== 'active') return '已归档，不能操作'
  if (entryAction.value === 'schedule' && !row.task) return '请先分配制作人'
  if (entryAction.value === 'assign' && !String(row.productionItem || '').trim()) return '请先完善分项信息'
  if (entryAction.value === 'assign' && row.task?.taskStatus !== 'not_started' && row.task) return '已开工，不能直接改派'
  if (row.task?.taskStatus === 'completed') return '已完成，不能执行此操作'
  return '当前状态或权限不支持此操作'
}
async function chooseAction(action) {
  if (blocked.value || mode.value || childOpen.value) return
  const token = generation
  const previous = [...selected.value]
  entryAction.value = action
  showUnavailable.value = false
  const retained = previous.filter(row => eligible(row, action))
  selectionNotice.value = previous.length > retained.length ? `${previous.length - retained.length} 个分项不适用于此操作，请核对后继续。` : ''
  await nextTick()
  if (!current(token)) return
  tableRef.value?.clearSelection()
  retained.forEach(row => tableRef.value?.toggleRowSelection(row, true, false))
  await nextTick()
  if (current(token) && previous.length && previous.length === retained.length) begin(action)
}
async function backToSelection() {
  const token = generation
  const ids = new Set(selected.value.map(row => row.assetItemId))
  mode.value = ''
  await nextTick()
  if (!current(token)) return
  for (const row of displayRows.value) if (ids.has(row.assetItemId) && canSelect(row)) tableRef.value?.toggleRowSelection(row, true, false)
}


function invalidate() {
  generation++
  controller?.abort()
  visible.value = false
  loading.value = false
  busy.value = false
  mode.value = ''
  adjustment.value = null
  append.value = null
  rows.value = []; selected.value = []; members.value = []; form.rows = []
}
watch(() => props.contextKey, invalidate)
watch(visible, value => emit('active-change', value))
onBeforeUnmount(() => { disposed = true; invalidate() })
async function open(assets, ids = [], action = '') {
  if (visible.value || busy.value || !props.projectId || !permitted('shotgrid:asset:query')) return
  invalidate()
  entryAction.value = action
  showUnavailable.value = false; selectionNotice.value = ''
  visible.value = true; loading.value = true; attempted.value = false; error.value = ''; project.value = null
  const token = generation
  controller = new AbortController()
  const signal = controller.signal
  try {
    const { data } = await getProjectDetail(props.projectId, { signal })
    if (!current(token)) return
    project.value = data
    if (Number(data.projectId) !== props.projectId || !manager.value) throw new Error('当前项目不允许管理分项，请刷新核对权限')
    const unique = [...new Map(assets.map(asset => [asset.assetId, asset])).values()]
    if (unique.length > 100 || unique.some(asset => Number(asset.projectId) !== props.projectId)) throw new Error('请在当前项目内选择最多 100 个资产')
    for (const parent of unique) {
      const { data: asset } = await getAssetDetail(props.projectId, parent.assetId, { signal })
      if (!current(token)) return
      if (Number(asset.projectId) !== props.projectId || Number(asset.assetId) !== Number(parent.assetId)) throw new Error('资产范围已变化，请关闭后刷新')
      rows.value.push(...asset.items.filter(item => ids.length ? ids.includes(item.assetItemId) : (!props.itemStatus || item.assetStatus === props.itemStatus)).map(item => ({ ...item, asset, displayLabel: `${asset.assetName} · ${item.productionItem || '未命名分项'}`, result: '' })))
    }
    if (permitted('shotgrid:task:assign')) {
      let pageNum = 1
      let hasNext = true
      while (hasNext) {
        const response = await listAssetAssignees(props.projectId, { pageNum, pageSize: 100 }, { signal })
        if (!current(token)) return
        members.value.push(...(response.rows || []).filter(member => member.producerCode))
        hasNext = Boolean(response.hasNext)
        if (hasNext && pageNum >= 100) throw new Error('制作人选项过多，请联系管理员缩小项目成员范围')
        pageNum++
      }
    }
    loading.value = false
    // 从分项行打开时只预选该分项，父资产批量入口要求用户明确勾选。
    await nextTick()
    if (ids.length && rows.value.length !== new Set(ids).size) throw new Error('部分所选分项已不可见，请关闭后刷新列表')
    if (current(token)) for (const row of displayRows.value) if (ids.includes(row.assetItemId) && canSelect(row)) tableRef.value?.toggleRowSelection(row, true)
    await nextTick()
    if (current(token) && action) begin(action)
  } catch (failure) { if (current(token) && !signal.aborted) error.value = failure?.message || '分项加载失败，请关闭重试' }
  finally { if (current(token)) loading.value = false }
}
function begin(action) {
  if (!available(action)) return
  if (action === 'review') {
    const token = generation
    feedback.value.open(props.projectId, selected.value.map(row => ({ ...row, canInspect: true })), () => current(token) && selected.value.every(row => eligible(row, 'review')))
    return
  }
  const token = generation
  const context = { projectId: props.projectId, targets: [...selected.value], permissions: [...session.permissions], validateContext: () => current(token) && selected.value.every(row => eligible(row, action)) }
  if (action === 'adjust') { adjustment.value = context; return }
  if (action === 'append') {
    append.value = { ...context, targets: selected.value.map(row => ({ versionId: row.latestVersion.versionId, label: `${row.displayLabel} · ${versionSummaryLabel(row.latestVersion)}` })) }
    return
  }
  form.commonAssignee = ''; form.commonRange = []; form.reason = ''
  form.rows = selected.value.map(row => ({ ...row, assigneeUserId: row.task?.assigneeUserId ? String(row.task.assigneeUserId) : '', range: row.task?.expectedStartTime && row.task?.expectedEndTime ? [row.task.expectedStartTime, row.task.expectedEndTime] : [], result: '', key: createIdempotencyState(`asset-batch:${row.task?.taskId}`).forPayload({ taskId: row.task?.taskId }) }))
  mode.value = action
}
function applyCommon() {
  if (blocked.value) return
  for (const row of form.rows) {
    if (mode.value === 'assign' && form.commonAssignee) row.assigneeUserId = form.commonAssignee
    if (mode.value === 'schedule' && form.commonRange.length === 2) row.range = [...form.commonRange]
  }
  formRef.value?.clearValidate()
}
const memberRules = [{ validator: (_rule, value, done) => done(members.value.some(member => Number(member.userId) === Number(value)) ? undefined : new Error('请选择有效制作人')) }]
const rangeRules = [{ validator: (_rule, value, done) => done(Array.isArray(value) && value.length === 2 && value.every(item => item && Number.isFinite(new Date(item).getTime())) && new Date(value[1]) > new Date(value[0]) ? undefined : new Error('请选择完整且结束晚于开始的时间')) }]
async function submit() {
  if (blocked.value || !mode.value || !form.rows.length) return
  const token = generation
  // 将异步表单校验纳入忙碌区间，防止连续点击生成重复批次。
  busy.value = true
  const valid = await formRef.value?.validate().catch(() => false)
  if (!current(token)) return
  if (!valid) { busy.value = false; return }
  if (!form.rows.every(row => eligible(row, mode.value))) { error.value = '权限或状态已变化，请关闭并刷新'; busy.value = false; return }
  attempted.value = true
  try {
    if (mode.value === 'assign') {
      const groups = new Map()
      for (const row of form.rows) {
        const id = Number(row.assigneeUserId)
        groups.set(id, [...(groups.get(id) || []), row])
      }
      for (const [id, targets] of groups) {
        if (!current(token)) return
        if (!targets.every(row => eligible(row, 'assign'))) throw { status: 403, message: '当前分配权限已变化' }
        targets.forEach(row => { row.result = '正在保存' })
        await batchAssignAssetItemTasks(props.projectId, id, targets.map(row => ({ assetItemId: row.assetItemId, taskLockVersion: row.task?.lockVersion ?? null })))
        if (!current(token)) return
        targets.forEach(row => { row.result = '已保存' })
      }
    } else {
      for (const row of form.rows) {
        if (!current(token)) return
        if (!eligible(row, 'schedule')) throw { status: 403, message: '当前排期权限已变化' }
        if (row.range.every((value, index) => new Date(value).getTime() === new Date([row.task.expectedStartTime, row.task.expectedEndTime][index]).getTime())) {
          row.result = '未改动，已跳过'
          continue
        }
        row.result = '正在保存'
        await updateTaskSchedule(row.task.taskId, { expectedStartTime: row.range[0], expectedEndTime: row.range[1], changeReason: form.reason.trim(), operationSource: 'dialog', lockVersion: row.task.lockVersion }, row.key)
        if (!current(token)) return
        row.result = '已保存'
      }
    }
    if (current(token)) ElMessage.success('所选分项已保存，任务不会自动开工')
  } catch (failure) {
    if (current(token)) {
      const status = Number(failure?.httpStatus || failure?.status)
      const message = [401, 403, 404, 409, 422].includes(status) ? failure?.message || '保存失败' : '请求结果未知，请刷新核对，勿直接重复保存'
      form.rows.filter(row => row.result === '正在保存').forEach(row => { row.result = message })
      error.value = `${message}；已保存项保留，后续项未执行。请关闭并刷新后核对。`
    }
  } finally {
    if (current(token)) { form.rows.filter(row => !row.result).forEach(row => { row.result = '未执行' }); busy.value = false; emit('changed') }
  }
}
async function finishChild() {
  adjustment.value = null; append.value = null
  emit('changed')
  invalidate()
}
async function close(done) {
  if (busy.value || childOpen.value) return
  if (mode.value && !attempted.value && !await ElMessageBox.confirm('关闭将放弃尚未保存的批量填写。', '关闭分项操作？', { type: 'warning' }).then(() => true).catch(() => false)) return
  invalidate()
  if (typeof done === 'function') done()
}
defineExpose({ open })
</script>

<template>
  <el-drawer v-model="visible" :title="drawerTitle" class="asset-batch-drawer" size="min(1080px, 96vw)" append-to-body destroy-on-close :before-close="close" :close-on-click-modal="false" :show-close="!busy && !childOpen" :close-on-press-escape="!busy && !childOpen">
    <div class="workspace-summary"><el-text type="info">涉及 {{ assetCount }} 个资产 · {{ rows.length }} 个制作分项</el-text><el-tag size="small" effect="plain">{{ mode ? '填写并确认' : '选择操作与分项' }}</el-tag></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="batch-gap" />
    <template v-if="!mode">
      <div class="operation-picker" aria-label="选择分项操作">
        <el-radio-group :model-value="entryAction" :disabled="blocked || childOpen" aria-label="操作类型" @change="chooseAction">
          <el-radio-button v-for="action in actionOptions.slice(0, 4)" :key="action.key" :value="action.key">{{ action.label }}（{{ rows.filter(row => eligible(row, action.key)).length }}）</el-radio-button>
        </el-radio-group>
        <el-dropdown :disabled="blocked || childOpen" @command="chooseAction"><el-button :type="entryAction === 'append' ? 'primary' : 'default'">{{ entryAction === 'append' ? '追加问题' : '更多操作' }}</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="append">追加问题（{{ rows.filter(row => eligible(row, 'append')).length }}）</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      </div>
      <el-alert v-if="selectionNotice" :title="selectionNotice" type="warning" :closable="false" class="batch-gap" />
      <div class="selection-summary"><el-text>{{ entryAction ? `可操作 ${eligibleRows.length} 项，请勾选需要处理的分项` : '请选择本次要执行的操作；列表中已勾选的分项会保留' }}</el-text><el-switch v-if="entryAction && unavailableCount" v-model="showUnavailable" aria-label="显示不可操作分项" :active-text="`显示不可操作分项（${unavailableCount}）`" :disabled="blocked || childOpen" /></div>
      <el-table class="batch-table" key="selection" ref="tableRef" v-loading="loading" :data="displayRows" row-key="assetItemId" max-height="520" @selection-change="selected = $event">
        <el-table-column :key="`selection:${blocked}:${childOpen}:${entryAction}`" type="selection" width="48" :selectable="canSelect" reserve-selection />
        <el-table-column label="制作分项 / 所属资产" min-width="220"><template #default="{ row }"><div class="item-name"><el-text tag="strong">{{ row.productionItem || '未命名分项' }}</el-text><el-text size="small" type="info">{{ row.asset.assetName }}</el-text></div></template></el-table-column>
        <el-table-column label="制作人" width="110"><template #default="{ row }">{{ members.find(member => Number(member.userId) === Number(row.task?.assigneeUserId))?.userName || row.task?.assigneeName || '未分配' }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="tagTypeFromTone(assetStatusMeta(row.assetStatus).tone)">{{ assetStatusMeta(row.assetStatus).label }}</el-tag></template></el-table-column>
        <el-table-column label="计划时间" min-width="170"><template #default="{ row }"><div class="item-name"><span>{{ row.task?.expectedStartTime ? formatTaskDateTime(row.task.expectedStartTime) : '未排期' }}</span><span v-if="row.task?.expectedEndTime">{{ formatTaskDateTime(row.task.expectedEndTime) }}</span></div></template></el-table-column>
        <el-table-column v-if="showUnavailable && entryAction" label="操作说明" min-width="175"><template #default="{ row }"><el-text :type="eligible(row, entryAction) ? 'success' : 'info'" size="small">{{ unavailableReason(row) || '可操作' }}</el-text></template></el-table-column>
        <el-table-column v-else label="版本" width="90"><template #default="{ row }">{{ versionSummaryLabel(row.latestVersion) }}</template></el-table-column>
        <template #empty><el-empty :image-size="64" :description="loading ? '正在加载分项' : entryAction ? '没有符合此操作条件的分项' : '暂无制作分项'" /></template>
      </el-table>
    </template>
    <el-form v-else ref="formRef" :model="form" :disabled="blocked" label-position="top" class="batch-gap">
      <el-alert title="可统一填写后应用，也可逐项调整；确认保存后生效。" type="info" :closable="false" />
      <div class="batch-actions">
        <el-form-item v-if="mode === 'assign'" class="batch-actions__assignee" label="统一制作人（选填）" prop="commonAssignee">
          <el-select v-model="form.commonAssignee" placeholder="选择制作人"><el-option v-for="member in members" :key="member.userId" :value="String(member.userId)" :label="memberLabel(member)" /></el-select>
        </el-form-item>
        <el-form-item v-else class="batch-actions__schedule" label="统一计划时间（选填）" prop="commonRange">
          <ScheduleDateRangePicker v-model="form.commonRange" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" />
        </el-form-item>
        <el-button class="batch-actions__apply" type="primary" plain :disabled="blocked" @click="applyCommon">应用到所选分项</el-button>
      </div>
      <el-table class="batch-table" :key="mode" :data="form.rows" row-key="assetItemId" max-height="500"><el-table-column prop="displayLabel" label="资产 / 制作分项" min-width="200" /><el-table-column :label="mode === 'assign' ? '制作人' : '计划起止时间'" min-width="380"><template #default="{ row, $index }"><el-form-item v-if="mode === 'assign'" :prop="`rows.${$index}.assigneeUserId`" :rules="memberRules" ><el-select v-model="row.assigneeUserId" style="width: 100%"><el-option v-for="member in members" :key="member.userId" :value="String(member.userId)" :label="memberLabel(member)" /></el-select></el-form-item><el-form-item v-else :prop="`rows.${$index}.range`" :rules="rangeRules"><ScheduleDateRangePicker v-model="row.range" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item></template></el-table-column><el-table-column prop="result" label="保存结果" min-width="200" /></el-table>
      <el-form-item v-if="mode === 'schedule'" label="排期原因（选填）" prop="reason" :rules="[{ max: 500, message: '最多 500 字' }]"><el-input v-model="form.reason" maxlength="500" /></el-form-item>
    </el-form>
    <template #footer><div class="workspace-footer"><div><el-text>已选 {{ mode ? form.rows.length : selected.length }} 个分项</el-text><el-text v-if="selected.length > 100" type="danger" size="small">每次最多操作 100 个分项</el-text><el-text v-else type="info" size="small">{{ attempted ? '请核对逐项保存结果' : '仅处理所选分项' }}</el-text></div><div class="workspace-footer__buttons"><el-button :disabled="busy || childOpen" @click="close">{{ attempted ? '完成' : '取消' }}</el-button><el-button v-if="mode && !attempted" :disabled="busy" @click="backToSelection">返回选择</el-button><el-button v-if="!mode" type="primary" :disabled="!entryAction || !available(entryAction)" @click="begin(entryAction)">{{ activeAction ? `下一步：${activeAction.next}` : '请选择操作' }}</el-button><el-button v-else-if="!attempted" type="primary" :disabled="blocked || !form.rows.length" :loading="busy" @click="submit">确认保存 {{ form.rows.length }} 个分项</el-button></div></div></template>
  </el-drawer>
  <BatchOverallFeedbackDialog v-if="visible" ref="feedback" @active-change="feedbackOpen = $event" @saved="finishChild" @review="details.open(`/versions/${$event.latestVersion.versionId}`)" />
  <BatchAppendIssueDialog v-if="append" :context="append" @close="finishChild" />
  <AssetProductionAdjustmentDialog v-if="adjustment" :context="adjustment" @close="finishChild" />
  <RelatedDetailDrawer ref="details" />
</template>
<style scoped>
.workspace-summary,.selection-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.operation-picker{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0}.selection-summary{margin:16px 0}.item-name{display:flex;flex-direction:column;align-items:flex-start;gap:4px}.workspace-footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.workspace-footer>div:first-child{display:flex;flex-direction:column;align-items:flex-start;gap:4px}.workspace-footer__buttons{display:flex;gap:8px;flex-wrap:wrap}.workspace-footer__buttons :deep(.el-button){margin-left:0}@media(max-width:760px){.workspace-footer{align-items:flex-start;flex-direction:column}.operation-picker :deep(.el-radio-group){display:flex;flex-wrap:wrap;gap:8px}}
.batch-gap{margin-top:16px}.batch-gap :deep(.el-date-editor){width:100%}.batch-gap :deep(.el-form-item){margin-bottom:12px}
.batch-actions{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px;margin:16px 0;padding:16px;background:var(--sg-bg);border:1px solid var(--sg-border);border-radius:var(--sg-radius-sm)}
.batch-actions :deep(.el-form-item){margin-bottom:0}
.batch-actions :deep(.el-form-item__label){margin-bottom:8px;line-height:20px;height:auto}
.batch-actions__assignee{flex:0 1 280px;min-width:0}
.batch-actions__assignee :deep(.el-select){width:100%}
.batch-actions__schedule{flex:0 1 420px;min-width:0}
.batch-actions__apply{margin-left:0;flex-shrink:0}
@media(max-width:600px){.batch-actions{padding:12px}.batch-actions__assignee,.batch-actions__schedule{flex-basis:100%;width:100%}.batch-actions__apply{width:100%}}
.batch-table{font-size:12px;--el-font-size-base:12px;--el-font-size-small:12px;--el-font-size-extra-small:12px}
.batch-table :deep(.cell),.batch-table :deep(.el-text),.batch-table :deep(.el-tag),.batch-table :deep(.el-select__wrapper),.batch-table :deep(.el-input__inner),.batch-table :deep(.el-range-input){font-size:12px}
.batch-table .item-name{text-align:left}
.batch-table .item-name :deep(.el-text){align-self:flex-start;text-align:left}
</style>
