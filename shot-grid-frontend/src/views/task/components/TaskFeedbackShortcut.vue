<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElButton } from 'element-plus'
import { getTaskIssues } from '@/api/shot-grid/reviews'

const props = defineProps({
  taskId: { type: Number, required: true },
  enabled: { type: Boolean, default: false },
  refreshKey: { type: [Number, String], default: 0 }
})
const emit = defineEmits(['open'])
const count = ref(0)
const state = ref('idle')
let controller
async function load() {
  controller?.abort()
  count.value = 0
  state.value = 'idle'
  if (!props.enabled) return
  const request = new AbortController()
  controller = request
  state.value = 'loading'
  try {
    const { data } = await getTaskIssues(props.taskId, { status: 'open' }, { signal: request.signal })
    if (request.signal.aborted) return
    if (!Array.isArray(data)) throw new Error('反馈响应无效')
    count.value = new Set(data.filter(issue => issue.status === 'open').map(issue => issue.issueId)).size
    state.value = 'ready'
  } catch (error) {
    if (!request.signal.aborted && error?.code !== 'ERR_CANCELED') state.value = 'error'
  }
}
watch(() => [props.taskId, props.enabled, props.refreshKey], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div v-if="enabled && (state !== 'ready' || count)" class="task-feedback-shortcut" aria-live="polite">
    <el-button v-if="state === 'ready' && count" type="danger" size="small" plain @click.stop="emit('open')">待处理反馈 {{ count }} 条</el-button>
    <el-button v-else-if="state === 'error'" link type="warning" size="small" @click.stop="load">反馈加载失败 · 重试</el-button>
    <small v-else>反馈加载中…</small>
  </div>
</template>

<style scoped>
.task-feedback-shortcut { margin-top: 6px; color: var(--sg-text-muted); }
</style>
