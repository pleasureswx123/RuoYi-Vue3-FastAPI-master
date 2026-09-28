<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElCheckbox } from 'element-plus'
import { getShotDetail } from '@/api/shot-grid/shots'
import { startTask } from '@/api/shot-grid/tasks'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
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
const calendarDates = ref([])
// 与单个开工保持一致，选日期时默认使用未来五分钟和结束日 18 点。
const defaultTime = [new Date(Date.now() + 5 * 60 * 1000), new Date(2000, 0, 1, 18)]
const form = reactive({ priority: 'normal', expectedRange: [], confirmed: true })
let disposed = false
let attempted = false
onBeforeUnmount(() => { disposed = true })
const current = () => !disposed && context.validateContext()
const needsSchedule = computed(() => rows.value.some(row => !row.detail.task.expectedStartTime || !row.detail.task.expectedEndTime))
const successCount = computed(() => rows.value.filter(row => row.success).length)
const rules = {
  priority: [{ required: true, message: '请选择任务优先级', trigger: 'change' }],
  expectedRange: [{ validator: (_rule, value, callback) => {
    if (!needsSchedule.value) return callback()
    if (value?.length !== 2 || value.some(time => !time || Number.isNaN(new Date(time).getTime()))) return callback(new Error('请选择完整的预期制作时间'))
    if (new Date(value[0]).getTime() < Math.floor(Date.now() / 1000) * 1000) return callback(new Error('开始时间不能早于当前时间'))
    if (new Date(value[1]).getTime() <= new Date(value[0]).getTime()) return callback(new Error('结束时间必须晚于开始时间'))
    callback()
  }, trigger: 'change' }],
  confirmed: [{ validator: (_rule, value, callback) => value === true ? callback() : callback(new Error('请先确认全部镜头的开工条件')), trigger: 'change' }]
}


function disabledDate(date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}
function currentDay(role) {
  const index = role === 'end' ? 1 : 0
  const value = calendarDates.value[index] || form.expectedRange?.[index]
  return value && new Date(value).toDateString() === new Date().toDateString()
}
const before = length => Array.from({ length }, (_value, index) => index)
const disabledHours = role => currentDay(role) ? before(new Date().getHours()) : []
const disabledMinutes = (hour, role) => currentDay(role) && hour === new Date().getHours() ? before(new Date().getMinutes()) : []
const disabledSeconds = (hour, minute, role) => currentDay(role) && hour === new Date().getHours() && minute === new Date().getMinutes() ? before(new Date().getSeconds()) : []

onMounted(async () => {
  try {
    // 固定打开弹窗时的任务和锁号，详情只用于核对，不自动替换过期版本。
    for (const shot of context.shots) {
      if (!current()) return
      const { data: detail } = await getShotDetail(context.projectId, shot.shotId)
      if (!current()) return
      if (!detail?.allowedActions?.includes('task.start') || detail.task?.taskId !== shot.taskId ||
          detail.task.lockVersion !== shot.taskLockVersion || detail.lockVersion !== shot.lockVersion) {
        throw new Error(`${shot.shotCode} 的任务或制作信息已变化，请关闭并刷新后重新选择`)
      }
      rows.value.push({ ...shot, detail, result: '待确认', success: false })
    }
  } catch (failure) {
    if (!disposed) error.value = failure?.message || '镜头详情加载失败，请关闭后重试'
  } finally {
    if (!disposed) loading.value = false
  }
})

