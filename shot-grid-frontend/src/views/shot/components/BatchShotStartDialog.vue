<script setup>
import { createIdempotencyState } from '@/utils/idempotency'
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'
import { RefreshLeft } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElCheckbox, ElDrawer, ElTag } from 'element-plus'
import { getShotDetail } from '@/api/shot-grid/shots'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { startTask } from '@/api/shot-grid/tasks'
import ShotProductionInfo from './ShotProductionInfo.vue'
import { formatTaskDateTime } from '@/views/task/taskPresentation'
import { shotAssigneeName } from '../shotPresentation'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close'])
const context = props.context
const formRef = ref(null)
const loading = ref(true)
const saving = ref(false)
const finished = ref(false)
const error = ref('')
const rows = ref([])
const tableRef = ref(null)
const selected = ref([])
const scheduleOnly = context.mode === 'schedule'
const singleSchedule = scheduleOnly && context.shots.length === 1
const scheduleVisible = ref(false)
const scheduleFormRef = ref(null)
const scheduleForm = reactive({ range: [], reason: '' })
const inlineFormRef = ref(null)
const inlineForm = reactive({ range: [], reason: '', rows: [] })
const inlineRangeRules = [{ validator: (_rule, value, done) => {
  const [start, end] = (value || []).map(time => new Date(time).getTime())
  done(Number.isFinite(start) && Number.isFinite(end) && end > start ? undefined : new Error('请选择完整且结束晚于开始的时间'))
}, trigger: 'change' }]
const inlinePending = computed(() => rows.value.filter(row => !row.draftRange?.[0] || !row.draftRange?.[1]).length)
async function applyInlineRange() {
  if (saving.value || !selected.value.length) return
  if (!await inlineFormRef.value.validateField('range').catch(() => false)) return
  selected.value.filter(row => !row.blocked).forEach(row => { row.draftRange = [...inlineForm.range] })
  inlineFormRef.value.clearValidate()
}
const scheduleTargets = ref([])
const scheduleError = ref('')
const scheduleRules = {
  range: [{ validator: (_rule, value, callback) => {
    const [start, end] = (value || []).map(time => new Date(time).getTime())
    callback(Number.isFinite(start) && Number.isFinite(end) && end > start ? undefined : new Error('请选择完整时间，结束时间须晚于开始时间'))
  }, trigger: 'change' }],
  reason: [{ max: 500, message: '最多500字', trigger: 'blur' }]
}
const hasSchedule = row => Boolean(row.detail.task.expectedStartTime && row.detail.task.expectedEndTime)
const pendingRows = computed(() => selected.value.filter(row => !hasSchedule(row)))
const form = reactive({ priority: 'normal', confirmed: true })
let disposed = false
let attempted = false
onBeforeUnmount(() => { disposed = true })
const current = () => !disposed && context.validateContext()
const blockedSelection = computed(() => selected.value.some(row => row.blocked))
const needsSchedule = computed(() => selected.value.some(row => !hasSchedule(row)))
const successCount = computed(() => rows.value.filter(row => row.success).length)
const rules = {
  priority: [{ required: true, message: '请选择任务优先级', trigger: 'change' }],
  confirmed: [{ validator: (_rule, value, callback) => value === true ? callback() : callback(new Error('请先确认全部镜头的开工条件')), trigger: 'change' }]
}


onMounted(async () => {
  try {
    // 固定打开弹窗时的任务和锁号，详情只用于核对，不自动替换过期版本。
    for (const shot of context.shots) {
      if (!current()) return
      const { data: detail } = await getShotDetail(context.projectId, shot.shotId)
      if (!current()) return
      if ((!scheduleOnly && !detail?.allowedActions?.includes('task.start')) || detail.task?.taskId !== shot.taskId ||
          detail.task.lockVersion !== shot.taskLockVersion || detail.lockVersion !== shot.lockVersion) {
        throw new Error(`${shot.shotCode} 的任务或制作信息已变化，请关闭并刷新后重新选择`)
      }
      rows.value.push({ ...shot, detail, draftRange: detail.task.expectedStartTime && detail.task.expectedEndTime ? [detail.task.expectedStartTime, detail.task.expectedEndTime] : [], result: '待确认', success: false, blocked: false })
    }
  } catch (failure) {
    if (!disposed) error.value = failure?.message || '镜头详情加载失败，请关闭后重试'
  } finally {
    if (!disposed) {
      loading.value = false
      inlineForm.rows = rows.value
      await nextTick()
      rows.value.forEach(row => tableRef.value?.toggleRowSelection(row, true))
      if (context.single && !scheduleOnly && !error.value) openSchedule(rows.value)
    }
  }
})

