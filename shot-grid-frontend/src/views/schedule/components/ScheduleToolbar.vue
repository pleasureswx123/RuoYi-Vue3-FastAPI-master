<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElTooltip } from 'element-plus'
import 'element-plus/es/components/tooltip/style/css'
import { RefreshLeft, ArrowLeft, ArrowRight, Calendar, Edit, Refresh } from '@element-plus/icons-vue'

import { dateRangeToScheduleWindow, scheduleWindowToDateRange } from '@/views/schedule/scheduleWindow'

const props = defineProps({
  mode: { type: String, default: 'swimlane' },
  scale: { type: String, default: 'day' },
  groupBy: { type: String, default: 'assignee' },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  filters: { type: Object, required: true },
  loading: Boolean,
  editMode: Boolean,
  editableAllowed: Boolean,
  unscheduledCount: { type: Number, default: 0 },
  filterOptions: { type: Object, default: () => ({}) },
  showBaseline: { type: Boolean, default: true }
})

const emit = defineEmits([
  'update:mode',
  'update:scale',
  'update:groupBy',
  'window-change',
  'window-shift',
  'filters-change',
  'baseline-change',
  'refresh',
  'edit-toggle',
  'open-unscheduled'
])

const filterFormRef = ref(null)
const filterForm = reactive({
  keyword: props.filters.keyword || '',
  assigneeUserIds: [...(props.filters.assigneeUserIds || [])],
  taskKinds: [...(props.filters.taskKinds || [])],
  taskStatuses: [...(props.filters.taskStatuses || [])],
  priorities: [...(props.filters.priorities || [])],
  episodeIds: [...(props.filters.episodeIds || [])],
  sceneIds: [...(props.filters.sceneIds || [])],
  assetTypes: [...(props.filters.assetTypes || [])],
  onlyConflicts: Boolean(props.filters.onlyConflicts),
  onlyDelayed: Boolean(props.filters.onlyDelayed)
})
const dateRange = ref(scheduleWindowToDateRange(props.windowStart, props.windowEnd))
const rules = {
  keyword: [{ max: 200, message: '关键字不能超过 200 个字符', trigger: 'blur' }]
}

watch(() => [props.windowStart, props.windowEnd], value => {
  dateRange.value = scheduleWindowToDateRange(value[0], value[1])
})

watch(() => props.filters, value => {
  filterForm.keyword = value.keyword || ''
  for (const key of ['assigneeUserIds', 'taskKinds', 'taskStatuses', 'priorities', 'episodeIds', 'sceneIds', 'assetTypes']) {
    filterForm[key] = [...(value[key] || [])]
  }
  filterForm.onlyConflicts = Boolean(value.onlyConflicts)
  filterForm.onlyDelayed = Boolean(value.onlyDelayed)
}, { deep: true })

const editLabel = computed(() => props.editMode ? '退出拖动编辑' : '开启拖动编辑')

function applyDateRange(value) {
  if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) return
  emit('window-change', dateRangeToScheduleWindow(value))
}

async function applyFilters() {
  const valid = await filterFormRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('filters-change', {
    keyword: filterForm.keyword.trim(),
    assigneeUserIds: [...filterForm.assigneeUserIds],
    taskKinds: [...filterForm.taskKinds],
    taskStatuses: [...filterForm.taskStatuses],
    priorities: [...filterForm.priorities],
    episodeIds: [...filterForm.episodeIds],
    sceneIds: [...filterForm.sceneIds],
    assetTypes: [...filterForm.assetTypes],
    onlyConflicts: filterForm.onlyConflicts,
    onlyDelayed: filterForm.onlyDelayed
  })
}

function resetFilters() {
  filterFormRef.value?.resetFields()
  filterForm.keyword = ''
  for (const key of ['assigneeUserIds', 'taskKinds', 'taskStatuses', 'priorities', 'episodeIds', 'sceneIds', 'assetTypes']) {
    filterForm[key] = []
  }
  filterForm.onlyConflicts = false
  filterForm.onlyDelayed = false
  emit('filters-change', {
    keyword: '', assigneeUserIds: [], taskKinds: [], taskStatuses: [], priorities: [],
    episodeIds: [], sceneIds: [], assetTypes: [], onlyConflicts: false, onlyDelayed: false
  })
}
</script>

