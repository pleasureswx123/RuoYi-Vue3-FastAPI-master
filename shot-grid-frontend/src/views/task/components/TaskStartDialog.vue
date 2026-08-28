<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { ElCheckbox } from 'element-plus'
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
const calendarDates = ref([])
let disposed = false
onBeforeUnmount(() => { disposed = true })
const form = reactive({
  priority: context.task?.priority || 'normal',
  expectedRange: context.task?.expectedStartTime && context.task?.expectedEndTime
    ? [context.task.expectedStartTime, context.task.expectedEndTime] : [],
  confirmed: true
})
const isShot = Boolean(context.shot)
const confirmation = isShot ? '我已在线下核对该镜头所需资产齐备，可以开工' : '我已确认该制作分项的线下制作条件齐备，可以开工'
const defaultTime = [new Date(Date.now() + 5 * 60 * 1000), new Date(2000, 0, 1, 18)]
const rules = {
  priority: [{ required: true, message: '请选择任务优先级', trigger: 'change' }],
  expectedRange: [{ validator: (_rule, value, callback) => {
    if (!Array.isArray(value) || value.length !== 2 || value.some(time => !time || Number.isNaN(new Date(time).getTime()))) {
      return callback(new Error('请选择完整的预期开始与结束时间'))
    }
    if (new Date(value[0]).getTime() < Math.floor(Date.now() / 1000) * 1000) return callback(new Error('开始时间不能早于当前时间，请重新选择'))
    if (new Date(value[1]).getTime() <= new Date(value[0]).getTime()) return callback(new Error('结束时间必须晚于开始时间'))
    callback()
  }, trigger: 'change' }],
  confirmed: [{ validator: (_rule, value, callback) => value ? callback() : callback(new Error('请先确认开工条件')), trigger: 'change' }]
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
const legacyDue = computed(() => !context.task?.expectedEndTime && context.task?.dueDate ? context.task.dueDate : '')

async function submit() {
  if (saving.value) return
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
      ...context.command, priority: form.priority,
      expectedStartTime: form.expectedRange[0], expectedEndTime: form.expectedRange[1]
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
  <ProjectModal :title="isShot ? '确认镜头开工' : '确认分项开工'" :description="context.name" :busy="saving" wide @close="emit('close')">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="task-start-form" aria-label="任务开工表单">
      <el-descriptions :column="1" border><el-descriptions-item label="制作人">{{ context.assigneeName }}</el-descriptions-item></el-descriptions>
      <section class="task-start-form__content" aria-label="完整制作信息">
        <ShotProductionInfo v-if="isShot" :shot="context.shot" layout="dialog" />
        <AssetProductionInfo v-else :asset="context.asset" :item="context.item" />
        <p v-if="context.task?.requirements" class="task-start-form__requirements">任务补充要求：{{ context.task.requirements }}</p>
      </section>
      <el-form-item label="任务优先级" prop="priority"><el-select v-model="form.priority" :disabled="saving"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
      <el-form-item label="预期制作时间" prop="expectedRange">
        <el-date-picker v-model="form.expectedRange" type="datetimerange" range-separator="至" start-placeholder="预期开始时间" end-placeholder="预期结束时间" value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm:ss" :default-time="defaultTime" :disabled-date="disabledDate" :disabled-hours="disabledHours" :disabled-minutes="disabledMinutes" :disabled-seconds="disabledSeconds" :disabled="saving" @calendar-change="dates => calendarDates = dates" />
        <small v-if="legacyDue">原截止日期：{{ legacyDue }}，请在本次开工时确认完整时间范围。</small>
      </el-form-item>
      <el-form-item prop="confirmed"><ElCheckbox v-model="form.confirmed" :disabled="saving">{{ confirmation }}</ElCheckbox></el-form-item>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <footer><el-button :disabled="saving" @click="emit('close')">暂不开工</el-button><el-button type="primary" :loading="saving" :disabled="saving" @click="submit">确认开工</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.task-start-form{display:grid;gap:18px}.task-start-form :deep(.el-form-item){margin-bottom:0}.task-start-form :deep(.el-date-editor){width:100%;box-sizing:border-box}.task-start-form__content{max-height:32vh;overflow:auto}.task-start-form__requirements{white-space:pre-wrap;overflow-wrap:anywhere}.task-start-form small{margin:0;color:var(--sg-text-secondary);font-size:12px;line-height:1.7}.task-start-form :deep(.el-checkbox){height:auto;white-space:normal}.task-start-form :deep(.el-checkbox__label){white-space:normal;line-height:1.6}.task-start-form footer{display:flex;justify-content:flex-end;gap:10px}
</style>
