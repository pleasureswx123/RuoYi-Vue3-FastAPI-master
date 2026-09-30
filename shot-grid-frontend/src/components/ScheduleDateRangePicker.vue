<script setup>
import { ref, watch } from 'vue'
import { ElDatePicker, ElMessage } from 'element-plus'

// 统一限制新选择的计划时间；已有排期仅回显，不因打开表单而清空。
const props = defineProps({ modelValue: { type: Array, default: null } })
const emit = defineEmits(['update:modelValue', 'change'])
const localValue = ref(props.modelValue)
const pickerKey = ref(0)
const defaultTime = ref(scheduleDefaultTime())
watch(() => props.modelValue, value => { localValue.value = value })

function scheduleDefaultTime() {
  const start = new Date(Math.ceil((Date.now() + 5 * 60000) / 60000) * 60000)
  return [start, new Date(start.getTime() + 3600000)]
}
function disabledDate(date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}
function update(value) {
  if (value?.[0] && new Date(value[0]).getTime() < Date.now()) {
    pickerKey.value += 1
    localValue.value = []
    emit('update:modelValue', [])
    emit('change', [])
    ElMessage.warning('计划开始时间不能早于当前时间，请重新选择')
    return
  }
  localValue.value = value
  emit('update:modelValue', value)
  emit('change', value)
}
function visibleChange(visible) {
  if (visible) defaultTime.value = scheduleDefaultTime()
}
</script>

<template>
  <el-date-picker :key="pickerKey" :model-value="localValue" type="datetimerange" :disabled-date="disabledDate" :default-time="defaultTime" @update:model-value="update" @visible-change="visibleChange" />
</template>
