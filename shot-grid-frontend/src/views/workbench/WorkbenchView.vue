<script setup>
import { onMounted, ref } from 'vue'
import { listMyTasks } from '@/api/shot-grid/tasks'

const tasks = ref([]), loading = ref(false)
onMounted(async () => {
  loading.value = true
  try { tasks.value = (await listMyTasks({ pageNum: 1, pageSize: 50 }))?.rows || [] }
  finally { loading.value = false }
})
</script>
<template>
  <section v-loading="loading" class="page"><span class="eyebrow">OVERVIEW</span><h1>我的任务</h1><p class="lead">当前由你负责的镜头与资产制作分项。</p><el-table :data="tasks" empty-text="暂无任务"><el-table-column prop="taskName" label="任务"/><el-table-column prop="taskKind" label="类型"/><el-table-column prop="taskStatus" label="状态"/><el-table-column prop="dueDate" label="截止日期"/><el-table-column label="操作"><template #default="{ row }"><router-link :to="{ name: 'TaskDetail', params: { taskId: row.taskId }, query: { projectId: row.projectId } }">详情</router-link></template></el-table-column></el-table></section>
</template>
