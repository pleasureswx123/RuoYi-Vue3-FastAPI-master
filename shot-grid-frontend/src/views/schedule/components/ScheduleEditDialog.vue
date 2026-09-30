<script setup>
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'
import ScheduleMilestones from './ScheduleMilestones.vue'
import { scheduleDateWarnings } from '@/views/schedule/scheduleMilestones'
import { computed, reactive, ref, watch } from 'vue'

import { scheduleErrorState, scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { formatTaskDateTime } from '@/views/task/taskPresentation'

const props = defineProps({
  visible: Boolean,
  task: { type: Object, default: null },
  draft: { type: Object, default: null },
  saving: Boolean,
  error: { type: Object, default: null }
})

const emit = defineEmits(['update:visible', 'save-request', 'cancel'])
const formRef = ref(null)
const milestones = ref(null)
const isInitialSchedule = computed(() => !props.task?.currentStart || !props.task?.currentEnd)
const scheduleTitle = computed(() => isInitialSchedule.value ? '设置排期' : '调整排期')
const unchanged = computed(() => new Date(form.expectedRange[0]).getTime() === new Date(props.task?.currentStart).getTime() && new Date(form.expectedRange[1]).getTime() === new Date(props.task?.currentEnd).getTime())
const warnings = computed(() => scheduleDateWarnings(props.task, form.expectedRange, milestones.value))
const form = reactive({ expectedRange: [], changeReason: '' })
const dialogVisible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value)
})
const errorState = computed(() => props.error ? scheduleErrorState(props.error) : null)
const rules = {
  expectedRange: [{
    validator: (_rule, value, callback) => {
      if (!Array.isArray(value) || value.length !== 2 || value.some(item => !item)) {
        callback(new Error('请选择完整的开始和结束时间'))
        return
      }
      if (value.some(item => !Number.isFinite(new Date(item).getTime())) || new Date(value[1]).getTime() <= new Date(value[0]).getTime()) {
        callback(new Error('结束时间必须晚于开始时间'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  changeReason: [
    { max: 500, message: '排期原因不能超过 500 个字符', trigger: 'blur' }
  ]
}

watch(() => [props.visible, props.task?.taskId, props.draft], ([visible]) => {
  if (!visible) return
  form.expectedRange = props.draft?.expectedStartTime && props.draft?.expectedEndTime
    ? [props.draft.expectedStartTime, props.draft.expectedEndTime]
    : []
  form.changeReason = props.draft?.changeReason || ''
  formRef.value?.clearValidate()
}, { immediate: true })

async function submit() {
  if (props.saving || unchanged.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('save-request', {
    expectedStartTime: form.expectedRange[0],
    expectedEndTime: form.expectedRange[1],
    operationSource: props.draft?.operationSource || 'dialog',
    changeReason: form.changeReason.trim()
  })
}

function cancel() {
  if (props.saving) return
  emit('cancel')
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    class="schedule-edit-dialog"
    :title="task ? `${scheduleTitle} · ${scheduleTaskLabel(task)}` : scheduleTitle"
    width="min(980px, 95vw)"
    append-to-body
    destroy-on-close
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="formRef?.resetFields()"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="schedule-edit-form">
      <el-alert type="info" :closable="false" show-icon :title="isInitialSchedule ? '先设置计划开始与结束时间。保存排期不会自动开工，待开工任务仍需管理人员确认开工。' : '调整的是计划时间，不会修改实际开工、提交或审核记录，也不会覆盖最初排期。'" />
      <el-card v-if="task" shadow="never" class="schedule-edit-form__panel">
        <template #header><h4>排期对照</h4></template>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="负责人">{{ task.assignee?.userName || '—' }}</el-descriptions-item>
        <el-descriptions-item label="原排期">{{ formatTaskDateTime(task.currentStart) }} 至 {{ formatTaskDateTime(task.currentEnd) }}</el-descriptions-item>
        <el-descriptions-item label="拟调整为">{{ formatTaskDateTime(form.expectedRange[0]) }} 至 {{ formatTaskDateTime(form.expectedRange[1]) }}</el-descriptions-item>
      </el-descriptions>
      </el-card>
      <div class="schedule-edit-form__workspace">
        <el-card shadow="never" class="schedule-edit-form__panel schedule-edit-form__history-panel">
          <div class="schedule-edit-form__history">
          <ScheduleMilestones :task="task" :active="visible" @loaded="milestones = $event" />
          </div>
        </el-card>
        <el-card shadow="never" class="schedule-edit-form__panel schedule-edit-form__edit-panel">
          <template #header><h4>{{ scheduleTitle }}</h4></template>
        <div class="schedule-edit-form__fields">
      <el-alert v-for="message in warnings" :key="message" type="warning" :closable="false" :title="message" />
      <el-alert v-if="unchanged" type="info" :closable="false" title="排期未变更，请调整时间后再保存。" />
      <el-form-item label="计划起止时间" prop="expectedRange">
        <ScheduleDateRangePicker
          v-model="form.expectedRange"
          type="datetimerange"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm:ss"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          :disabled="saving"
        />
      </el-form-item>
      <el-form-item label="排期原因（选填）" prop="changeReason">
        <el-input v-model="form.changeReason" type="textarea" :rows="3" maxlength="500" show-word-limit :disabled="saving" placeholder="可补充排期说明，也可以直接保存" />
      </el-form-item>
      <el-alert v-if="errorState" type="error" :closable="false" show-icon :title="errorState.title" :description="`${errorState.message} · ${errorState.action}`" />
        </div>
        </el-card>
      </div>
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="cancel">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="saving || unchanged" @click="submit">保存排期</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.schedule-edit-form { display: grid; gap: 16px; }
.schedule-edit-form__workspace { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 16px; align-items: stretch; }
.schedule-edit-form__panel { min-width: 0; border-radius: 10px; --el-card-padding: 16px; }
.schedule-edit-form__panel :deep(.el-card__header) { padding: 12px 16px; background: var(--el-fill-color-light); }
.schedule-edit-form__panel h4 { margin: 0; font-size: 14px; line-height: 20px; font-weight: 600; }
.schedule-edit-form__history-panel { background: var(--el-fill-color-light); }
.schedule-edit-form__edit-panel { border-color: var(--el-color-primary-light-7); }
.schedule-edit-form__history { min-width: 0; max-height: 48vh; overflow-y: auto; }
.schedule-edit-form__fields { display: grid; gap: 16px; min-width: 0; }
.schedule-edit-form:deep(.el-form-item) { margin-bottom: 0; }
.schedule-edit-form:deep(.el-date-editor) { width: 100%; box-sizing: border-box; }
@media (max-width: 760px) {
  .schedule-edit-form__workspace { grid-template-columns: minmax(0, 1fr); }
  .schedule-edit-form__history { max-height: 30vh; }
}
</style>
