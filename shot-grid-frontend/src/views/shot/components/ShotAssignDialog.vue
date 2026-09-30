<script setup>
import { computed, reactive, ref } from 'vue'
import { ElCollapse, ElCollapseItem } from 'element-plus'
import 'element-plus/es/components/collapse/style/css'
import 'element-plus/es/components/collapse-item/style/css'

import { assignShotTask } from '@/api/shot-grid/shots'
import { shotAssigneeName, shotErrorState } from '@/views/shot/shotPresentation'
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
const expandedInfo = ref([])
const shotLabel = computed(() => [props.shot.episodeCode, props.shot.sceneCode, props.shot.shotCode].filter(Boolean).join(' / '))
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
  <ProjectModal :title="isReassign ? `改派制作人 · ${shotLabel}` : `分配制作人 · ${shotLabel}`" :description="isReassign ? '选择新的制作人后确认改派。' : '选择负责此镜头的制作人。'" :busy="busy" @close="closeDialog">
    <el-form ref="assignFormRef" :model="form" :rules="assignFormRules" class="assign-form" size="large" label-position="top" aria-label="镜头任务分配表单">
      <section class="assign-form__summary" aria-label="镜头摘要">
        <p class="assign-form__description">{{ shot.description || '暂无制作内容' }}</p>
        <p v-if="isReassign" class="assign-form__current"><span>当前制作人</span><strong>{{ shotAssigneeName(shot.task?.assignee, members) }}</strong></p>
      </section>
      <el-form-item :label="isReassign ? '新制作人' : '主制作人'" prop="assigneeUserId" required>
        <el-select v-model="form.assigneeUserId" class="sg-select" filterable placeholder="请选择制作人" :disabled="busy || !candidates.length"><el-option label="请选择项目成员" value="" /><el-option v-for="member in candidates" :key="member.userId" :label="member.userName ? `${member.nickName}（${member.userName}）` : member.nickName" :value="String(member.userId)" /></el-select>
        <small v-if="!candidates.length">当前项目暂无有效制作人员。</small>
      </el-form-item>
      <el-collapse v-if="!isReassign" v-model="expandedInfo" class="assign-form__production">
        <el-collapse-item name="production" title="查看完整制作信息">
          <ShotProductionInfo v-if="expandedInfo.includes('production')" :shot="shot" layout="dialog" />
        </el-collapse-item>
      </el-collapse>
      <el-alert v-if="requestError" class="assign-form__alert" type="error" :closable="false" show-icon :title="requestError.title"><div class="form-alert-content"><p>{{ requestError.message }}</p><el-button v-if="requestError.status === 409" link type="primary" @click="emit('refresh')">刷新任务后重试</el-button></div></el-alert>
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="busy || !candidates.length" @click="submit">{{ isReassign ? '确认改派' : '确认分配制作人' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.assign-form{display:grid;gap:18px}.assign-form:deep(.el-form-item){margin-bottom:0}.assign-form:deep(.el-form-item__label){height:auto;padding-bottom:8px;color:var(--sg-text);font-size:12px;font-weight:650;line-height:1.2}.assign-form:deep(.el-select),.assign-form:deep(.el-date-editor){width:100%}.assign-form small{display:block;margin-top:6px;color:var(--sg-text-muted)}.assign-form__production{display:grid;gap:10px}.assign-form__production header{display:flex;gap:12px;align-items:baseline;justify-content:space-between}.assign-form__production strong{color:var(--sg-text);font-size:12px}.assign-form__production header small{margin:0;text-align:right}.form-alert-content{display:grid;gap:5px}.form-alert-content p{margin:0}.form-alert-content code,.form-alert-content small{color:var(--sg-text-muted);font-size:10px}.form-alert-content:deep(.el-button){width:max-content;margin:0;padding:0}footer{display:flex;gap:10px;justify-content:flex-end}
.assign-form__summary{padding:14px 16px;border:1px solid var(--sg-border);border-radius:8px;background:var(--sg-surface)}
.assign-form__description{margin:0;color:var(--sg-text-secondary);font-size:12px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.assign-form__current{display:flex;align-items:center;gap:12px;margin:12px 0 0;padding-top:12px;border-top:1px solid var(--sg-border);font-size:12px}
.assign-form__current span{color:var(--sg-text-muted)}
.assign-form__current strong{color:var(--sg-text);font-weight:600}
.assign-form :deep(.el-select__wrapper){font-size:12px}
.assign-form__production :deep(.el-collapse-item__header){font-size:12px;color:var(--sg-text-muted);font-weight:400}
.assign-form__production :deep(.el-collapse-item__content){max-height:320px;overflow:auto}
</style>