function close() {
  if (!saving.value) emit('close', { attempted })
}
function reset() {
  if (saving.value || finished.value) return
  formRef.value?.resetFields()
  calendarDates.value = []
}
async function submit() {
  if (loading.value || saving.value || finished.value || error.value) return
  saving.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false) || disposed) return
    if (!current()) { error.value = '项目或选中任务已变化，请关闭并重新选择'; return }
    for (const row of rows.value) {
      if (!current()) break
      row.result = '正在确认开工'
      attempted = true
      try {
        const hasSchedule = row.detail.task.expectedStartTime && row.detail.task.expectedEndTime
        const response = await startTask(row.taskId, {
          lockVersion: row.taskLockVersion, shotLockVersion: row.lockVersion, assetsConfirmed: true,
          priority: form.priority,
          ...(hasSchedule ? {} : { expectedStartTime: form.expectedRange[0], expectedEndTime: form.expectedRange[1] })
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
      rows.value.filter(row => row.result === '待确认').forEach(row => { row.result = '未执行，请刷新后重新选择' })
      finished.value = true
    }
  } finally { saving.value = false }
}
</script>

<template>
  <ProjectModal title="批量开始任务" :description="`已选择 ${context.shots.length} 个镜头，请逐项核对制作信息和负责人`" :busy="saving" wide @close="close">
    <el-alert title="逐个确认开工，成功项立即生效；失败项不会撤销已成功任务。已有排期保持不变。" type="info" :closable="false" show-icon />
    <el-table v-loading="loading" :data="rows" row-key="shotId" max-height="320" empty-text="正在读取镜头详情">
      <el-table-column type="expand"><template #default="{ row }"><ShotProductionInfo :shot="row.detail" layout="dialog" /><p v-if="row.detail.task.requirements">任务补充要求：{{ row.detail.task.requirements }}</p></template></el-table-column>
      <el-table-column label="镜头" min-width="155"><template #default="{ row }">{{ [row.episodeCode, row.sceneCode, row.shotCode].join(' / ') }}</template></el-table-column>
      <el-table-column label="制作人" min-width="90"><template #default="{ row }">{{ shotAssigneeName(row.detail.task.assignee || row.assignee, context.members) }}</template></el-table-column>
      <el-table-column label="已有排期" min-width="170"><template #default="{ row }">{{ row.detail.task.expectedStartTime ? `${formatTaskDateTime(row.detail.task.expectedStartTime)} 至 ${formatTaskDateTime(row.detail.task.expectedEndTime)}` : '使用下方统一时间' }}</template></el-table-column>
      <el-table-column label="执行结果" prop="result" min-width="180" />
    </el-table>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="finished" :title="`已确认开工 ${successCount} / ${rows.length} 个镜头。关闭后刷新列表，其他项请核对状态后重新选择。`" :type="successCount === rows.length ? 'success' : 'warning'" :closable="false" show-icon />
    <el-form v-if="!loading && !error && !finished" ref="formRef" :model="form" :rules="rules" label-position="top" class="batch-start-form" aria-label="批量镜头开工表单" :disabled="saving">
      <el-form-item label="统一任务优先级" prop="priority"><el-select v-model="form.priority"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
      <el-form-item v-if="needsSchedule" label="未排期任务的预期制作时间" prop="expectedRange"><el-date-picker v-model="form.expectedRange" type="datetimerange" range-separator="至" start-placeholder="预期开始时间" end-placeholder="预期结束时间" value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm:ss" :default-time="defaultTime" :disabled-date="disabledDate" :disabled-hours="disabledHours" :disabled-minutes="disabledMinutes" :disabled-seconds="disabledSeconds" @calendar-change="dates => calendarDates = dates" /></el-form-item>
      <el-form-item prop="confirmed"><ElCheckbox v-model="form.confirmed">我已逐项在线下核对全部所选镜头的资产齐备，可以开工</ElCheckbox></el-form-item>
    </el-form>
    <footer class="batch-start-actions">
      <el-button :disabled="saving" @click="close">{{ finished || error ? '关闭并刷新' : '取消' }}</el-button>
      <template v-if="!loading && !error && !finished"><el-button :disabled="saving" @click="reset">重置</el-button><el-button type="primary" :loading="saving" :disabled="saving" @click="submit">确认批量开工</el-button></template>
    </footer>
  </ProjectModal>
</template>

<style scoped>
.batch-start-form{margin-top:20px}.batch-start-form :deep(.el-date-editor){width:100%;box-sizing:border-box}.batch-start-form :deep(.el-checkbox){height:auto;white-space:normal}.batch-start-form :deep(.el-checkbox__label){white-space:normal;line-height:1.6}.batch-start-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
</style>
