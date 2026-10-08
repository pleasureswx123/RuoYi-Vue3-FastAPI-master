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
    <template v-else-if="detail">
      <template v-if="detail.requirements"><el-text tag="strong" size="small">制作要求</el-text><p>{{ detail.requirements }}</p></template>
      <el-text tag="strong" size="small">参考资料</el-text>
      <p v-if="detail.referenceDescription">{{ detail.referenceDescription }}</p>
      <ReviewReferenceFiles v-if="detail.referenceFiles?.length" :files="detail.referenceFiles" compact />
      <el-text v-if="!detail.referenceDescription && !detail.referenceFiles?.length" type="info" size="small">暂无参考资料</el-text>
    </template>
  </section>
</template>
<style scoped>
.item-references{display:grid;gap:8px;margin-top:12px;font-size:12px;text-align:left}.item-references :deep(.el-text){justify-self:start;align-self:start}.item-references p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--sg-text-secondary)}
</style>
