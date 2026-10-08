<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { getVersionDetail } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import ProjectDrawer from '@/views/project/components/ProjectDrawer.vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
const props = defineProps({ projectId: { type: Number, required: true } })
const emit = defineEmits(['changed'])
const session = useSessionStore()
const visible = ref(false), loading = ref(false), opening = ref(false), error = ref(''), asset = ref(null), review = ref(null)
const allowed = () => ['shotgrid:asset:query', 'shotgrid:version:query', 'shotgrid:reviewList:query', 'shotgrid:version:review'].every(permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission))
const items = computed(() => (asset.value?.items || []).filter(row => row.allowedActions?.includes('task.review') && row.task?.taskStatus === 'pending_review' && row.latestVersion?.versionId))
let generation = 0, controller, disposed = false
function close() { generation++; controller?.abort(); visible.value = false; loading.value = false }
onBeforeUnmount(() => { disposed = true; close() })
async function openReview(row) {
  if (opening.value || !allowed() || !items.value.some(item => item.assetItemId === row.assetItemId)) return
  const token = generation
  opening.value = true; error.value = ''
  try {
    const { data } = await getVersionDetail(row.latestVersion.versionId, { signal: controller.signal })
    if (disposed || token !== generation) return
    if (Number(data.taskId) !== Number(row.task.taskId)) throw new Error('审核版本与任务不匹配，请刷新列表')
    const id = data.autoReviewList?.reviewListId
    if (!id) throw new Error('当前版本没有可用审核单，请刷新列表')
    if (!allowed()) throw new Error('审核权限已变化，请刷新列表')
    if (items.value.length === 1) visible.value = false
    review.value.open(`/reviews/${id}`)
  } catch (failure) { if (!disposed && token === generation) error.value = failure.message || '审核入口加载失败，请重试' }
  finally { if (token === generation) opening.value = false }
}
async function open(parent, itemId = null) {
  if (loading.value || opening.value || !allowed() || Number(parent.projectId) !== props.projectId) return
  close(); visible.value = true; loading.value = true; error.value = ''; asset.value = null
  const token = generation
  controller = new AbortController()
  try {
    const { data } = await getAssetDetail(props.projectId, parent.assetId, { signal: controller.signal })
    if (disposed || token !== generation) return
    if (Number(data.projectId) !== props.projectId || Number(data.assetId) !== Number(parent.assetId)) throw new Error('资产范围已变化，请刷新')
    asset.value = { ...data, items: data.items.filter(item => !itemId || Number(item.assetItemId) === Number(itemId)) }
    if (items.value.length === 1) await openReview(items.value[0])
  } catch (failure) { if (!disposed && token === generation) error.value = failure.message || '分项加载失败，请关闭重试' }
  finally { if (token === generation) loading.value = false }
}
function reviewed() { close(); emit('changed') }
defineExpose({ open })
</script>
<template>
  <ProjectDrawer v-if="visible" title="选择分项审核" :description="asset?.assetName || '正在加载'" :busy="opening" wide @close="close">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="items" row-key="assetItemId">
      <el-table-column prop="productionItem" label="制作分项" min-width="180" />
      <el-table-column label="版本" width="100"><template #default="{ row }">{{ row.latestVersion.versionNumber || `V${String(row.latestVersion.versionNo).padStart(3, '0')}` }}</template></el-table-column>
      <el-table-column label="操作" width="120"><template #default="{ row }"><el-button type="primary" size="small" :disabled="opening || loading" @click="openReview(row)">审核任务</el-button></template></el-table-column>
      <template #empty><el-empty :image-size="60" description="暂无可审核分项，请刷新列表核对状态或权限" /></template>
    </el-table>
  </ProjectDrawer>
  <RelatedDetailDrawer ref="review" @closed="reviewed" />
</template>
