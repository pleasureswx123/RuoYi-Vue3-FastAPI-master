<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { getProductionHistory } from '@/api/shot-grid/productionHistory'
import { taskMilestones } from '@/views/schedule/scheduleMilestones'
import { eventsForLane, expandProductionTimeline, formatHistoryDateTime, historyReviewActionMeta, actorDisplayName } from '@/components/production-history/productionHistoryPresentation'
const props = defineProps({ task: { type: Object, default: null }, active: Boolean })
const emit = defineEmits(['loaded'])
const data = ref(null)
const loading = ref(false)
const error = ref('')
let generation = 0
let controller
const history = ref(null)
const timeline = computed(() => {
  const lane = history.value?.lanes?.find(item => item.task?.taskId === props.task?.taskId)
  return expandProductionTimeline(eventsForLane(history.value?.events, lane?.laneId)).reverse()
})
function eventTitle(event) {
  if (event.reviewAction) return `${event.versionCycle.versionNumber} 审核 · ${historyReviewActionMeta(event.reviewAction.actionType).label}`
  if (event.versionCycle) return `${event.versionCycle.versionNumber} 提交版本`
  return event.title
}
async function load() {
  const current = ++generation
  controller?.abort()
  data.value = null
  history.value = null
  error.value = ''
  loading.value = false
  emit('loaded', null)
  const task = props.task
  if (!props.active || !task?.projectId || !task.target) return
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  try {
    const shot = task.target.targetKind === 'shot'
    const response = await getProductionHistory(task.projectId, shot ? 'shot' : 'asset', shot ? task.target.targetId : task.target.parentId, { signal })
    if (current !== generation) return
    history.value = response.data
    data.value = taskMilestones(response.data, task.taskId)
    if (!data.value) throw new Error('履历中未找到当前任务')
    emit('loaded', data.value)
  } catch (caught) {
    if (current === generation && !signal.aborted) error.value = caught?.message || '实际节点加载失败'
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(() => [props.active, props.task?.projectId, props.task?.taskId, props.task?.lockVersion], load, { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>
<template>
  <section aria-label="实际关键节点">
    <el-skeleton v-if="loading" animated :rows="2" />
    <el-alert v-else-if="error" type="info" :closable="false" title="实际节点暂不可用">
      <span>{{ error }}</span><el-button link type="primary" @click="load">重试</el-button>
    </el-alert>
    <div v-else>
      <h4>制作履历节点</h4>
      <el-timeline v-if="timeline.length" mode="alternate">
        <el-timeline-item v-for="(event, index) in timeline" :key="event.eventId" :timestamp="formatHistoryDateTime(event.occurredAt)" placement="top" :type="index === timeline.length - 1 ? 'warning' : 'success'" hollow>
          <el-tooltip :content="`${actorDisplayName(event.reviewAction?.reviewer || event.versionCycle?.submitter || event.actor)} · ${eventTitle(event)}`" placement="top">
            <div class="milestone-summary"><span class="milestone-actor">{{ actorDisplayName(event.reviewAction?.reviewer || event.versionCycle?.submitter || event.actor) }}</span> · {{ eventTitle(event) }}</div>
          </el-tooltip>
          <el-tag v-if="event.evidenceLevel === 'inferred'" size="small" type="info">按现有记录推断</el-tag>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else :image-size="40" description="暂无可确认的履历记录" />
    </div>
  </section>
</template>

<style scoped>
h4 { margin: 0 0 16px; font-size: 14px; font-weight: 600; line-height: 20px; }
.milestone-summary { font-size: 12px; line-height: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.milestone-actor { color: var(--sg-text-muted); }
</style>