<template>
  <section class="schedule-toolbar" aria-label="排期工具栏">
    <el-form ref="filterFormRef" class="schedule-toolbar__filters" :model="filterForm" :rules="rules" label-position="top">
      <el-form-item label="关键字" prop="keyword">
        <el-input v-model="filterForm.keyword" clearable placeholder="镜头号、资产或任务" @keyup.enter="applyFilters" />
      </el-form-item>
      <el-form-item label="负责人" prop="assigneeUserIds">
        <el-select v-model="filterForm.assigneeUserIds" multiple collapse-tags clearable placeholder="全部负责人">
          <el-option v-for="item in filterOptions.assignees || []" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="任务类型" prop="taskKinds">
        <el-select v-model="filterForm.taskKinds" multiple collapse-tags clearable placeholder="全部类型">
          <el-option label="镜头任务" value="shot_video" />
          <el-option label="资产任务" value="asset_image" />
        </el-select>
      </el-form-item>
      <el-form-item label="任务状态" prop="taskStatuses">
        <el-select v-model="filterForm.taskStatuses" multiple collapse-tags clearable placeholder="全部状态">
          <el-option label="待排期" value="pending_schedule" />
          <el-option label="待开工" value="not_started" />
          <el-option label="制作中" value="in_progress" />
          <el-option label="待审核" value="pending_review" />
          <el-option label="待修改" value="revision" />
          <el-option label="已完成" value="completed" />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级" prop="priorities">
        <el-select v-model="filterForm.priorities" multiple collapse-tags clearable placeholder="全部优先级">
          <el-option label="低" value="low" />
          <el-option label="普通" value="normal" />
          <el-option label="高" value="high" />
          <el-option label="紧急" value="urgent" />
        </el-select>
      </el-form-item>
      <el-form-item label="集" prop="episodeIds">
        <el-select v-model="filterForm.episodeIds" multiple collapse-tags clearable placeholder="全部集">
          <el-option v-for="item in filterOptions.episodes || []" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="场次" prop="sceneIds">
        <el-select v-model="filterForm.sceneIds" multiple collapse-tags clearable placeholder="全部场次">
          <el-option v-for="item in filterOptions.scenes || []" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="资产类型" prop="assetTypes">
        <el-select v-model="filterForm.assetTypes" multiple collapse-tags clearable placeholder="全部资产类型">
          <el-option label="角色" value="Character" />
          <el-option label="场景" value="Environment" />
          <el-option label="道具" value="Prop" />
        </el-select>
      </el-form-item>
      <div class="schedule-toolbar__footer">
        <el-form-item label="关注项" label-position="left" class="schedule-toolbar__focus">
          <el-tooltip content="允许重叠安排；此选项仅用于查看同一项目、同一制作人计划时间重叠的任务，不代表排期错误。勾选后点击应用筛选；同时勾选两个条件时须同时满足。" placement="top">
            <el-checkbox v-model="filterForm.onlyConflicts" aria-description="仅显示同一制作人计划时间重叠的任务">仅排期重叠</el-checkbox>
          </el-tooltip>
          <el-tooltip content="当前计划结束时间晚于最初排期，不表示已经到期未完成。无最初排期的任务不计入。勾选后点击应用筛选。" placement="top">
            <el-checkbox v-model="filterForm.onlyDelayed" aria-description="仅显示当前计划结束时间晚于最初排期的任务">仅较最初排期延后</el-checkbox>
          </el-tooltip>
        </el-form-item>
        <el-form-item class="schedule-toolbar__filter-actions">
          <el-button type="primary" :loading="loading" @click="applyFilters">应用筛选</el-button>
          <el-button :icon="RefreshLeft" @click="resetFilters">重置</el-button>
        </el-form-item>


      <div class="schedule-toolbar__actions">
        <el-tooltip content="用细线对比任务第一次确定的计划，后续改期不会改变它；不代表实际制作时间。" placement="top">
        <el-checkbox :model-value="showBaseline" @change="value => emit('baseline-change', value)">对比最初排期</el-checkbox>
        </el-tooltip>
        <el-button :icon="Refresh" :loading="loading" @click="emit('refresh')">刷新</el-button>
        <el-button @click="emit('open-unscheduled')">未排期任务（{{ unscheduledCount }}）</el-button>
        <el-button
          :type="editMode ? 'warning' : 'primary'"
          :plain="!editMode"
          :icon="Edit"
          :disabled="!editableAllowed"
          :aria-description="editableAllowed ? '' : '没有调整排期权限'"
          @click="emit('edit-toggle', !editMode)"
        >{{ editLabel }}</el-button>
      </div>
      </div>
    </el-form>
  </section>
    <div class="schedule-toolbar__primary" aria-label="排期时间与视图">
      <el-radio-group :model-value="mode" size="small" aria-label="排期视图" @change="value => emit('update:mode', value)">
        <el-radio-button value="swimlane">人员泳道</el-radio-button>
        <el-radio-button value="gantt">任务甘特</el-radio-button>
      </el-radio-group>
      <el-radio-group :model-value="scale" size="small" aria-label="时间缩放" @change="value => emit('update:scale', value)">
        <el-radio-button value="day">日</el-radio-button>
        <el-radio-button value="week">周</el-radio-button>
        <el-radio-button value="month">月</el-radio-button>
      </el-radio-group>
      <el-select :model-value="groupBy" class="schedule-toolbar__group" aria-label="分组方式" @change="value => emit('update:groupBy', value)">
        <el-option label="按负责人" value="assignee" />
        <el-option label="按任务类型" value="task_kind" />
        <el-option label="按状态" value="status" />
        <el-option label="按集" value="episode" />
        <el-option label="按场次" value="scene" />
        <el-option label="按资产类型" value="asset_type" />
      </el-select>
      <div class="schedule-toolbar__navigation">
        <el-button :icon="ArrowLeft" aria-label="上一时间窗口" @click="emit('window-shift', -1)" />
        <el-button :icon="Calendar" aria-label="回到今天" @click="emit('window-shift', 0)">回到今天</el-button>
        <el-button :icon="ArrowRight" aria-label="下一时间窗口" @click="emit('window-shift', 1)" />
      </div>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        unlink-panels
        :clearable="false"
        @change="applyDateRange"
      />
      <slot name="deadline-filter" />
    </div>
