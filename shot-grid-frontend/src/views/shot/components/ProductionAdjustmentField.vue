<script setup>
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'
import { computed } from 'vue'
const props = defineProps({ field: { type: Object, required: true }, members: { type: Array, default: () => [] } })
const value = defineModel()
const memberOptions = computed(() => props.members.map(member => ({ value: member.userId, label: member.userName || member.nickName })))
const priorityOptions = [{ label: '低', value: 'low' }, { label: '普通', value: 'normal' }, { label: '高', value: 'high' }, { label: '紧急', value: 'urgent' }]
</script>
<template><div class="adjustment-field">
  <ScheduleDateRangePicker v-if="field.type === 'range'" v-model="value" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss" range-separator="至" start-placeholder="计划开始时间" end-placeholder="计划结束时间" style="width:100%" />
  <el-select v-else-if="field.type === 'member'" v-model="value" placeholder="请选择制作人" :aria-label="field.label" :options="memberOptions" />
  <el-select v-else-if="field.type === 'priority'" v-model="value" :aria-label="field.label" :options="priorityOptions" />
  <el-input-number v-else-if="field.type === 'number'" v-model="value" :min="0" :max="Number.MAX_SAFE_INTEGER" :precision="0" :aria-label="field.label" />
  <el-input v-else v-model="value" type="textarea" :rows="2" :maxlength="field.max" :show-word-limit="Boolean(field.max)" :aria-label="field.label" placeholder="填写新内容；留空表示清空该字段" />
</div></template>


<style scoped>
.adjustment-field { width: 100%; }
</style>
