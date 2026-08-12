<script setup>
import { reactive, ref } from 'vue'

import { updateProject } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({
  project: { type: Object, required: true }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const busy = ref(false)
const validationMessage = ref('')
const requestError = ref(null)
const form = reactive({
  projectName: props.project.projectName || '',
  projectDescription: props.project.projectDescription || '',
  projectType: props.project.projectType || 'ai_short_film',
  aspectRatio: props.project.aspectRatio || '16:9',
  plannedDurationMinutes:
    props.project.plannedDurationMs === null || props.project.plannedDurationMs === undefined
      ? ''
      : String(props.project.plannedDurationMs / 60000),
  deliveryDate: props.project.deliveryDate || '',
  currentPhase: props.project.currentPhase || 'planning',
  remark: props.project.remark || ''
})

function buildPayload() {
  const projectName = form.projectName.trim()
  if (!projectName) throw new Error('项目名称不能为空')
  const minutes = form.plannedDurationMinutes === '' ? null : Number(form.plannedDurationMinutes)
  if (minutes !== null && (!Number.isFinite(minutes) || minutes < 0)) {
    throw new Error('计划总时长不能为负数')
  }
  return {
    projectName,
    projectDescription: form.projectDescription.trim() || null,
    projectType: form.projectType,
    aspectRatio: form.aspectRatio,
    plannedDurationMs: minutes === null ? null : Math.round(minutes * 60000),
    deliveryDate: form.deliveryDate || null,
    currentPhase: form.currentPhase,
    remark: form.remark.trim() || null,
    lockVersion: props.project.lockVersion
  }
}

async function submit() {
  validationMessage.value = ''
  requestError.value = null
  let payload
  try {
    payload = buildPayload()
  } catch (error) {
    validationMessage.value = error.message
    return
  }
  busy.value = true
  try {
    const response = await updateProject(props.project.projectId, payload)
    emit('saved', response.data)
  } catch (error) {
    requestError.value = projectErrorState(error, '项目修改失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ProjectModal title="编辑项目" description="项目代号和 NAS 绑定不可在普通编辑中修改。" :busy="busy" @close="emit('close')">
    <form class="edit-form" @submit.prevent="submit">
      <label><span>项目名称 *</span><input v-model="form.projectName" maxlength="200" /></label>
      <div class="edit-form__grid">
        <label>
          <span>当前阶段 *</span>
          <el-select v-model="form.currentPhase" class="sg-select">
            <el-option label="策划" value="planning" />
            <el-option label="资产制作" value="asset_production" />
            <el-option label="镜头制作" value="shot_production" />
            <el-option label="审核" value="review" />
            <el-option label="交付" value="delivery" />
            <el-option label="已完成" value="completed" />
          </el-select>
        </label>
        <label>
          <span>画幅 *</span>
          <el-select v-model="form.aspectRatio" class="sg-select">
            <el-option v-for="ratio in ['16:9', '21:9', '2.39:1', '9:16', '1:1']" :key="ratio" :label="ratio" :value="ratio" />
          </el-select>
        </label>
        <label><span>计划总时长（分钟）</span><input v-model="form.plannedDurationMinutes" type="number" min="0" step="0.1" /></label>
        <label><span>交付日期</span><input v-model="form.deliveryDate" type="date" /></label>
      </div>
      <label><span>项目描述</span><textarea v-model="form.projectDescription" rows="4" /></label>
      <label><span>备注</span><textarea v-model="form.remark" rows="2" maxlength="500" /></label>
      <div v-if="validationMessage || requestError" class="edit-form__error" role="alert">
        <strong>{{ requestError?.title || '请检查表单' }}</strong>
        <span>{{ requestError?.message || validationMessage }}</span>
        <el-button v-if="requestError?.status === 409" text @click="emit('refresh')">刷新最新数据</el-button>
      </div>
      <footer>
        <el-button :disabled="busy" @click="emit('close')">取消</el-button>
        <el-button type="primary" native-type="submit" :loading="busy">保存修改</el-button>
      </footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.edit-form,
label { display: grid; gap: 8px; }
.edit-form { gap: 18px; }
.edit-form__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
label span { font-size: 13px; font-weight: 600; }
input, textarea {
  width: 100%; color: var(--sg-text); background: rgba(255,255,255,.035);
  border: 1px solid var(--sg-border-strong); border-radius: 10px;
}
input { height: 42px; padding: 0 12px; }
textarea { padding: 11px 12px; resize: vertical; }
input:focus, textarea:focus { border-color: var(--sg-accent); outline: 0; }
.edit-form__error { display: grid; gap: 5px; padding: 14px; color: #ffb4b4; font-size: 13px; background: rgba(255,107,107,.08); border-radius: 10px; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
@media (max-width: 620px) { .edit-form__grid { grid-template-columns: 1fr; } }
</style>
