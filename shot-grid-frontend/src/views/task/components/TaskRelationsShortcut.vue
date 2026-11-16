<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getShotDetail } from '@/api/shot-grid/shots'
import { getAssetRelations } from '@/api/shot-grid/assets'
import { useSessionStore } from '@/store/modules/session'

const props = defineProps({ task: { type: Object, required: true }, refreshKey: { type: [Number, String], default: 0 } })
const emit = defineEmits(['open'])
const session = useSessionStore()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const enabled = computed(() => allowed('shotgrid:task:query') && allowed('shotgrid:asset:query') && (props.task.taskKind !== 'shot_video' || allowed('shotgrid:shot:query')))
const count = ref(0)
const state = ref('idle')
let controller
async function load() {
  controller?.abort()
  count.value = 0; state.value = 'idle'
  if (!enabled.value) return
  const request = new AbortController(); controller = request; state.value = 'loading'
  const task = props.task, projectId = Number(task.project?.projectId)
  const shot = task.taskKind === 'shot_video'
  const targetId = Number(shot ? task.target?.shotId || task.target?.targetId : task.target?.assetId)
  try {
    if (!Number.isSafeInteger(projectId) || projectId <= 0 || !Number.isSafeInteger(targetId) || targetId <= 0) throw new Error('任务目标无效')
    const { data } = await (shot ? getShotDetail : getAssetRelations)(projectId, targetId, { signal: request.signal })
    if (request.signal.aborted) return
    const assets = shot ? data?.assets : data?.relatedAssets
    if (Number(data?.projectId) !== projectId || Number(shot ? data?.shotId : data?.assetId) !== targetId || !Array.isArray(assets)) throw new Error('关联归属不匹配')
    if (assets.some(asset => !Number.isSafeInteger(Number(asset.assetId)) || Number(asset.assetId) <= 0 || (asset.projectId != null && Number(asset.projectId) !== projectId))) throw new Error('关联资产无效')
    count.value = new Set(assets.map(asset => Number(asset.assetId))).size
    state.value = 'ready'
  } catch { if (!request.signal.aborted) state.value = 'error' }
}
watch(() => [props.task.taskId, props.task.project?.projectId, props.task.taskKind, props.task.target?.shotId, props.task.target?.targetId, props.task.target?.assetId, enabled.value, props.refreshKey], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <div v-if="enabled" class="task-relations-shortcut" aria-live="polite">
    <el-button v-if="state === 'ready'" link type="primary" size="small" @click.stop="emit('open')">{{ count ? `关联资产 ${count} 项` : '暂无关联资产' }}</el-button>
    <el-button v-else-if="state === 'error'" link type="warning" size="small" @click.stop="load">关联加载失败 · 重试</el-button>
    <el-text v-else size="small" type="info">关联资产加载中…</el-text>
  </div>
</template>
<style scoped>
.task-relations-shortcut { margin-top: 6px; }
</style>
