<script setup>
import { reactive, ref } from 'vue'

import { archiveProject } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({ project: { type: Object, required: true } })
const emit = defineEmits(['close', 'archived', 'refresh'])
const archiveFormRef = ref(null)
const archiveForm = reactive({ reason: '' })
const busy = ref(false)
const errorState = ref(null)
const archiveRules = {
  reason: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (!normalized) callback(new Error('请填写归档原因'))
      else if (normalized.length > 500) callback(new Error('归档原因不能超过 500 个字符'))
      else callback()
    },
    trigger: 'change'
  }]
}

async function submit() {
  if (busy.value) return
  errorState.value = null
  busy.value = true
  try {
    const isValid = archiveFormRef.value
      ? await archiveFormRef.value.validate().catch(() => false)
      : false
    if (!isValid) return

    const response = await archiveProject(props.project.projectId, {
      reason: archiveForm.reason.trim(),
      lockVersion: props.project.lockVersion
    })
    emit('archived', response.data)
  } catch (error) {
    errorState.value = projectErrorState(error, '项目归档失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ProjectModal title="归档项目" description="归档后项目将转为只读，暂不支持恢复。" :busy="busy" @close="emit('close')">
    <el-form ref="archiveFormRef" :model="archiveForm" :rules="archiveRules" class="archive-form" label-position="top">
      <el-alert :title="`${project.projectCode} · ${project.projectName}`" description="归档会保留全部业务记录和文件，但成员不能继续修改项目。" type="warning" show-icon :closable="false" />
      <el-form-item label="归档原因" prop="reason" required>
        <el-input v-model="archiveForm.reason" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="请说明归档依据" />
      </el-form-item>
      <el-alert v-if="errorState" :title="errorState.title" type="error" show-icon :closable="false"><span>{{ errorState.message }}</span><el-button v-if="errorState.status === 409" link type="danger" @click="emit('refresh')">刷新最新数据</el-button></el-alert>
      <footer>
        <el-button :disabled="busy" @click="emit('close')">取消</el-button>
        <el-button type="danger" :loading="busy" @click="submit">确认归档</el-button>
      </footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.archive-form { display: grid; gap: 20px; }
.archive-form :deep(.el-form-item) { margin-bottom: 0; }
.archive-form :deep(.el-textarea__inner) { resize: vertical; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
</style>
