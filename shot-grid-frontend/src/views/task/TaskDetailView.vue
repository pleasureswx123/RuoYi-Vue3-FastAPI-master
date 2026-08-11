<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTask, startTask } from '@/api/shot-grid/tasks'

const props = defineProps({ taskId: { type: String, required: true } })
const route = useRoute(), projectId = String(route.query.projectId || ''), task = ref(null), reason = ref('')
async function load() { task.value = await getTask(projectId, props.taskId) }
async function start() { await startTask(projectId, props.taskId, { reason: reason.value || null }); await load() }
onMounted(load)
const actionLabels = { assigned: '分配', reassigned: '改派', started: '开始任务' }
</script>
<template>
  <section class="page"><span class="eyebrow">TASK / {{ taskId }}</span><template v-if="task"><h1>{{ task.taskName }}</h1><p class="lead">状态：{{ task.taskStatus }} · 负责人 #{{ task.assigneeUserId }}</p><div v-if="task.taskStatus === 'not_started'" class="task-actions"><el-input v-model="reason" placeholder="代操作时填写原因"/><el-button type="success" @click="start">开始任务</el-button></div><h2>任务历史</h2><el-timeline><el-timeline-item v-for="item in task.history" :key="item.historyId" :timestamp="item.createTime"><strong>{{ actionLabels[item.action] || item.action }}</strong><span> · 操作人 #{{ item.actorUserId }}</span><el-tag v-if="item.delegated" type="warning">代操作</el-tag><p v-if="item.detail?.reason">原因：{{ item.detail.reason }}</p></el-timeline-item></el-timeline></template></section>
</template>
<style scoped>.task-actions{display:flex;gap:12px;max-width:600px;margin:20px 0}.el-tag{margin-left:8px}</style>
