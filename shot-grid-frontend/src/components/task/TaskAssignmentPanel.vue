<script setup>
import { computed, onMounted, ref } from 'vue'
import { listProjectMembers } from '@/api/shot-grid/members'
import { assignAssetItemTask, assignShotTask, listTasks, startTask } from '@/api/shot-grid/tasks'

const props = defineProps({ projectId: { type: String, required: true }, shotId: String, assetItemId: [String, Number] })
const task = ref(null), members = ref([]), assigneeUserId = ref(), loading = ref(false), reason = ref('')
const filter = computed(() => props.shotId ? { shotId: props.shotId } : { assetItemId: props.assetItemId })
async function load() {
  loading.value = true
  try {
    const [tasks, memberResult] = await Promise.all([listTasks(props.projectId, filter.value), listProjectMembers(props.projectId)])
    task.value = tasks?.rows?.[0] || null
    assigneeUserId.value = task.value?.assigneeUserId
    members.value = (memberResult?.rows || memberResult || []).filter((member) => member.memberStatus === 'active' && member.producerCode)
  } finally { loading.value = false }
}
async function assign() {
  if (!assigneeUserId.value) return
  const payload = { assigneeUserId: assigneeUserId.value, dueDate: task.value?.dueDate || null, requirements: task.value?.requirements || null }
  task.value = props.shotId
    ? await assignShotTask(props.projectId, props.shotId, payload)
    : await assignAssetItemTask(props.projectId, props.assetItemId, payload)
}
async function start() { task.value = await startTask(props.projectId, task.value.taskId, { reason: reason.value || null }); await load() }
onMounted(load)
</script>
<template>
  <section v-loading="loading" class="task-panel">
    <h3>制作任务</h3>
    <div class="task-panel__actions">
      <el-select v-model="assigneeUserId" placeholder="选择项目制作人" filterable>
        <el-option v-for="member in members" :key="member.userId" :label="`${member.userName || member.nickName || member.userId} (${member.producerCode})`" :value="member.userId" />
      </el-select>
      <el-button type="primary" @click="assign">{{ task ? '改派 / 更新' : '分配任务' }}</el-button>
      <el-input v-if="task && task.taskStatus === 'not_started'" v-model="reason" placeholder="代操作时填写原因" />
      <el-button v-if="task && task.taskStatus === 'not_started'" type="success" @click="start">开始任务</el-button>
      <router-link v-if="task" :to="{ name: 'TaskDetail', params: { taskId: task.taskId }, query: { projectId } }">查看详情与历史</router-link>
    </div>
    <p v-if="task">状态：{{ task.taskStatus }} · 负责人 #{{ task.assigneeUserId }}</p>
    <p v-else>尚未分配制作任务。</p>
  </section>
</template>
<style scoped>.task-panel{margin-top:24px;padding:20px;border:1px solid var(--el-border-color);border-radius:12px}.task-panel__actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.el-select,.el-input{width:240px}</style>
