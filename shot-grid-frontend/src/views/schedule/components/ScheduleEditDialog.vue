<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { scheduleErrorState, scheduleTaskLabel } from '@/views/schedule/schedulePresentation'

const props = defineProps({
  visible: Boolean,
  task: { type: Object, default: null },
  draft: { type: Object, default: null },
  saving: Boolean,
  conflictTaskIds: { type: Array, default: () => [] },
  error: { type: Object, default: null }
})

const emit = defineEmits(['update:visible', 'submit', 'cancel'])
const formRef = ref(null)
const form = reactive({ expectedRange: [], changeReason: '', overlapAcknowledged: false })
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
      if (new Date(value[1]).getTime() <= new Date(value[0]).getTime()) {
        callback(new Error('结束时间必须晚于开始时间'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  changeReason: [
    { required: true, message: '请填写本次排期原因', trigger: 'blur' },
    { min: 1, max: 500, message: '排期原因不能超过 500 个字符', trigger: 'blur' }
  ],
  overlapAcknowledged: [{
    validator: (_rule, value, callback) => {
      if (props.conflictTaskIds.length && !value) {
        callback(new Error('请确认已查看本次重叠任务'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}

watch(() => [props.visible, props.task?.taskId, props.draft], ([visible]) => {
  if (!visible) return
  form.expectedRange = props.draft?.expectedStartTime && props.draft?.expectedEndTime
    ? [props.draft.expectedStartTime, props.draft.expectedEndTime]
    : []
  form.changeReason = props.draft?.changeReason || ''
  form.overlapAcknowledged = false
  formRef.value?.clearValidate()
}, { immediate: true })

watch(() => props.conflictTaskIds, () => {
  form.overlapAcknowledged = false
  formRef.value?.clearValidate('overlapAcknowledged')
})

async function submit() {
  if (props.saving) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('submit', {
    expectedStartTime: form.expectedRange[0],
    expectedEndTime: form.expectedRange[1],
    operationSource: props.draft?.operationSource || 'dialog',
    changeReason: form.changeReason.trim(),
    overlapAcknowledged: form.overlapAcknowledged
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
    :title="task ? `调整排期 · ${scheduleTaskLabel(task)}` : '安排任务时间'"
    width="620px"
    append-to-body
    destroy-on-close
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="formRef?.resetFields()"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="schedule-edit-form">
      <el-alert type="info" :closable="false" show-icon title="只调整完整时间范围，不改变负责人、任务状态或首版基线。" />
      <el-form-item label="开始与结束时间" prop="expectedRange">
        <el-date-picker
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
      <el-form-item label="排期原因" prop="changeReason">
        <el-input v-model="form.changeReason" type="textarea" :rows="3" maxlength="500" show-word-limit :disabled="saving" placeholder="说明为什么安排或调整这段制作时间" />
      </el-form-item>
      <el-alert
        v-if="conflictTaskIds.length"
        type="error"
        :closable="false"
        show-icon
        title="保存前请二次确认人员时间重叠"
        :description="`冲突任务 ID：${conflictTaskIds.join('、')}。系统不会自动改派或压缩任务。`"
      />
      <el-form-item v-if="conflictTaskIds.length" prop="overlapAcknowledged">
        <el-checkbox v-model="form.overlapAcknowledged" :disabled="saving">我已查看本次完整冲突清单，仍要保存该排期</el-checkbox>
      </el-form-item>
      <el-alert v-if="errorState && !conflictTaskIds.length" type="error" :closable="false" show-icon :title="errorState.title" :description="`${errorState.message} · ${errorState.action}`" />
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="cancel">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="saving" @click="submit">保存排期</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.schedule-edit-form { display: grid; gap: 16px; }
.schedule-edit-form:deep(.el-form-item) { margin-bottom: 0; }
.schedule-edit-form:deep(.el-date-editor) { width: 100%; box-sizing: border-box; }
</style>
