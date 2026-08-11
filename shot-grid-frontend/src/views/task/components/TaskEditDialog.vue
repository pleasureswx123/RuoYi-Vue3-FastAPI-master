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
const form = reactive({
  requirements: props.task.requirements || '',
  priority: props.task.priority || 'normal',
  dueDate: props.task.dueDate || ''
})

async function submit() {
  requestError.value = null
  saving.value = true
  try {
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
    description="保存制作要求、优先级和截止日期的完整快照；并发变更时后端会拒绝旧锁版本。"
    :busy="saving"
    @close="emit('close')"
  >
    <form class="task-edit-form" aria-label="编辑任务" @submit.prevent="submit">
      <label>
        <span>优先级</span>
        <select v-model="form.priority" :disabled="saving">
          <option value="low">低</option>
          <option value="normal">普通</option>
          <option value="high">高</option>
          <option value="urgent">紧急</option>
        </select>
      </label>
      <label>
        <span>截止日期</span>
        <input v-model="form.dueDate" type="date" :disabled="saving" />
      </label>
      <label class="task-edit-form__wide">
        <span>制作要求</span>
        <textarea v-model="form.requirements" rows="7" maxlength="4000" :disabled="saving" placeholder="可留空" />
      </label>

      <div v-if="requestError" class="task-edit-form__error" role="alert">
        <strong>{{ requestError.title }}</strong>
        <span>{{ requestError.message }}</span>
        <code v-if="requestError.errorKey">{{ requestError.errorKey }}</code>
        <button v-if="requestError.status === 409" type="button" @click="emit('refresh', operationContext)">刷新任务后重试</button>
      </div>

      <footer>
        <el-button :disabled="saving" @click="emit('close')">取消</el-button>
        <el-button type="primary" native-type="submit" :loading="saving">保存任务</el-button>
      </footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.task-edit-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.task-edit-form label{display:grid;gap:7px}.task-edit-form label>span{color:var(--sg-text-muted);font-size:11px}.task-edit-form input,.task-edit-form select,.task-edit-form textarea{width:100%;box-sizing:border-box;padding:10px 11px;color:var(--sg-text);background:#11151a;border:1px solid var(--sg-border);border-radius:8px}.task-edit-form textarea{resize:vertical}.task-edit-form__wide,.task-edit-form__error,footer{grid-column:1/-1}.task-edit-form__error{display:grid;gap:5px;padding:14px;color:#ffb4b4;font-size:12px;background:rgba(255,107,107,.08);border-radius:10px}.task-edit-form__error code{font-size:10px}.task-edit-form__error button{width:max-content;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:640px){.task-edit-form{grid-template-columns:1fr}.task-edit-form__wide,.task-edit-form__error,footer{grid-column:auto}}
</style>
