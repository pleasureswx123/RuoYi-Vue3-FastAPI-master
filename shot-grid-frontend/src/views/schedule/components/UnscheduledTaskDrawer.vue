<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getUnscheduledScheduleTasks } from '@/api/shot-grid/schedules'
import { scheduleTaskLabel } from '@/views/schedule/schedulePresentation'
import { taskPriorityMeta, taskStatusMeta } from '@/views/task/taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({
  visible: Boolean,
  projectId: { type: [Number, String], required: true },
  query: { type: Object, required: true }
})

const emit = defineEmits(['update:visible', 'edit-task'])
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref(null)
let controller = null
let generation = 0

const drawerVisible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value)
})

async function loadRows() {
  controller?.abort()
  if (!props.visible) return
  const currentGeneration = ++generation
  controller = new AbortController()
  loading.value = true
  error.value = null
  try {
    const response = await getUnscheduledScheduleTasks(
      props.projectId,
      { ...props.query, pageNum: 1, pageSize: 100 },
      { signal: controller.signal }
    )
    if (currentGeneration !== generation) return
    const result = response?.data ?? response ?? {}
    rows.value = Array.isArray(result.rows) ? result.rows : []
    total.value = Number(result.total || 0)
  } catch (caught) {
    if (currentGeneration === generation && caught?.code !== 'ERR_CANCELED') error.value = caught
  } finally {
    if (currentGeneration === generation) loading.value = false
  }
}

watch(() => [props.visible, props.projectId, JSON.stringify(props.query)], loadRows, { immediate: true })
onBeforeUnmount(() => {
  generation += 1
  controller?.abort()
})
</script>

<template>
  <el-drawer v-model="drawerVisible" title="未排期任务" direction="rtl" size="680px" append-to-body destroy-on-close>
    <el-alert type="info" :closable="false" show-icon title="这里只展示已有真实任务且负责人有效的未排期项；未分配镜头或资产仍在原列表处理。" />
    <el-alert v-if="error" class="unscheduled-drawer__state" type="error" :closable="false" show-icon title="未排期任务加载失败" description="请重试，不会将服务失败显示为空任务池。" />
    <el-table v-else v-loading="loading" :data="rows" row-key="taskId" empty-text="当前没有未排期任务">
      <el-table-column label="任务" min-width="220"><template #default="{ row }">{{ scheduleTaskLabel(row) }}</template></el-table-column>
      <el-table-column label="负责人" width="120"><template #default="{ row }">{{ row.assignee?.userName || '—' }}</template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="tagTypeFromTone(taskStatusMeta(row.taskStatus).tone)" effect="light" round>{{ taskStatusMeta(row.taskStatus).label }}</el-tag></template></el-table-column>
      <el-table-column label="优先级" width="90"><template #default="{ row }"><el-tag :type="tagTypeFromTone(taskPriorityMeta(row.priority).tone)" effect="plain" round>{{ taskPriorityMeta(row.priority).label }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="110" fixed="right"><template #default="{ row }"><el-button v-if="row.allowedActions?.includes('schedule')" type="primary" size="small" @click="emit('edit-task', row)">安排时间</el-button><span v-else>只读</span></template></el-table-column>
    </el-table>
    <p class="unscheduled-drawer__count">共 {{ total }} 项未排期任务</p>
  </el-drawer>
</template>

<style scoped>
.unscheduled-drawer__state { margin-top: 14px; }
.unscheduled-drawer__count { color: var(--sg-text-muted); font-size: 11px; text-align: right; }
</style>
