<script setup>
import { computed, reactive, ref } from 'vue'

import { assignShotTask } from '@/api/shot-grid/shots'
import { shotErrorState } from '@/views/shot/shotPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'

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
const assignFormRef = ref(null)
const busy = ref(false)
const requestError = ref(null)
const form = reactive({
  assigneeUserId: props.shot.task?.assignee?.userId ? String(props.shot.task.assignee.userId) : ''
})
const candidates = computed(() => props.members.filter(member => member.projectRole === 'creator'))
const isReassign = computed(() => Boolean(props.shot.task))
const assignFormRules = {
  assigneeUserId: [{
    validator: (_rule, value, callback) => {
      const userId = Number(value)
      if (!Number.isSafeInteger(userId) || userId <= 0) {
        callback(new Error('请选择制作人员'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}

async function submit() {
  if (busy.value) return
  requestError.value = null
  const valid = assignFormRef.value
    ? await assignFormRef.value.validate().catch(() => false)
    : false
  if (!valid) return
  const userId = Number(form.assigneeUserId)
  const payload = {
    assigneeUserId: userId
  }
  if (isReassign.value) {
    payload.taskLockVersion = props.shot.task.lockVersion
  }
  busy.value = true
  try {
    const response = await assignShotTask(operationContext.projectId, operationContext.shotId, payload)
    emit('assigned', response.data, operationContext)
  } catch (error) {
    requestError.value = shotErrorState(error, isReassign.value ? '镜头任务改派失败' : '镜头任务分配失败')
  } finally { busy.value = false }
}

function closeDialog() {
  if (busy.value) return
  assignFormRef.value?.resetFields()
  assignFormRef.value?.clearValidate()
  requestError.value = null
  emit('close')
}
</script>

<template>
  <ProjectModal :title="isReassign ? `改派 ${shot.shotCode}` : `分配 ${shot.shotCode}`" :description="isReassign ? '本次只调整主制作人，原任务内容保持不变。' : '首次分配会按当前镜头制作内容创建任务；如需调整制作要求，请先编辑镜头。'" :busy="busy" @close="closeDialog">
    <el-form ref="assignFormRef" :model="form" :rules="assignFormRules" class="assign-form" size="large" label-position="top" aria-label="镜头任务分配表单">
      <el-form-item label="主制作人" prop="assigneeUserId" required>
        <el-select v-model="form.assigneeUserId" class="sg-select" placeholder="请选择项目成员" :disabled="busy || !candidates.length"><el-option label="请选择项目成员" value="" /><el-option v-for="member in candidates" :key="member.userId" :label="member.userName ? `${member.nickName}（${member.userName}）` : member.nickName" :value="String(member.userId)" /></el-select>
        <small v-if="!candidates.length">当前项目暂无有效制作人员。</small>
      </el-form-item>
      <section class="assign-form__production" aria-labelledby="assign-production-title">
        <header><strong id="assign-production-title">完整制作信息</strong><small>只读；如需调整，请先编辑镜头。</small></header>
        <ShotProductionInfo :shot="shot" layout="dialog" />
      </section>
      <p v-if="isReassign" class="assign-form__warning">仅待开工任务可改派，原任务要求、优先级和截止日期保持不变。目录准备中及后续状态均不可普通改派；存在待处理版本提交时也不能改派。</p>
      <el-alert v-if="requestError" class="assign-form__alert" type="error" :closable="false" show-icon :title="requestError.title"><div class="form-alert-content"><p>{{ requestError.message }}</p><el-button v-if="requestError.status === 409" link type="primary" @click="emit('refresh')">刷新任务后重试</el-button></div></el-alert>
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="busy || !candidates.length" @click="submit">{{ isReassign ? '确认改派' : '创建并分配任务' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.assign-form{display:grid;gap:18px}.assign-form:deep(.el-form-item){margin-bottom:0}.assign-form:deep(.el-form-item__label){height:auto;padding-bottom:8px;color:var(--sg-text);font-size:12px;font-weight:650;line-height:1.2}.assign-form:deep(.el-select),.assign-form:deep(.el-date-editor){width:100%}.assign-form small{display:block;margin-top:6px;color:var(--sg-text-muted)}.assign-form__production{display:grid;gap:10px}.assign-form__production header{display:flex;gap:12px;align-items:baseline;justify-content:space-between}.assign-form__production strong{color:var(--sg-text);font-size:12px}.assign-form__production header small{margin:0;text-align:right}.assign-form__warning{margin:0;padding:12px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:9px}.form-alert-content{display:grid;gap:5px}.form-alert-content p{margin:0}.form-alert-content code,.form-alert-content small{color:var(--sg-text-muted);font-size:10px}.form-alert-content:deep(.el-button){width:max-content;margin:0;padding:0}footer{display:flex;gap:10px;justify-content:flex-end}
</style>