function close() {
  if (!saving.value) emit('close', { attempted })
}
function reset() {
  if (saving.value || finished.value) return
  formRef.value?.resetFields()
}
function selectScheduled() {
  tableRef.value?.clearSelection()
  rows.value.filter(row => hasSchedule(row) && !row.blocked && !row.success).forEach(row => tableRef.value?.toggleRowSelection(row, true))
}
function openSchedule(targets) {
  if (saving.value || loading.value || error.value || !context.canSchedule || !targets.length || targets.some(row => row.blocked) || !current()) return
  scheduleTargets.value = targets.map(row => ({ row, key: createIdempotencyState(`batch-schedule:${row.taskId}`).forPayload({ taskId: row.taskId }) }))
  scheduleForm.range = targets.length === 1 && hasSchedule(targets[0]) ? [targets[0].detail.task.expectedStartTime, targets[0].detail.task.expectedEndTime] : []
  scheduleForm.reason = ''
  scheduleError.value = ''
  scheduleVisible.value = true
  nextTick(() => scheduleFormRef.value?.clearValidate())
}
async function saveSchedules() {
  if (saving.value || loading.value || error.value || !context.canSchedule || !current()) return
  saving.value = true
  try {
    if (scheduleOnly) {
      if (!rows.value.length || rows.value.some(row => row.blocked)) return
      const fields = ['reason', ...rows.value.map((_row, index) => `rows.${index}.draftRange`)]
      if (!await inlineFormRef.value.validateField(fields).catch(() => false) || !current()) return
      scheduleTargets.value = rows.value.map(row => ({ row, key: createIdempotencyState(`batch-schedule:${row.taskId}`).forPayload({ taskId: row.taskId }) }))
    }
    if ((!scheduleOnly && !await scheduleFormRef.value?.validate().catch(() => false)) || !current()) return
    let failed = false
    for (const { row, key } of scheduleTargets.value) {
      if (!current()) return
      const range = scheduleOnly ? [...row.draftRange] : scheduleForm.range
      if (hasSchedule(row) && new Date(row.detail.task.expectedStartTime).getTime() === new Date(range[0]).getTime() && new Date(row.detail.task.expectedEndTime).getTime() === new Date(range[1]).getTime()) {
        row.result = '排期未变更'
        continue
      }
      attempted = true
      try {
        const { data } = await updateTaskSchedule(row.taskId, {
          lockVersion: row.taskLockVersion, expectedStartTime: range[0], expectedEndTime: range[1],
          changeReason: (scheduleOnly ? inlineForm.reason : scheduleForm.reason).trim(), operationSource: 'dialog'
        }, key)
        if (!current()) return
        if (data?.taskId !== row.taskId || !Number.isInteger(data.lockVersion) || !data.currentStart || !data.currentEnd) throw new Error('响应不完整，请关闭并刷新核对')
        row.taskLockVersion = data.lockVersion
        Object.assign(row.detail.task, { lockVersion: data.lockVersion, expectedStartTime: data.currentStart, expectedEndTime: data.currentEnd })
        row.result = '排期已保存，尚未开工'
      } catch (failure) {
        if (!current()) return
        row.result = failure?.message || '结果未知，请关闭并刷新核对'
        row.blocked = true
        failed = true
        if (![409, 422].includes(Number(failure?.httpStatus || failure?.status))) break
      }
    }
    scheduleVisible.value = false
    if ((context.single || scheduleOnly) && !failed) emit('close', { attempted })
    scheduleError.value = failed ? '部分排期未保存，请查看逐项结果；失败项请关闭并刷新后核对。已保存项不会撤销，也不会自动开工。' : ''
  } finally { saving.value = false }
}
async function submit() {
  if (loading.value || saving.value || finished.value || error.value || blockedSelection.value || needsSchedule.value || !selected.value.length || scheduleOnly || scheduleVisible.value) return
  saving.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false) || disposed) return
    if (!current()) { error.value = '项目或选中任务已变化，请关闭并重新选择'; return }
    for (const row of [...selected.value]) {
      if (!current()) break
      row.result = '正在确认开工'
      attempted = true
      try {
        const response = await startTask(row.taskId, {
          lockVersion: row.taskLockVersion, shotLockVersion: row.lockVersion, assetsConfirmed: true,
          priority: form.priority
        })
        if (!current()) return
        row.success = true
        row.result = response.data?.taskStatus === 'preparing' ? '已开工，目录准备中' : '已开工，可以开始制作'
      } catch (failure) {
        if (!current()) return
        const status = Number(failure?.httpStatus || failure?.status)
        row.result = failure?.message || '请求结果未知，请刷新核对任务状态'
        // 业务冲突可继续处理其他镜头；权限或网络异常停止后续请求，不自动重试。
        if (![409, 422].includes(status)) break
      }
    }
    if (!disposed) {
      selected.value.filter(row => row.result === '待确认').forEach(row => { row.result = '未执行，请刷新后重新选择' })
      finished.value = true
    }
  } finally { saving.value = false }
}
</script>

