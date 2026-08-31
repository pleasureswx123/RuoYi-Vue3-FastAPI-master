<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Calendar, Edit, Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  mode: { type: String, default: 'swimlane' },
  scale: { type: String, default: 'week' },
  groupBy: { type: String, default: 'assignee' },
  windowStart: { type: String, required: true },
  windowEnd: { type: String, required: true },
  filters: { type: Object, required: true },
  loading: Boolean,
  editMode: Boolean,
  editableAllowed: Boolean,
  unscheduledCount: { type: Number, default: 0 }
})

const emit = defineEmits([
  'update:mode',
  'update:scale',
  'update:groupBy',
  'window-change',
  'window-shift',
  'filters-change',
  'refresh',
  'edit-toggle',
  'open-unscheduled'
])

const filterFormRef = ref(null)
const filterForm = reactive({
  keyword: props.filters.keyword || '',
  taskStatus: props.filters.taskStatuses?.[0] || '',
  priority: props.filters.priorities?.[0] || ''
})
const dateRange = ref([props.windowStart, props.windowEnd])
const rules = {
  keyword: [{ max: 200, message: '关键字不能超过 200 个字符', trigger: 'blur' }]
}

watch(() => [props.windowStart, props.windowEnd], value => {
  dateRange.value = [...value]
})

const editLabel = computed(() => props.editMode ? '退出排期编辑' : '进入排期编辑')

function applyDateRange(value) {
  if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) return
  emit('window-change', { windowStart: value[0], windowEnd: value[1] })
}

async function applyFilters() {
  const valid = await filterFormRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('filters-change', {
    keyword: filterForm.keyword.trim(),
    taskStatuses: filterForm.taskStatus ? [filterForm.taskStatus] : [],
    priorities: filterForm.priority ? [filterForm.priority] : []
  })
}

function resetFilters() {
  filterFormRef.value?.resetFields()
  filterForm.keyword = ''
  filterForm.taskStatus = ''
  filterForm.priority = ''
  emit('filters-change', { keyword: '', taskStatuses: [], priorities: [] })
}
</script>

<template>
  <section class="schedule-toolbar" aria-label="排期工具栏">
    <div class="schedule-toolbar__primary">
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
        <el-button :icon="Calendar" @click="emit('window-shift', 0)">今天</el-button>
        <el-button :icon="ArrowRight" aria-label="下一时间窗口" @click="emit('window-shift', 1)" />
      </div>
      <el-date-picker
        v-model="dateRange"
        type="datetimerange"
        value-format="YYYY-MM-DDTHH:mm:ss"
        format="YYYY-MM-DD HH:mm"
        range-separator="至"
        start-placeholder="窗口开始"
        end-placeholder="窗口结束"
        :clearable="false"
        @change="applyDateRange"
      />
    </div>

    <el-form ref="filterFormRef" class="schedule-toolbar__filters" :model="filterForm" :rules="rules" label-position="top">
      <el-form-item label="关键字" prop="keyword">
        <el-input v-model="filterForm.keyword" clearable placeholder="镜头号、资产或任务" @keyup.enter="applyFilters" />
      </el-form-item>
      <el-form-item label="任务状态" prop="taskStatus">
        <el-select v-model="filterForm.taskStatus" clearable placeholder="全部状态">
          <el-option label="待开工" value="not_started" />
          <el-option label="目录准备中" value="preparing" />
          <el-option label="制作中" value="in_progress" />
          <el-option label="待审核" value="pending_review" />
          <el-option label="待修订" value="revision" />
          <el-option label="已完成" value="completed" />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级" prop="priority">
        <el-select v-model="filterForm.priority" clearable placeholder="全部优先级">
          <el-option label="低" value="low" />
          <el-option label="普通" value="normal" />
          <el-option label="高" value="high" />
          <el-option label="紧急" value="urgent" />
        </el-select>
      </el-form-item>
      <el-form-item class="schedule-toolbar__filter-actions">
        <el-button type="primary" :loading="loading" @click="applyFilters">应用筛选</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </el-form-item>
    </el-form>

    <div class="schedule-toolbar__actions">
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
  </section>
</template>

<style scoped>
.schedule-toolbar { display: grid; gap: 14px; padding: 16px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-md); }
.schedule-toolbar__primary,.schedule-toolbar__actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.schedule-toolbar__group { width: 150px; }
.schedule-toolbar__filters { display: grid; grid-template-columns: minmax(220px,1fr) repeat(2,minmax(140px,.45fr)) auto; gap: 10px; align-items: end; }
.schedule-toolbar__filters:deep(.el-form-item) { margin-bottom: 0; }
.schedule-toolbar__filters:deep(.el-form-item__label) { color: var(--sg-text-muted); font-size: 11px; }
.schedule-toolbar__filter-actions:deep(.el-form-item__content) { flex-wrap: nowrap; }
.schedule-toolbar__actions { justify-content: flex-end; }
@media (max-width: 980px) { .schedule-toolbar__filters { grid-template-columns: 1fr 1fr; }.schedule-toolbar__filter-actions { grid-column: 1 / -1; } }
@media (max-width: 640px) { .schedule-toolbar__filters { grid-template-columns: 1fr; }.schedule-toolbar__filter-actions { grid-column: auto; } }
</style>
