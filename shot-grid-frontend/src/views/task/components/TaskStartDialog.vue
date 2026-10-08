<script setup>
import { createIdempotencyState } from '@/utils/idempotency'
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { ElCheckbox } from 'element-plus'
import { formatTaskDateTime } from '@/views/task/taskPresentation'
import ScheduleEditDialog from '@/views/schedule/components/ScheduleEditDialog.vue'
import { updateTaskSchedule } from '@/api/shot-grid/schedules'
import { startTask } from '@/api/shot-grid/tasks'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'
import AssetProductionInfo from '@/views/asset/components/AssetProductionInfo.vue'

const props = defineProps({ context: { type: Object, required: true } })
const emit = defineEmits(['close', 'started', 'failed'])
const context = props.context
const formRef = ref(null)
const saving = ref(false)
const error = ref('')
const scheduleVisible = ref(false)
const scheduleSaving = ref(false)
const scheduleError = ref(null)
const taskVersion = ref(context.command.lockVersion)
let scheduleKey = ''
const scheduleTask = computed(() => ({
  ...context.task, taskId: context.taskId,
  projectId: context.shot?.projectId || context.asset?.projectId,
  taskName: context.name,
  target: context.shot ? { targetKind: 'shot', targetId: context.shot.shotId }
    : { targetKind: 'asset_item', targetId: context.item?.assetItemId, parentId: context.asset?.assetId },
  assignee: { userName: context.assigneeName }, lockVersion: taskVersion.value,
  currentStart: form.expectedRange[0], currentEnd: form.expectedRange[1]
}))
const scheduleDraft = computed(() => ({ expectedStartTime: form.expectedRange[0], expectedEndTime: form.expectedRange[1] }))
function openSchedule() {
  if (saving.value || !context.canSchedule || !context.validateContext()) return
  scheduleError.value = null
  scheduleKey = createIdempotencyState(`start-schedule:${context.taskId}`).forPayload({ taskId: context.taskId })
  scheduleVisible.value = true
}
async function saveSchedule(command) {
  if (scheduleSaving.value || disposed || !context.validateContext()) return
  scheduleSaving.value = true
  try {
    const { data } = await updateTaskSchedule(context.taskId, { ...command, lockVersion: taskVersion.value }, scheduleKey)
    if (disposed || !context.validateContext()) return
    if (Number(data?.taskId) !== Number(context.taskId) || !Number.isInteger(data?.lockVersion)) throw new Error('排期响应不完整，请关闭并刷新后核对')
    taskVersion.value = data.lockVersion
    form.expectedRange = [data.currentStart, data.currentEnd]
    context.onScheduleSaved?.(data)
    scheduleVisible.value = false
    formRef.value?.clearValidate('expectedRange')
  } catch (failure) {
    if (!disposed) scheduleError.value = failure
  } finally { scheduleSaving.value = false }
}
let disposed = false
onBeforeUnmount(() => { disposed = true })
const form = reactive({
  priority: context.task?.priority || 'normal',
  expectedRange: context.task?.expectedStartTime && context.task?.expectedEndTime
    ? [context.task.expectedStartTime, context.task.expectedEndTime] : [],
  confirmed: true
})
const isShot = Boolean(context.shot)
const hasExistingSchedule = computed(() => form.expectedRange.length === 2 && form.expectedRange.every(Boolean))
const confirmation = isShot ? '我已在线下核对该镜头所需资产齐备，可以开工' : '我已确认该制作分项的线下制作条件齐备，可以开工'
const rules = {
  priority: [{ required: true, message: '请选择任务优先级', trigger: 'change' }],
  expectedRange: [{ validator: (_rule, value, callback) => {
    if (!Array.isArray(value) || value.length !== 2 || value.some(time => !time || Number.isNaN(new Date(time).getTime()))) {
      return callback(new Error('请先设置并保存计划起止时间'))
    }
    if (new Date(value[1]).getTime() <= new Date(value[0]).getTime()) return callback(new Error('结束时间必须晚于开始时间'))
    callback()
  }, trigger: 'change' }],
  confirmed: [{ validator: (_rule, value, callback) => value ? callback() : callback(new Error('请先确认开工条件')), trigger: 'change' }]
}
const legacyDue = computed(() => !context.task?.expectedEndTime && context.task?.dueDate ? context.task.dueDate : '')