<template>
  <el-drawer v-if="scheduleOnly" :model-value="true" :title="singleSchedule ? '设置排期' : '批量设置排期'" class="batch-schedule-drawer" size="min(1040px, 95vw)" direction="rtl" append-to-body :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" @close="close">
      <p class="batch-schedule-description">{{ singleSchedule ? '核对镜头信息，填写计划起止时间后保存' : `已选择 ${context.shots.length} 个镜头，请逐项核对制作信息和负责人` }}</p>
      <el-alert :title="singleSchedule ? '保存计划时间不会自动开工，之后由管理人员确认开工。' : '先设置计划时间，再单独确认开工。保存逐项生效，成功项会保留。'" type="info" :closable="false" show-icon />
      <el-form ref="inlineFormRef" :model="inlineForm" :rules="{ reason: scheduleRules.reason }" :disabled="saving || loading || Boolean(error) || rows.some(row => row.blocked)" label-position="top" class="inline-schedule-form" :aria-label="singleSchedule ? '单项排期表单' : '批量排期表单'">
        <div v-if="!singleSchedule" class="inline-schedule-toolbar">
          <div><strong>批量设置</strong><small>已勾选 {{ selected.length }} 项</small></div>
          <el-form-item prop="range" :rules="inlineRangeRules"><ScheduleDateRangePicker v-model="inlineForm.range" type="datetimerange" format="YYYY-MM-DD HH:mm" value-format="YYYY-MM-DDTHH:mm:ss" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" aria-label="统一计划起止时间" /></el-form-item>
          <el-button type="primary" :disabled="!selected.length" @click="applyInlineRange">应用到勾选项</el-button>
        </div>
        <div v-if="!singleSchedule" class="inline-schedule-heading"><strong>逐项核对</strong><span>下方时间可单独调整，保存全部 {{ rows.length }} 项</span></div>
        <el-table ref="tableRef" v-loading="loading" :data="rows" row-key="shotId" height="100%" @selection-change="value => selected = value">
          <el-table-column v-if="!singleSchedule" type="selection" width="42" :selectable="row => !saving && !row.blocked" />
          <el-table-column label="镜头" width="145" show-overflow-tooltip><template #default="{ row }">{{ [row.episodeCode, row.sceneCode, row.shotCode].join(' / ') }}</template></el-table-column>
          <el-table-column label="制作内容" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.detail.description || row.description || '未填写' }}</template></el-table-column>
          <el-table-column label="制作人" width="80" show-overflow-tooltip><template #default="{ row }">{{ shotAssigneeName(row.detail.task.assignee || row.assignee, context.members) }}</template></el-table-column>
          <el-table-column label="计划起止时间" width="330"><template #default="{ row, $index }">
            <el-form-item :prop="`rows.${$index}.draftRange`" :rules="inlineRangeRules"><ScheduleDateRangePicker v-model="row.draftRange" type="datetimerange" format="YYYY-MM-DD HH:mm" value-format="YYYY-MM-DDTHH:mm:ss" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" :aria-label="`${row.shotCode} 计划起止时间`" /></el-form-item>
            <small v-if="hasSchedule(row)" class="inline-schedule-original">原：{{ formatTaskDateTime(row.detail.task.expectedStartTime) }} 至 {{ formatTaskDateTime(row.detail.task.expectedEndTime) }}</small>
          </template></el-table-column>
          <el-table-column v-if="scheduleError" label="执行结果" prop="result" min-width="150" />
        </el-table>
        <div v-if="!singleSchedule" class="inline-schedule-summary">共 {{ rows.length }} 项 · 已填写 {{ rows.length - inlinePending }} 项 · 未填写 {{ inlinePending }} 项</div>
        <el-form-item label="排期原因（选填）" prop="reason"><el-input v-model="inlineForm.reason" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item>
      </el-form>
      <el-alert v-if="error || scheduleError" :title="error || scheduleError" type="error" show-icon :closable="false" />
      <template #footer><el-button :disabled="saving" @click="close">{{ attempted ? '关闭并刷新' : '取消' }}</el-button><el-button type="primary" :loading="saving" :disabled="loading || Boolean(error) || rows.some(row => row.blocked) || !rows.length || !context.canSchedule" @click="saveSchedules">保存排期</el-button></template>
  </el-drawer>
  <el-drawer v-if="!scheduleOnly && (!context.single || error || scheduleError)" :model-value="true" :title="context.single ? '设置排期' : '批量确认开工'" class="batch-start-drawer" size="min(1040px, 95vw)" direction="rtl" append-to-body :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" @close="close">
    <p class="batch-schedule-description">已选择 {{ context.shots.length }} 个镜头，请逐项核对制作信息和负责人</p>
    <el-alert title="请核对制作内容和制作人，确认所需资产齐备后开工。将沿用已保存的排期，开工结果逐项反馈。" type="info" :closable="false" show-icon />
    <div v-if="!loading && !error && !finished" class="batch-start-overview"><strong>本次开工 {{ selected.length }} 项</strong><span>展开镜头可查看完整制作要求</span></div>
    <div v-if="!loading && !error && !finished && needsSchedule" class="batch-schedule-toolbar">
      <div class="batch-schedule-summary"><strong>有 {{ pendingRows.length }} 项缺少排期</strong><span>补齐后再确认开工，或仅选择已排期项</span></div>
      <div class="batch-schedule-buttons">
        <el-button v-if="context.canSchedule" type="primary" plain :disabled="saving" @click="openSchedule(pendingRows)">统一设置未排期（{{ pendingRows.length }}）</el-button>
        <el-button :disabled="saving" @click="selectScheduled">仅选择已排期项</el-button>
      </div>
    </div>
    <el-table class="batch-start-table" ref="tableRef" v-loading="loading" @selection-change="value => selected = value" :data="rows" row-key="shotId" height="100%" empty-text="正在读取镜头详情">
      <el-table-column type="selection" width="36" :selectable="row => !saving && !finished && !row.success" />
      <el-table-column type="expand" width="32"><template #default="{ row }"><ShotProductionInfo :shot="row.detail" layout="dialog" /><p v-if="row.detail.task.requirements">任务补充要求：{{ row.detail.task.requirements }}</p></template></el-table-column>
      <el-table-column label="镜头" width="145" show-overflow-tooltip><template #default="{ row }">{{ [row.episodeCode, row.sceneCode, row.shotCode].join(' / ') }}</template></el-table-column>
      <el-table-column label="制作内容" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.detail.description || row.description || '未填写' }}</template></el-table-column>
      <el-table-column label="制作人" width="80" show-overflow-tooltip><template #default="{ row }">{{ shotAssigneeName(row.detail.task.assignee || row.assignee, context.members) }}</template></el-table-column>
      <el-table-column label="计划起止时间" width="170"><template #default="{ row }">{{ row.detail.task.expectedStartTime ? `${formatTaskDateTime(row.detail.task.expectedStartTime)} 至 ${formatTaskDateTime(row.detail.task.expectedEndTime)}` : '尚未排期，请先设置排期' }}</template></el-table-column>
      <el-table-column v-if="context.canSchedule && needsSchedule" label="补齐排期" width="100"><template #default="{ row }"><el-button v-if="!hasSchedule(row)" link type="primary" :disabled="loading || saving || finished || row.blocked || Boolean(error)" @click="openSchedule([row])">{{ hasSchedule(row) ? '调整排期' : '设置排期' }}</el-button></template></el-table-column>
      <el-table-column v-if="saving || finished || error || scheduleError" label="开工结果" prop="result" min-width="130" show-overflow-tooltip />
    </el-table>
    <el-alert v-if="scheduleError" :title="scheduleError" type="warning" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="finished" :title="`已确认开工 ${successCount} / ${selected.length} 个镜头。关闭后刷新列表，其他项请核对状态后重新选择。`" :type="successCount === selected.length ? 'success' : 'warning'" :closable="false" show-icon />
    <el-form v-if="!scheduleOnly && !loading && !error && !finished" ref="formRef" :model="form" :rules="rules" label-position="top" class="batch-start-form" aria-label="批量镜头开工表单" :disabled="saving">
      <el-form-item label="统一任务优先级" prop="priority"><el-select v-model="form.priority"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
      <el-alert v-if="needsSchedule" type="warning" :closable="false" :title="context.canSchedule ? '所选任务包含未排期项，请使用上方或行内的设置排期；保存后可在此继续确认开工。' : '所选任务包含未排期项，请联系具备排期权限的管理人员，或明确选择仅已排期项开工。'" />
      <el-form-item prop="confirmed"><ElCheckbox v-model="form.confirmed">我已逐项在线下核对全部所选镜头的资产齐备，可以开工</ElCheckbox></el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="close">{{ finished || error || attempted ? '关闭并刷新' : '取消' }}</el-button>
      <template v-if="!scheduleOnly && !loading && !error && !finished"><el-button :icon="RefreshLeft" :disabled="saving" @click="reset">重置</el-button><el-button type="primary" :loading="saving" :disabled="saving || blockedSelection || needsSchedule || !selected.length" @click="submit">确认开工（{{ selected.length }} 项）</el-button></template>
    </template>
  </el-drawer>
  <el-dialog v-if="!scheduleOnly" v-model="scheduleVisible" :title="`设置排期 · ${scheduleTargets.length} 项任务`" width="min(620px, 95vw)" append-to-body :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" @update:model-value="value => { if (!value && context.single && !saving) close() }">
    <el-alert title="仅修改本次目标任务的计划时间，不会自动开工。逐项保存，成功项立即生效。" type="info" :closable="false" />
    <section class="batch-schedule-targets" aria-label="本次排期任务">
      <div class="batch-schedule-targets__heading"><strong>本次排期任务</strong><span>共 {{ scheduleTargets.length }} 项</span></div>
      <div class="batch-schedule-targets__list">
        <el-tag v-for="{ row } in scheduleTargets" :key="row.shotId" type="info" effect="plain" size="small">{{ [row.episodeCode, row.sceneCode, row.shotCode].join(' / ') }}</el-tag>
      </div>
    </section>
    <el-form ref="scheduleFormRef" :model="scheduleForm" :rules="scheduleRules" label-position="top" :disabled="saving">
      <el-form-item label="计划起止时间" prop="range"><ScheduleDateRangePicker v-model="scheduleForm.range" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" range-separator="至" style="width:100%" /></el-form-item>
      <el-form-item label="排期原因（选填）" prop="reason"><el-input v-model="scheduleForm.reason" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item>
    </el-form>
    <template #footer><el-button :disabled="saving" @click="scheduleVisible = false; if (context.single) close()">取消</el-button><el-button type="primary" :loading="saving" @click="saveSchedules">保存排期</el-button></template>
  </el-dialog>
