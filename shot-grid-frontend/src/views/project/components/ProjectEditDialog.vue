<script setup>
import { onBeforeUnmount, reactive, ref } from 'vue'
import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'

import { updateProject } from '@/api/shot-grid/projects'
import { PROJECT_PHASE_OPTIONS, projectErrorState } from '@/views/project/projectPresentation'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'

const props = defineProps({
  project: { type: Object, required: true },
  referencesOnly: { type: Boolean, default: false }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const editFormRef = ref(null)
const busy = ref(false)
const requestError = ref(null)
const initialProjectId = props.project.projectId
const initialLockVersion = props.project.lockVersion
let active = true
onBeforeUnmount(() => { active = false })
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({
  canEdit: () => !busy.value,
  isCurrent: () => active && props.project.projectId === initialProjectId && props.project.lockVersion === initialLockVersion
})
resetReferenceAttachments((props.project.referenceFiles || []).map(file => ({ ...file })))
const form = reactive({
  referenceFileIds: referenceAttachments,
  referenceDescription: props.project.referenceDescription || '',
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
  referenceDescription: [{ max: 10000, message: '资料说明不能超过 10000 字', trigger: 'change' }],
  remark: [{ max: 500, message: '备注不能超过 500 个字符', trigger: 'change' }]
}

function buildPayload() {
  const projectName = form.projectName.trim()
  return {
    projectName,
    referenceDescription: form.referenceDescription.trim() || null,
    projectDescription: form.projectDescription.trim() || null,
    projectType: form.projectType,
    aspectRatio: form.aspectRatio,
    plannedDurationMs: props.project.plannedDurationMs ?? null,
    deliveryDate: props.project.deliveryDate || null,
    currentPhase: form.currentPhase,
    remark: form.remark.trim() || null,
    lockVersion: initialLockVersion
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
    payload.referenceFileIds = await uploadPendingReferenceFiles()
    const response = await updateProject(initialProjectId, payload)
    if (!active || props.project.projectId !== initialProjectId) return
    emit('saved', response.data)
  } catch (error) {
    requestError.value = projectErrorState(error, '项目修改失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-drawer
    :title="referencesOnly ? '编辑项目资料' : '编辑项目'"
    :model-value="true"
    size="min(720px, 100vw)"
    direction="rtl"
    append-to-body
    destroy-on-close
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    :before-close="done => { if (!busy) done() }"
    @close="!busy && emit('close')"
  >
    <el-form ref="editFormRef" :model="form" :disabled="busy" :rules="editRules" class="edit-form" size="large" label-position="top">
      <el-alert v-if="!referencesOnly" title="项目代号和 NAS 目录绑定创建后不可在此修改。" type="info" :closable="false" show-icon />
      <el-form-item v-if="!referencesOnly" label="项目名称" prop="projectName" required>
        <el-input v-model="form.projectName" maxlength="200" />
      </el-form-item>
      <div v-if="!referencesOnly" class="edit-form__grid">
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
      <el-form-item v-if="!referencesOnly" label="项目描述" prop="projectDescription">
        <el-input v-model="form.projectDescription" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="项目资料说明（可选）" prop="referenceDescription">
        <el-input v-model="form.referenceDescription" type="textarea" :rows="4" maxlength="10000" show-word-limit placeholder="可填写剧本梗概、风格要求、参考资料说明等，供本项目所有任务制作时查阅。" />
      </el-form-item>
      <el-form-item label="剧本与参考附件（可选）" prop="referenceFileIds">
        <ReviewReferenceInput :files="referenceAttachments" :disabled="busy" purpose="项目" @add="addReferenceFile" @remove="removeReferenceFile" />
      </el-form-item>
      <el-form-item v-if="!referencesOnly" label="备注" prop="remark">
        <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
      </el-form-item>
      <el-alert v-if="requestError" :title="requestError.title" type="error" show-icon :closable="false">
        <span>{{ requestError.message }}</span>
        <el-button v-if="requestError?.status === 409" link type="danger" @click="emit('refresh')">刷新最新数据</el-button>
      </el-alert>
    </el-form>
    <template #footer>
      <el-button :disabled="busy" @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="busy" @click="submit">{{ referencesOnly ? '保存资料' : '保存修改' }}</el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.edit-form { display: grid; }
.edit-form { gap: 18px; }
.edit-form__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.edit-form :deep(.el-form-item) { margin-bottom: 0; }
.edit-form :deep(.el-input),
.edit-form :deep(.el-select) { width: 100%; }
.edit-form :deep(.el-textarea__inner) { resize: vertical; }
@media (max-width: 620px) { .edit-form__grid { grid-template-columns: 1fr; } }
</style>
