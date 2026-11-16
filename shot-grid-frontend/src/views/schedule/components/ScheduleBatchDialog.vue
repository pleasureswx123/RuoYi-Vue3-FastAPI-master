<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useLeaveProtection } from '@/composables/useLeaveProtection'
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { createIdempotencyState } from '@/utils/idempotency'
import { scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { formatTaskDateTime, taskStatusMeta } from '@/views/task/taskPresentation'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close'])
// 固定打开时的身份与版本；保存前不偷偷替换锁号或扩大选择范围。
const context = props.context
const formRef = ref(null)
const tableRef = ref(null)
const selected = ref([])
const saving = ref(false)
const attempted = ref(false)
const error = ref('')
const form = reactive({ commonRange: [], reason: '', rows: context.tasks.map(task => ({
  ...task, range: task.currentStart && task.currentEnd ? [task.currentStart, task.currentEnd] : [],
  result: '', saved: false, requestKey: createIdempotencyState(`schedule-batch:${task.taskId}`)
})) })
let disposed = false
onBeforeUnmount(() => { disposed = true })
const current = () => !disposed && context.validateContext()
const eligible = row => Number(row.projectId) === Number(context.projectId)
  && Number.isSafeInteger(row.taskId) && row.taskId > 0 && Number.isSafeInteger(row.lockVersion) && row.lockVersion >= 0
  && row.taskStatus !== 'completed' && row.allowedActions?.includes('schedule')
const selectable = row => !saving.value && !attempted.value && current() && eligible(row)
const unchanged = row => row.range.length === 2 && row.range.every((value, i) =>
  new Date(value).getTime() === new Date([row.currentStart, row.currentEnd][i]).getTime())
const selectedIds = computed(() => new Set(selected.value.map(row => row.taskId)))
const changedCount = computed(() => selected.value.filter(row => !unchanged(row)).length)
const savedCount = computed(() => form.rows.filter(row => row.saved).length)
const dirty = computed(() => !attempted.value && (form.reason.trim() || form.commonRange.length || form.rows.some(row => row.range.length && !unchanged(row))))
const disabled = computed(() => saving.value || attempted.value || !current())
const rangeRules = [{ validator: (_rule, value, done) => {
  const valid = Array.isArray(value) && value.length === 2 && value.every(time => time && Number.isFinite(new Date(time).getTime())) && new Date(value[1]) > new Date(value[0])
  done(valid ? undefined : new Error('请选择完整周期，结束时间须晚于开始时间'))
}, trigger: 'change' }]
const reasonRules = [{ max: 500, message: '调整说明不能超过 500 字', trigger: 'blur' }]

async function canLeave() {
  if (saving.value) { ElMessage.info('正在保存制作周期，请稍候'); return false }
  if (!dirty.value) return true
  try { await ElMessageBox.confirm('有尚未保存的制作周期，确定放弃本次修改吗？', '离开批量修改', { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' }); return true } catch { return false }
}
useLeaveProtection(canLeave, () => Boolean(dirty.value || saving.value))
async function close() {
  if (await canLeave()) emit('close', { attempted: attempted.value, savedCount: savedCount.value })
}
async function beforeClose(done) { if (await canLeave()) { emit('close', { attempted: attempted.value, savedCount: savedCount.value }); done() } }
async function applyCommon() {
  if (disabled.value || !selected.value.length || selected.value.length > 100) return
  if (!await formRef.value.validateField('commonRange').catch(() => false) || disabled.value) return
  selected.value.forEach(row => { row.range = [...form.commonRange] })
  formRef.value.clearValidate()
}
function clearSelection() { if (!disabled.value) tableRef.value?.clearSelection() }
async function save() {
  if (disabled.value || !selected.value.length || selected.value.length > 100 || !changedCount.value) return
  const targets = [...selected.value]
  saving.value = true
  error.value = ''
  try {
    const fields = ['reason', ...targets.map(row => `rows.${form.rows.indexOf(row)}.range`)]
    if (!await formRef.value.validateField(fields).catch(() => false)) return
    if (!current() || targets.some(row => !eligible(row))) { error.value = '项目、筛选或权限已变化，请关闭后重新选择'; return }
    for (const row of targets) {
      if (!current()) { error.value = '页面范围已变化，已停止后续保存'; break }
      if (unchanged(row)) { row.result = '未改动，已跳过'; continue }
      const command = { lockVersion: row.lockVersion, expectedStartTime: row.range[0], expectedEndTime: row.range[1], changeReason: form.reason.trim(), operationSource: 'dialog' }
      row.result = '正在保存'
      attempted.value = true
      try {
        const response = await updateTaskSchedule(row.taskId, command, row.requestKey.forPayload(command))
        if (disposed) return
        const saved = response?.data ?? response
        if (Number(saved?.taskId) !== row.taskId || Number(saved?.projectId) !== Number(context.projectId)
          || !Number.isSafeInteger(saved.lockVersion) || saved.lockVersion <= row.lockVersion
          || new Date(saved.currentStart).getTime() !== new Date(command.expectedStartTime).getTime()
          || new Date(saved.currentEnd).getTime() !== new Date(command.expectedEndTime).getTime()) throw new Error('返回结果不完整，请刷新核对')
        row.saved = true
        row.result = '已保存'
      } catch (failure) {
        if (disposed) return
        row.result = failure?.message || '保存结果未确认，请刷新核对'
        error.value = '保存已暂停，请查看逐项结果。已成功保存的项目会保留，其余项目未继续提交；关闭后刷新核对。'
        break
      }
    }
    if (disposed) return
    if (error.value) targets.filter(row => !row.result).forEach(row => { row.result = '未执行' })
    else {
      ElMessage.success(`已修改 ${savedCount.value} 项制作周期`)
      emit('close', { attempted: attempted.value, savedCount: savedCount.value })
    }
  } finally { if (!disposed) saving.value = false }
}
</script>

<template>
  <el-drawer :model-value="true" title="批量修改制作周期" size="min(1120px, 96vw)" append-to-body :before-close="beforeClose" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving">
    <p class="schedule-batch__hint">显示当前排期及已加载的未设周期任务。勾选后可统一设置时间，也可逐项填写；仅保存勾选项，每次最多 100 项。调整周期不会改变制作人、任务状态或最初排期。</p>
    <el-alert v-if="!current()" title="项目、筛选或权限已变化，请关闭后重新选择" type="warning" :closable="false" />
    <el-form ref="formRef" :model="form" :disabled="disabled" label-position="top" aria-label="批量制作周期表单">
      <div class="schedule-batch__common">
        <el-form-item label="统一制作周期" prop="commonRange" :rules="rangeRules"><ScheduleDateRangePicker v-model="form.commonRange" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm" start-placeholder="开始时间" end-placeholder="结束时间" aria-label="统一制作周期" /></el-form-item>
        <el-button type="primary" :disabled="disabled || !selected.length || selected.length > 100" @click="applyCommon">应用到勾选项</el-button>
        <el-button :disabled="disabled || !selected.length" @click="clearSelection">清空选择</el-button>
      </div>
      <el-alert v-if="selected.length > 100" title="每次最多修改 100 项，请减少勾选" type="warning" :closable="false" />
      <el-table ref="tableRef" :data="form.rows" row-key="taskId" :max-height="440" size="small" @selection-change="value => { selected = value }" empty-text="当前筛选没有任务">
        <el-table-column type="selection" width="44" :selectable="selectable" />
        <el-table-column label="镜头 / 资产分项" min-width="210"><template #default="{ row }"><strong>{{ scheduleTaskLabel(row) }}</strong><small v-if="!eligible(row)" class="schedule-batch__readonly">{{ row.taskStatus === 'completed' ? '已通过，不能修改周期' : '当前无排期修改权限' }}</small></template></el-table-column>
        <el-table-column label="制作人" width="110"><template #default="{ row }">{{ row.assignee?.userName || '—' }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }">{{ taskStatusMeta(row).label }}</template></el-table-column>
        <el-table-column label="制作周期" min-width="345"><template #default="{ row, $index }">
          <el-form-item v-if="selectedIds.has(row.taskId)" :prop="`rows.${$index}.range`" :rules="rangeRules"><ScheduleDateRangePicker v-model="row.range" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm" start-placeholder="开始时间" end-placeholder="结束时间" :aria-label="`${scheduleTaskLabel(row)} 制作周期`" /></el-form-item>
          <small>{{ row.currentStart && row.currentEnd ? `原：${formatTaskDateTime(row.currentStart)} 至 ${formatTaskDateTime(row.currentEnd)}` : '尚未设置制作周期' }}</small>
        </template></el-table-column>
        <el-table-column v-if="attempted" label="保存结果" min-width="160"><template #default="{ row }"><el-text :type="row.saved ? 'success' : 'warning'">{{ row.result || '未选择' }}</el-text></template></el-table-column>
      </el-table>
      <el-form-item class="schedule-batch__reason" label="调整说明（选填）" prop="reason" :rules="reasonRules"><el-input v-model="form.reason" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="可补充本次调整原因" /></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template #footer><div class="schedule-batch__footer"><el-text size="small">已选 {{ selected.length }} 项 · 修改 {{ changedCount }} 项<template v-if="attempted"> · 已保存 {{ savedCount }} 项</template></el-text><div><el-button :disabled="saving" @click="close">{{ attempted ? '关闭并刷新' : '取消' }}</el-button><el-button type="primary" :loading="saving" :disabled="disabled || !changedCount || selected.length > 100" @click="save">保存勾选项</el-button></div></div></template>
  </el-drawer>
</template>

<style scoped>
.schedule-batch__hint,.schedule-batch__readonly { color: var(--sg-text-muted); font-size: 12px; line-height: 1.6; }
.schedule-batch__readonly { display: block; }
.schedule-batch__common,.schedule-batch__footer { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.schedule-batch__common { align-items: flex-end; margin: 16px 0; }
.schedule-batch__common .el-form-item { flex: 1 1 340px; max-width: 540px; margin-bottom: 0; }
.schedule-batch__footer { justify-content: space-between; }
.schedule-batch__reason { margin-top: 16px; }
.el-table :deep(.el-form-item) { margin-bottom: 16px; margin-top: 6px; }
</style>