</template>

<style scoped>
:global(.batch-start-drawer .el-drawer__body) { display: flex; flex-direction: column; }
:global(.batch-start-drawer .el-drawer__body > *) { flex-shrink: 0; }
:global(.batch-start-drawer .el-drawer__header) { padding-bottom: 16px; margin-bottom: 0; border-bottom: 1px solid var(--sg-border); }
:global(.batch-start-drawer .el-drawer__footer) { border-top: 1px solid var(--sg-border); }
:global(.batch-start-drawer .batch-start-table) { flex: 1 1 0; min-height: 180px; }

.batch-start-table { font-size: 12px; }
.batch-start-table :deep(.cell) { padding-left: 8px; padding-right: 8px; line-height: 1.6; }
.batch-start-table :deep(.el-button), .batch-start-table :deep(.el-table__expanded-cell) { font-size: 12px; }

.batch-schedule-drawer :deep(.el-drawer__header) { padding-bottom: 16px; margin-bottom: 0; border-bottom: 1px solid var(--sg-border); }
.batch-schedule-drawer :deep(.el-drawer__footer) { border-top: 1px solid var(--sg-border); padding-top: 16px; }
.batch-schedule-description { margin: 0 0 16px; color: var(--sg-text-muted); font-size: 12px; }

.batch-start-overview { display: flex; align-items: baseline; gap: 14px; margin: 18px 0 12px; }
.batch-start-overview span { color: var(--sg-text-muted); font-size: 12px; }
.batch-start-form{margin-top:20px}.batch-start-form :deep(.el-date-editor){width:100%;box-sizing:border-box}.batch-start-form :deep(.el-checkbox){height:auto;white-space:normal}.batch-start-form :deep(.el-checkbox__label){white-space:normal;line-height:1.6}.batch-start-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
.batch-schedule-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 16px; margin: 16px 0; padding: 14px 16px; background: var(--sg-surface-soft); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-sm); }
.batch-schedule-summary { display: flex; flex-direction: column; gap: 5px; font-size: 12px; }
.batch-schedule-summary strong { color: var(--sg-text); font-weight: 600; }
.batch-schedule-summary span { color: var(--sg-text-muted); }
.batch-schedule-buttons { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.batch-schedule-buttons :deep(.el-button + .el-button) { margin-left: 0; }
.batch-schedule-targets { margin: 16px 0 20px; padding: 14px 16px; background: var(--sg-surface-soft); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-sm); }
.batch-schedule-targets__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; font-size: 12px; color: var(--sg-text-muted); }
.batch-schedule-targets__heading strong { color: var(--sg-text-secondary); font-weight: 600; }
.batch-schedule-targets__list { display: flex; flex-wrap: wrap; gap: 8px; max-height: 120px; overflow-y: auto; }
.batch-schedule-targets__list :deep(.el-tag) { max-width: 100%; height: auto; min-height: 26px; padding: 4px 8px; white-space: normal; overflow-wrap: anywhere; line-height: 1.5; }
@media (max-width: 640px) {
  .batch-schedule-buttons { width: 100%; }
  .batch-schedule-buttons :deep(.el-button) { flex: 1 1 auto; }
}
:global(.batch-schedule-drawer .el-drawer__body) { display: flex; flex-direction: column; }
:global(.batch-schedule-drawer .el-drawer__body > *) { flex-shrink: 0; }
.inline-schedule-form { display: flex; flex-direction: column; flex: 1; min-height: 460px; margin-top: 16px; font-size: 12px; }
.inline-schedule-form > * { flex-shrink: 0; }
.inline-schedule-form > .el-table { flex: 1 1 0; min-height: 180px; }
.inline-schedule-form :deep(.el-table),
.inline-schedule-form :deep(.el-range-input),
.inline-schedule-form :deep(.el-range-separator) { font-size: 12px; }
.inline-schedule-form :deep(.el-table .cell) { padding-left: 8px; padding-right: 8px; }
.inline-schedule-form :deep(.el-range-editor) { padding-left: 8px; padding-right: 8px; }
.inline-schedule-original { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inline-schedule-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 14px; background: var(--sg-surface-soft); border: 1px solid var(--sg-border); border-radius: 8px; margin-bottom: 18px; }
.inline-schedule-toolbar > div:first-child { min-width: 100px; }
.inline-schedule-toolbar strong, .inline-schedule-toolbar small { display: block; }
.inline-schedule-toolbar small { margin-top: 5px; color: var(--sg-text-muted); }
.inline-schedule-toolbar :deep(.el-form-item) { flex: 1 1 340px; margin-bottom: 0; }
.inline-schedule-form :deep(.el-date-editor) { width: 100%; min-width: 0; box-sizing: border-box; }
.inline-schedule-form > .el-table { margin-bottom: 16px; }
.inline-schedule-form :deep(.el-table .el-form-item) { margin: 4px 0; }
.inline-schedule-form :deep(.el-form-item__error) { position: static; }
.inline-schedule-heading { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 10px; font-size: 12px; }
.inline-schedule-heading span, .inline-schedule-original { color: var(--sg-text-muted); font-size: 12px; }
.inline-schedule-summary { padding: 12px 14px; margin: 14px 0; background: var(--sg-surface-soft); border-radius: 8px; font-size: 12px; }
</style>
