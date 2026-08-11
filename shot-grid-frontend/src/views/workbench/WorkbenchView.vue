<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getWorkbench } from '@/api/shot-grid/discovery'
import EmptyState from '@/components/EmptyState.vue'
import { createLatestRequest } from '@/utils/latestRequest'

const data = ref(null), loading = ref(false), error = ref('')
const gate = createLatestRequest()
const sections = [
  ['myTasks', '我的任务'], ['pendingReviews', '待审核'], ['revisions', '修改中'],
  ['recentSubmissions', '近期提交'], ['projectSummaries', '项目摘要']
]
async function load() {
  loading.value = true; error.value = ''
  try {
    const result = await gate.run(signal => getWorkbench({ recentLimit: 8 }, { signal }))
    if (result.accepted) data.value = result.value
  } catch (e) { error.value = e.status === 403 ? '你没有查看工作台的权限' : '工作台加载失败，请稍后重试' }
  finally { loading.value = false }
}
onMounted(load); onBeforeUnmount(() => gate.cancel())
</script>
<template>
  <section class="page" v-loading="loading">
    <span class="eyebrow">OVERVIEW</span><h1>制作工作台</h1><p class="lead">你的任务、审核与项目进度均由服务端按项目权限聚合。</p>
    <el-result v-if="error" icon="error" title="无法加载工作台" :sub-title="error"><template #extra><el-button type="primary" @click="load">重试</el-button></template></el-result>
    <template v-else-if="data">
      <article v-for="([key, title]) in sections" :key="key" class="dashboard-card">
        <h2>{{ title }} <small>{{ data[key]?.length || 0 }}</small></h2>
        <EmptyState v-if="!data[key]?.length" :title="`暂无${title}`" description="这里有新内容时会自动汇总显示。" />
        <el-table v-else :data="data[key]" size="small">
          <el-table-column prop="projectName" label="项目" min-width="150" />
          <el-table-column :prop="key === 'projectSummaries' ? 'projectStatus' : key === 'recentSubmissions' ? 'taskName' : 'taskName'" :label="key === 'projectSummaries' ? '状态' : '内容'" min-width="190" />
          <el-table-column v-if="key === 'myTasks' || key === 'pendingReviews' || key === 'revisions'" prop="taskStatus" label="状态" width="130" />
          <el-table-column v-if="key === 'recentSubmissions'" prop="versionNo" label="版本" width="90"><template #default="{ row }">V{{ String(row.versionNo).padStart(3, '0') }}</template></el-table-column>
          <el-table-column v-if="key === 'projectSummaries'" prop="taskCount" label="任务数" width="100" />
          <el-table-column v-if="key !== 'projectSummaries'" label="操作" width="90"><template #default="{ row }"><router-link :to="{ name: 'TaskDetail', params: { taskId: row.taskId }, query: { projectId: row.projectId } }">详情</router-link></template></el-table-column>
        </el-table>
      </article>
    </template>
  </section>
</template>
