<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
const props = defineProps({ taskId: { type: Number, required: true }, taskVersion: { type: Number, default: 0 }, projectId: { type: Number, required: true } })
const detail = ref(null), loading = ref(false), error = ref('')
let generation = 0, controller
async function load() {
  const token = ++generation
  controller?.abort()
  controller = new AbortController()
  detail.value = null; error.value = ''; loading.value = true
  try {
    const { data } = await getTaskDetail(props.taskId, { signal: controller.signal })
    if (token !== generation) return
    if (Number(data.taskId) !== props.taskId || Number(data.project?.projectId) !== props.projectId) throw new Error('制作资料范围已变化，请刷新后查看')
    detail.value = data
  } catch (failure) {
    if (token === generation) error.value = [403, 404].includes(Number(failure?.httpStatus || failure?.status)) ? '暂无权限查看该任务的制作资料' : '制作资料加载失败'
  } finally { if (token === generation) loading.value = false }
}
watch(() => [props.projectId, props.taskId, props.taskVersion], load, { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>
<template>
  <section class="item-references" aria-label="制作要求与参考资料">
    <el-skeleton v-if="loading" :rows="1" animated />
    <template v-else-if="error"><el-text type="warning" size="small">{{ error }}</el-text><el-button link type="primary" @click="load">重试</el-button></template>
    <el-descriptions v-else-if="detail" :column="1" label-width="96px" size="small" border>
      <el-descriptions-item label="制作要求"><p>{{ detail.requirements || '暂无额外制作要求。' }}</p></el-descriptions-item>
      <el-descriptions-item label="参考说明"><p>{{ detail.referenceDescription || '暂无参考说明。' }}</p></el-descriptions-item>
      <el-descriptions-item label="参考附件">
        <ReviewReferenceFiles v-if="detail.referenceFiles?.length" :files="detail.referenceFiles" compact />
        <el-text v-else type="info" size="small">暂无参考附件。</el-text>
      </el-descriptions-item>
    </el-descriptions>
  </section>
</template>
<style scoped>
.item-references{display:grid;gap:8px;margin-top:12px;font-size:12px;text-align:left}.item-references :deep(.el-text){justify-self:start;align-self:start}.item-references p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--sg-text-secondary)}
.item-references :deep(.el-descriptions__cell) { padding: 8px 10px !important; border-color: var(--sg-border); font-size: 12px; line-height: 1.6; }
.item-references :deep(.el-descriptions__label) { color: var(--sg-text-muted); background: var(--sg-surface-raised); font-weight: 500; }
.item-references :deep(.el-descriptions__content) { background: var(--sg-surface); overflow-wrap: anywhere; }
</style>
