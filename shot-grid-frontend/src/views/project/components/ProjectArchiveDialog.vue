<script setup>
import { ref } from 'vue'

import { archiveProject } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({ project: { type: Object, required: true } })
const emit = defineEmits(['close', 'archived', 'refresh'])
const reason = ref('')
const busy = ref(false)
const errorState = ref(null)

async function submit() {
  const normalized = reason.value.trim()
  if (!normalized) {
    errorState.value = { title: '请填写归档原因', message: '归档原因会进入审计记录。', status: 422 }
    return
  }
  busy.value = true
  errorState.value = null
  try {
    const response = await archiveProject(props.project.projectId, {
      reason: normalized,
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
  <ProjectModal title="归档项目" description="归档后项目只允许读取，当前没有普通恢复入口。" :busy="busy" @close="emit('close')">
    <form class="archive-form" @submit.prevent="submit">
      <div class="archive-warning">
        <strong>{{ project.projectCode }} · {{ project.projectName }}</strong>
        <p>归档会保留全部业务记录和文件引用，但成员不能继续修改项目。</p>
      </div>
      <label>
        <span>归档原因 *</span>
        <textarea v-model="reason" rows="4" maxlength="500" placeholder="请说明归档依据" />
      </label>
      <div v-if="errorState" class="archive-error" role="alert">
        <strong>{{ errorState.title }}</strong><span>{{ errorState.message }}</span>
        <el-button v-if="errorState.status === 409" text @click="emit('refresh')">刷新最新数据</el-button>
      </div>
      <footer>
        <el-button :disabled="busy" @click="emit('close')">取消</el-button>
        <el-button type="danger" native-type="submit" :loading="busy">确认归档</el-button>
      </footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.archive-form, label, .archive-error { display: grid; gap: 8px; }
.archive-form { gap: 20px; }
.archive-warning { padding: 16px; background: rgba(255,182,87,.08); border: 1px solid rgba(255,182,87,.2); border-radius: 12px; }
.archive-warning p { margin: 7px 0 0; color: var(--sg-text-secondary); font-size: 13px; line-height: 1.6; }
label span { font-size: 13px; font-weight: 600; }
textarea { width: 100%; padding: 12px; color: var(--sg-text); resize: vertical; background: rgba(255,255,255,.035); border: 1px solid var(--sg-border-strong); border-radius: 10px; }
.archive-error { padding: 14px; color: #ffb4b4; font-size: 13px; background: rgba(255,107,107,.08); border-radius: 10px; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
</style>
