<script setup>
import { reactive, ref } from 'vue'

import { updateProject } from '@/api/shot-grid/projects'
import { PROJECT_PHASE_OPTIONS, projectErrorState } from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({
  project: { type: Object, required: true }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const editFormRef = ref(null)
const busy = ref(false)
const requestError = ref(null)
const form = reactive({
  projectName: props.project.projectName || '',
  projectDescription: props.project.projectDescription || '',
  projectType: props.project.projectType || 'ai_short_film',
  aspectRatio: props.project.aspectRatio || '16:9',
  currentPhase: props.project.currentPhase || 'planning',
  remark: props.project.remark || ''
})
const editRules = {
  projectName: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (!normalized) callback(new Error('项目名称不能为空'))
      else if (normalized.length > 200) callback(new Error('项目名称不能超过 200 个字符'))
      else callback()
    },
    trigger: 'change'
  }],
  currentPhase: [{ required: true, type: 'enum', enum: PROJECT_PHASE_OPTIONS.map(phase => phase.value), message: '请选择有效的当前阶段', trigger: 'change' }],
  aspectRatio: [{ required: true, type: 'enum', enum: ['16:9', '21:9', '2.39:1', '9:16', '1:1'], message: '请选择有效的画幅', trigger: 'change' }],
  remark: [{ max: 500, message: '备注不能超过 500 个字符', trigger: 'change' }]
}

function buildPayload() {
  const projectName = form.projectName.trim()
  return {
    projectName,
    projectDescription: form.projectDescription.trim() || null,
    projectType: form.projectType,
    aspectRatio: form.aspectRatio,
    plannedDurationMs: props.project.plannedDurationMs ?? null,
    deliveryDate: props.project.deliveryDate || null,
    currentPhase: form.currentPhase,
    remark: form.remark.trim() || null,
    lockVersion: props.project.lockVersion
  }
}

async function submit() {
  if (busy.value) return
  requestError.value = null
  busy.value = true
  try {
    const isValid = editFormRef.value
      ? await editFormRef.value.validate().catch(() => false)
      : false
    if (!isValid) return

    const payload = buildPayload()
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
  <ProjectModal title="编辑项目" description="项目代号和 NAS 目录绑定创建后不可在此修改。" :busy="busy" @close="emit('close')">
    <el-form ref="editFormRef" :model="form" :rules="editRules" class="edit-form" size="large" label-position="top">
      <el-form-item label="项目名称" prop="projectName" required>
        <el-input v-model="form.projectName" maxlength="200" />
      </el-form-item>
      <div class="edit-form__grid">
        <el-form-item label="当前阶段" prop="currentPhase" required>
          <el-select v-model="form.currentPhase" class="sg-select">
            <el-option v-for="phase in PROJECT_PHASE_OPTIONS" :key="phase.value" :label="phase.label" :value="phase.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="画幅" prop="aspectRatio" required>
          <el-select v-model="form.aspectRatio" class="sg-select">
            <el-option v-for="ratio in ['16:9', '21:9', '2.39:1', '9:16', '1:1']" :key="ratio" :label="ratio" :value="ratio" />
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="项目描述" prop="projectDescription">
        <el-input v-model="form.projectDescription" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="备注" prop="remark">
        <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
      </el-form-item>
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false">
        <span>{{ requestError.message }}</span>
        <el-button v-if="requestError?.status === 409" link type="danger" @click="emit('refresh')">刷新最新数据</el-button>
      </el-alert>
      <footer>
        <el-button :disabled="busy" @click="emit('close')">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submit">保存修改</el-button>
      </footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.edit-form { display: grid; }
.edit-form { gap: 18px; }
.edit-form__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.edit-form :deep(.el-form-item) { margin-bottom: 0; }
.edit-form :deep(.el-input),
.edit-form :deep(.el-select) { width: 100%; }
.edit-form :deep(.el-textarea__inner) { resize: vertical; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
@media (max-width: 620px) { .edit-form__grid { grid-template-columns: 1fr; } }
</style>
