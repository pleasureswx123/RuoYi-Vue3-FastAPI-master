<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getProjectOverview } from '@/api/shot-grid/projects'
import ProjectDetailLayout from './ProjectDetailLayout.vue'
import { domainErrorMessage } from '@/utils/projectDomain'

const props = defineProps({ projectId: { type: String, required: true } })
const overview = ref(null)
const loading = ref(false)
const error = ref('')
let controller
async function loadOverview() {
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try { overview.value = await getProjectOverview(props.projectId, { signal: controller.signal }) }
  catch (reason) { if (reason?.code !== 'ERR_CANCELED') error.value = domainErrorMessage(reason, '概览加载失败。') }
  finally { loading.value = false }
}
onBeforeUnmount(() => controller?.abort())
onMounted(loadOverview)
</script>
<template>
  <ProjectDetailLayout :project-id="projectId"><template #default="{ project }"><div v-if="error" class="state-panel state-panel--error"><p>{{ error }}</p><el-button @click="loadOverview">重试</el-button></div><div v-else v-loading="loading" class="overview-content">
    <div v-if="overview" class="metric-grid"><article><span>总体进度</span><strong>{{ overview.overallProgress }}%</strong></article><article><span>镜头</span><strong>{{ overview.completedShots }} / {{ overview.totalShots }}</strong></article><article><span>资产</span><strong>{{ overview.completedAssets }} / {{ overview.totalAssets }}</strong></article><article><span>待审核</span><strong>{{ overview.pendingReviewShots + overview.pendingReviewAssets + overview.pendingReviewAssetItems }}</strong></article></div>
    <div v-if="overview" class="overview-panels"><article><h2>项目资料</h2><dl><dt>画幅</dt><dd>{{ project.aspectRatio }}</dd><dt>类型</dt><dd>{{ project.projectTypeName }}</dd><dt>当前阶段</dt><dd>{{ overview.currentPhase }}</dd><dt>交付日期</dt><dd>{{ project.deliveryDate || '未设置' }}</dd></dl></article><article><h2>制作关注</h2><dl><dt>修改中</dt><dd>{{ overview.revisionShots + overview.revisionAssets + overview.revisionAssetItems }}</dd><dt>未分配</dt><dd>{{ overview.unassignedShots + overview.unassignedAssets + overview.unassignedAssetItems }}</dd><dt>集 / 场</dt><dd>{{ overview.totalEpisodes }} / {{ overview.totalScenes }}</dd></dl></article></div>
  </div></template></ProjectDetailLayout>
</template>
