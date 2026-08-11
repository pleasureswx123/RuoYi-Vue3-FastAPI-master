<script setup>
import { computed, reactive, ref } from 'vue'

import { assignShotTask } from '@/api/shot-grid/shots'
import { shotErrorState } from '@/views/shot/shotPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  shot: { type: Object, required: true },
  members: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'assigned', 'refresh'])
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  shotId: Number(props.shot.shotId),
  operationGeneration: Number(props.operationGeneration),
  wasReassign: Boolean(props.shot.task)
})
const busy = ref(false)
const validationMessage = ref('')
const requestError = ref(null)
const form = reactive({
  assigneeUserId: props.shot.task?.assignee?.userId ? String(props.shot.task.assignee.userId) : '',
  taskDescription: props.shot.description || '',
  priority: props.shot.task?.priority || 'normal',
  dueDate: props.shot.task?.dueDate || ''
})
const candidates = computed(() => props.members.filter(member => member.producerCode))
const isReassign = computed(() => Boolean(props.shot.task))

async function submit() {
  validationMessage.value = ''
  requestError.value = null
  const userId = Number(form.assigneeUserId)
  if (!Number.isSafeInteger(userId) || userId <= 0) { validationMessage.value = '请选择具有制作人缩写的项目成员'; return }
  const payload = {
    assigneeUserId: userId
  }
  if (isReassign.value) {
    payload.taskLockVersion = props.shot.task.lockVersion
  } else {
    payload.taskDescription = form.taskDescription.trim() || null
    payload.priority = form.priority
    payload.dueDate = form.dueDate || null
  }
  busy.value = true
  try {
    const response = await assignShotTask(operationContext.projectId, operationContext.shotId, payload)
    emit('assigned', response.data, operationContext)
  } catch (error) {
    requestError.value = shotErrorState(error, isReassign.value ? '镜头任务改派失败' : '镜头任务分配失败')
  } finally { busy.value = false }
}
</script>

<template>
  <ProjectModal :title="isReassign ? `改派 ${shot.shotCode}` : `分配 ${shot.shotCode}`" description="首次分配会创建唯一镜头视频任务；改派更新同一任务，不创建第二条任务。" :busy="busy" @close="emit('close')">
    <form class="assign-form" @submit.prevent="submit">
      <label><span>主制作人 *</span><select v-model="form.assigneeUserId"><option value="">请选择项目成员</option><option v-for="member in candidates" :key="member.userId" :value="String(member.userId)">{{ member.nickName }}（{{ member.producerCode }}）</option></select><small v-if="!candidates.length">暂无已配置制作人缩写的有效项目成员。</small></label>
      <template v-if="!isReassign">
        <label><span>任务优先级</span><select v-model="form.priority"><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
        <label><span>截止日期</span><input v-model="form.dueDate" type="date" /></label>
        <label><span>制作要求</span><textarea v-model="form.taskDescription" rows="5" /></label>
      </template>
      <p v-if="isReassign" class="assign-form__warning">本动作只改派主制作人，原任务要求、优先级和截止日期保持不变；存在未完成版本提交或状态冲突时后端会拒绝改派。</p>
      <div v-if="validationMessage || requestError" class="assign-form__error" role="alert"><strong>{{ requestError?.title || '请检查表单' }}</strong><span>{{ requestError?.message || validationMessage }}</span><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新任务后重试</button></div>
      <footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="busy" :disabled="!candidates.length">{{ isReassign ? '确认改派' : '创建并分配任务' }}</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.assign-form,.assign-form label{display:grid;gap:8px}.assign-form{gap:18px}.assign-form label>span{font-size:12px;font-weight:650}input,select,textarea{width:100%;color:var(--sg-text);background:rgba(255,255,255,.035);border:1px solid var(--sg-border-strong);border-radius:10px}input,select{height:42px;padding:0 12px}textarea{padding:11px 12px;resize:vertical}small{color:var(--sg-text-muted)}.assign-form__warning{margin:0;padding:12px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:9px}.assign-form__error{display:grid;gap:5px;padding:14px;color:#ffb4b4;font-size:13px;background:rgba(255,107,107,.08);border-radius:10px}.assign-form__error button{width:max-content;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