</template>

<style scoped>
.schedule-toolbar { container-type: inline-size; display: grid; gap: 14px; padding: 16px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.schedule-toolbar__primary,.schedule-toolbar__actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.schedule-toolbar__primary {
  position: sticky;
  top: var(--app-header-height, 76px);
  z-index: 20;
  justify-content: center;
  padding: 8px 12px;
  background: var(--sg-surface);
  border: 1px solid var(--sg-border);
  border-radius: var(--sg-radius-md);
  box-shadow: 0 2px 8px rgb(0 0 0 / 4%);
}
.schedule-toolbar__primary :deep(.el-date-editor) { flex: 1; min-width: 250px; max-width: 520px; }
.schedule-toolbar__navigation { display: flex; gap: 6px; flex-shrink: 0; }
.schedule-toolbar__navigation .el-button + .el-button { margin-left: 0; }
.schedule-toolbar__primary :deep(.el-radio-group) { flex-shrink: 0; }
.schedule-toolbar__group { width: 150px; }
.schedule-toolbar__filters { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; align-items: end; }
.schedule-toolbar__footer { grid-column: 1 / -1; display: flex; align-items: center; flex-wrap: wrap; gap: 12px 20px; }
.schedule-toolbar__focus:deep(.el-form-item__label) { margin-bottom: 0; padding-right: 12px; }
.schedule-toolbar__focus:deep(.el-form-item__content) { gap: 16px; }
.schedule-toolbar__focus:deep(.el-checkbox) { margin-right: 0; }
.schedule-toolbar__filters:deep(.el-form-item), .schedule-toolbar__filters:deep(.el-form-item__content) { min-width: 0; }
.schedule-toolbar__filters:deep(.el-select) { width: 100%; }
.schedule-toolbar__footer .el-button + .el-button { margin-left: 0; }
.schedule-toolbar__filters:deep(.el-form-item) { margin-bottom: 0; }
.schedule-toolbar__filters:deep(.el-form-item__label) { color: var(--sg-text-muted); font-size: 11px; }
.schedule-toolbar__filter-actions:deep(.el-form-item__content) { flex-wrap: nowrap; gap: 10px; }
.schedule-toolbar__actions { margin-left: auto; justify-content: flex-end; }
@container (min-width: 1200px) {
  .schedule-toolbar__filters { grid-template-columns: minmax(170px,1.4fr) repeat(7,minmax(0,1fr)); }

}
@container (max-width: 899px) {
  .schedule-toolbar__filters { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .schedule-toolbar__actions { width: 100%; margin-left: 0; justify-content: flex-start; }
}
@container (max-width: 479px) {
  .schedule-toolbar__filters { grid-template-columns: minmax(0,1fr); }
}
</style>
