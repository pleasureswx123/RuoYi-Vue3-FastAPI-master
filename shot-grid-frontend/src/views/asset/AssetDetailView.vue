<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getAsset, listAssetItems } from '@/api/shot-grid/assets'
import { getErrorDetails } from '@/utils/requestErrors'
import TaskAssignmentPanel from '@/components/task/TaskAssignmentPanel.vue'
const props = defineProps({ assetId: { type: String, required: true } }), route = useRoute(), asset = ref(null), items = ref([]), loading = ref(false), error = ref(''); let controller
async function load() { controller = new AbortController(); loading.value = true; try { const projectId = String(route.query.projectId || ''); const [assetResult, itemResult] = await Promise.all([getAsset(projectId, props.assetId, { signal: controller.signal }), listAssetItems(projectId, props.assetId, { signal: controller.signal })]); asset.value = assetResult; items.value = itemResult?.rows || [] } catch (reason) { if (reason?.code !== 'ERR_CANCELED') error.value = getErrorDetails(reason).message } finally { loading.value = false } }
onMounted(load); onBeforeUnmount(() => controller?.abort())
</script>
<template><section v-loading="loading" class="page domain-page"><span class="eyebrow">ASSET / {{ assetId }}</span><div v-if="error" class="state-panel state-panel--error">{{ error }} <el-button @click="load">重试</el-button></div><template v-else-if="asset"><h1>{{ asset.assetName }}</h1><p class="lead">{{ asset.description || '暂无资产描述' }}</p><h2>制作分项</h2><p>每个分项是分配制作任务、提交版本与审核的最小单元；展开后可分配、改派或开始任务。</p><el-table :data="items" empty-text="暂无制作分项"><el-table-column type="expand"><template #default="{ row }"><TaskAssignmentPanel :project-id="String(route.query.projectId || '')" :asset-item-id="row.id || row.assetItemId" /></template></el-table-column><el-table-column prop="productionItem" label="制作分项"/><el-table-column prop="taskAssigneeName" label="制作人"><template #default="{ row }">{{ row.taskAssigneeName || '未分配' }}</template></el-table-column><el-table-column prop="latestVersionName" label="最新版本"/><el-table-column prop="aggregateStatusLabel" label="聚合状态"/></el-table></template></section></template>
