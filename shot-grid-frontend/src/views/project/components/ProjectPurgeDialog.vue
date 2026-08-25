<script setup>
import { reactive, ref } from 'vue'

import { purgeProject } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({ project: { type: Object, required: true } })
const emit = defineEmits(['close', 'purged', 'refresh'])
const purgeFormRef = ref(null)
const purgeForm = reactive({ projectName: '', reason: '' })
const busy = ref(false)
const errorState = ref(null)
const purgeRules = {
  projectName: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (!normalized) callback(new Error('请输入当前项目名称'))
      else if (normalized !== props.project.projectName) callback(new Error('项目名称不一致，请完整输入当前项目名称'))
      else callback()
    },
    trigger: 'change'
  }],
  reason: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (normalized.length < 2) callback(new Error('请填写至少 2 个字符的删除原因'))
      else if (normalized.length > 500) callback(new Error('删除原因不能超过 500 个字符'))
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
    const isValid = purgeFormRef.value
      ? await purgeFormRef.value.validate().catch(() => false)
      : false
    if (!isValid) return
    const response = await purgeProject(props.project.projectId, {
      projectName: purgeForm.projectName.trim(),
      reason: purgeForm.reason.trim(),
      lockVersion: props.project.lockVersion
    })
    emit('purged', response.data)
  } catch (error) {
    errorState.value = projectErrorState(error, '项目永久删除失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ProjectModal title="永久删除项目" description="该操作不可恢复，仅平台管理员可执行。" :busy="busy" @close="emit('close')">
    <el-form ref="purgeFormRef" :model="purgeForm" :rules="purgeRules" class="purge-form" label-position="top">
      <el-alert
        title="将永久删除项目业务数据和项目 NAS 目录"
        :description="`项目：${project.projectCode} · ${project.projectName}。项目成员、镜头、资产、任务、版本与审核数据会被删除；独占上传文件会被清理，只保留最小删除审计。`"
        type="error"
        show-icon
        :closable="false"
      />
      <el-form-item :label="`输入项目名称“${project.projectName}”确认`" prop="projectName" required>
        <el-input v-model="purgeForm.projectName" maxlength="200" autocomplete="off" placeholder="完整输入当前项目名称" />
      </el-form-item>
      <el-form-item label="删除原因" prop="reason" required>
        <el-input v-model="purgeForm.reason" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="例如：公司演示产生的测试项目" />
      </el-form-item>
      <el-alert v-if="errorState" :title="errorState.title" type="error" show-icon :closable="false">
        <span>{{ errorState.message }}</span>
        <el-button v-if="errorState.status === 409" link type="danger" @click="emit('refresh')">刷新最新数据</el-button>
      </el-alert>
      <footer>
        <el-button :disabled="busy" @click="emit('close')">取消</el-button>
        <el-button type="danger" :loading="busy" @click="submit">确认永久删除</el-button>
      </footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.purge-form { display: grid; gap: 20px; }
.purge-form :deep(.el-form-item) { margin-bottom: 0; }
.purge-form :deep(.el-textarea__inner) { resize: vertical; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
</style>