async function submit() {
  if (saving.value || scheduleVisible.value || scheduleSaving.value || !hasExistingSchedule.value) return
  // 验证也处于忙碌区间，避免连续点击重复进入异步验证。
  saving.value = true
  error.value = ''
  try {
    if (!await formRef.value?.validate().catch(() => false) || disposed) return
    if (!context.validateContext()) {
      emit('failed', { httpStatus: 409, message: '制作对象或任务已发生变化，请刷新后重新确认开工。' })
      return
    }
    const response = await startTask(context.taskId, {
      ...context.command,
      priority: form.priority,
      lockVersion: taskVersion.value
    })
    if (!disposed) emit('started', response)
  } catch (failure) {
    if (disposed) return
    if ([401, 403, 404, 409].includes(Number(failure?.httpStatus || failure?.status))) emit('failed', failure)
    else error.value = failure?.message || '确认开工失败，请重试'
  } finally { saving.value = false }
}
</script>

<template>
  <ProjectModal :title="isShot ? '确认镜头开工' : '确认分项开工'" :description="context.name" :busy="saving || scheduleSaving" wide @close="emit('close')">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="task-start-form" aria-label="任务开工表单">
      <el-descriptions :column="1" border><el-descriptions-item label="制作人">{{ context.assigneeName }}</el-descriptions-item></el-descriptions>
      <section class="task-start-form__content" aria-label="完整制作信息">
        <ShotProductionInfo v-if="isShot" :shot="context.shot" layout="dialog" />
        <AssetProductionInfo v-else :asset="context.asset" :item="context.item" />
        <p v-if="context.task?.requirements" class="task-start-form__requirements">任务补充要求：{{ context.task.requirements }}</p>
      </section>
      <el-form-item label="任务优先级" prop="priority"><el-select v-model="form.priority" :disabled="saving"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
      <el-form-item label="计划起止时间" prop="expectedRange">
        <span v-if="hasExistingSchedule" class="task-start-form__schedule">{{ formatTaskDateTime(form.expectedRange[0]) }} 至 {{ formatTaskDateTime(form.expectedRange[1]) }}</span>
        <template v-else>
          <span>尚未排期，请先保存计划起止时间。</span>
          <small v-if="legacyDue">原截止日期：{{ legacyDue }}</small>
          <el-button v-if="context.canSchedule" type="primary" link :disabled="saving || scheduleSaving" @click="openSchedule">设置排期</el-button>
          <small v-else>请联系具备排期权限的管理人员设置排期。</small>
        </template>
      </el-form-item>
      <el-form-item prop="confirmed"><ElCheckbox v-model="form.confirmed" :disabled="saving">{{ confirmation }}</ElCheckbox></el-form-item>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <footer><el-button :disabled="saving || scheduleSaving" @click="emit('close')">暂不开工</el-button><el-button type="primary" :loading="saving" :disabled="saving || !hasExistingSchedule || scheduleVisible" @click="submit">确认开工</el-button></footer>
    </el-form>
  </ProjectModal>
  <ScheduleEditDialog v-model:visible="scheduleVisible" :task="scheduleTask" :draft="scheduleDraft" :saving="scheduleSaving" :error="scheduleError" @save-request="saveSchedule" @cancel="scheduleVisible = false" />
</template>

<style scoped>
.task-start-form__schedule { font-size: 12px; color: var(--sg-text); }
.task-start-form{display:grid;gap:18px}.task-start-form :deep(.el-form-item){margin-bottom:0}.task-start-form :deep(.el-date-editor){width:100%;box-sizing:border-box}.task-start-form__content{max-height:32vh;overflow:auto}.task-start-form__requirements{white-space:pre-wrap;overflow-wrap:anywhere}.task-start-form small{margin:0;color:var(--sg-text-secondary);font-size:12px;line-height:1.7}.task-start-form :deep(.el-checkbox){height:auto;white-space:normal}.task-start-form :deep(.el-checkbox__label){white-space:normal;line-height:1.6}.task-start-form footer{display:flex;justify-content:flex-end;gap:10px}
</style>
