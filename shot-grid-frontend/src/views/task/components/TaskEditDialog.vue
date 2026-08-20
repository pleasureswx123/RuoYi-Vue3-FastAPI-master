<script setup>
import { reactive, ref } from 'vue'

import { updateTask } from '@/api/shot-grid/tasks'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { taskErrorState } from '@/views/task/taskPresentation'

const props = defineProps({
  task: { type: Object, required: true },
  operationGeneration: { type: Number, required: true }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const operationContext = Object.freeze({
  taskId: Number(props.task.taskId),
  projectId: Number(props.task.project?.projectId),
  operationGeneration: Number(props.operationGeneration)
})
const saving = ref(false)
const requestError = ref(null)
const formRef = ref(null)
const form = reactive({
  requirements: props.task.requirements || '',
  priority: props.task.priority || 'normal',
  dueDate: props.task.dueDate || ''
})
const formRules = {
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
  requirements: [{ max: 4000, message: '制作要求不能超过 4000 个字符', trigger: 'blur' }]
}

async function submit() {
  if (saving.value) return
  requestError.value = null
  saving.value = true
  try {
    let valid = false
    await formRef.value?.validate(result => {
      valid = result
    })
    if (!valid) return
    const response = await updateTask(operationContext.taskId, {
      requirements: form.requirements.trim() || null,
      priority: form.priority,
      dueDate: form.dueDate || null,
      lockVersion: Number(props.task.lockVersion)
    })
    emit('saved', response.data, operationContext)
  } catch (error) {
    requestError.value = taskErrorState(error, '任务更新失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ProjectModal
    :title="`编辑任务 · ${task.taskName}`"
    description="保存制作要求、优先级和截止日期；若任务已被他人更新，请刷新后再保存。"
    :busy="saving"
    @close="emit('close')"
  >
    <el-form ref="formRef" :model="form" :rules="formRules" class="task-edit-form" size="large" label-position="top" aria-label="编辑任务">
      <el-form-item label="优先级" prop="priority">
        <el-select v-model="form.priority" class="sg-select" :disabled="saving">
          <el-option label="低" value="low" />
          <el-option label="普通" value="normal" />
          <el-option label="高" value="high" />
          <el-option label="紧急" value="urgent" />
        </el-select>
      </el-form-item>
      <el-form-item label="截止日期" prop="dueDate">
        <el-date-picker v-model="form.dueDate" class="task-edit-form__control" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD" clearable :disabled="saving" placeholder="选择截止日期" />
      </el-form-item>
      <el-form-item class="task-edit-form__wide" label="制作要求" prop="requirements">
        <el-input v-model="form.requirements" type="textarea" :rows="7" maxlength="4000" show-word-limit resize="vertical" :disabled="saving" placeholder="可留空" />
      </el-form-item>

      <el-alert v-if="requestError" class="task-edit-form__alert" type="error" :closable="false" show-icon :title="requestError.title">
        <div class="form-alert-content"><p>{{ requestError.message }}</p><el-button v-if="requestError.status === 409" link type="primary" @click="emit('refresh', operationContext)">刷新任务后重试</el-button></div>
      </el-alert>

      <footer>
        <el-button :disabled="saving" @click="emit('close')">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存任务</el-button>
      </footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.task-edit-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.task-edit-form :deep(.el-form-item){margin-bottom:0}.task-edit-form__control{width:100%}.task-edit-form__wide,.task-edit-form__alert,footer{grid-column:1/-1}.form-alert-content{display:grid;gap:5px}.form-alert-content p{margin:0}.form-alert-content code,.form-alert-content small{color:var(--sg-text-muted);font-size:10px}.form-alert-content .el-button{width:max-content;padding:0}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:640px){.task-edit-form{grid-template-columns:1fr}.task-edit-form__wide,.task-edit-form__alert,footer{grid-column:auto}}
</style>
