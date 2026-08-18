<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { getMemberCandidatePage, getProjectMemberCandidatePage } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'

const props = defineProps({
  projectId: { type: Number, default: null },
  departmentId: { type: Number, default: null },
  excludeIds: { type: Array, default: () => [] },
  placeholder: { type: String, default: '按账号或姓名搜索平台用户' }
})
const emit = defineEmits(['select'])
const keyword = ref('')
const selectedUserId = ref('')
const candidates = ref([])
const loading = ref(false)
const errorState = ref(null)
let controller = null
let timer = null

const excluded = computed(() => new Set(props.excludeIds.map(Number)))
const visibleCandidates = computed(() =>
  candidates.value.filter(candidate => !excluded.value.has(Number(candidate.userId)))
)

async function search(nextKeyword = keyword.value) {
  clearTimeout(timer)
  keyword.value = String(nextKeyword || '')
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  errorState.value = null
  try {
    const params = {
      pageNum: 1,
      pageSize: 20,
      keyword: keyword.value.trim() || undefined,
      deptId: props.departmentId || undefined
    }
    const options = { signal: requestController.signal }
    const response = props.projectId
      ? await getProjectMemberCandidatePage(props.projectId, params, options)
      : await getMemberCandidatePage(params, options)
    candidates.value = Array.isArray(response.rows) ? response.rows : []
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      candidates.value = []
      errorState.value = projectErrorState(error, '成员候选加载失败')
    }
  } finally {
    if (controller === requestController) loading.value = false
  }
}

function scheduleSearch(nextKeyword = '') {
  keyword.value = String(nextKeyword || '')
  clearTimeout(timer)
  timer = setTimeout(() => search(keyword.value), 260)
}

function choose(userId) {
  const candidate = visibleCandidates.value.find(item => String(item.userId) === String(userId))
  if (!candidate) return
  emit('select', candidate)
  selectedUserId.value = ''
  keyword.value = ''
  candidates.value = []
  errorState.value = null
}

function openSelect(visible) {
  if (visible && !candidates.value.length && !loading.value) search(keyword.value)
}

onBeforeUnmount(() => {
  clearTimeout(timer)
  controller?.abort()
})
</script>

<template>
  <div class="candidate-select">
    <el-select
      v-model="selectedUserId"
      class="candidate-select__control"
      filterable
      remote
      clearable
      :remote-method="scheduleSearch"
      :loading="loading"
      :placeholder="placeholder"
      popper-class="candidate-select__popper"
      loading-text="正在查询平台用户…"
      no-data-text="没有匹配且尚未选择的有效账号"
      aria-label="搜索平台成员"
      :suffix-icon="Search"
      @visible-change="openSelect"
      @change="choose"
    >
      <el-option
        v-for="candidate in visibleCandidates"
        :key="candidate.userId"
        :value="String(candidate.userId)"
        :label="candidate.nickName || candidate.userName"
      >
        <span class="candidate-select__avatar">{{ (candidate.nickName || candidate.userName).slice(0, 1) }}</span>
        <span class="candidate-select__identity">
          <strong>{{ candidate.nickName || candidate.userName }}</strong>
          <small>{{ candidate.userName }} · {{ candidate.deptName || '未分配部门' }}</small>
        </span>
      </el-option>
    </el-select>
    <el-alert v-if="errorState" class="candidate-select__error" :title="errorState.message" type="error" show-icon :closable="false">
      <el-button v-if="errorState.retryable" link type="danger" @click="search(keyword)">重试</el-button>
    </el-alert>
  </div>
</template>

<style scoped>
.candidate-select { display: grid; gap: 7px; }
.candidate-select__control { width: 100%; }
.candidate-select__error { --el-alert-bg-color: rgba(255,107,107,.08); }
.candidate-select__error :deep(.el-alert__description) { margin-top: 4px; }

/* 下拉层 Teleport 到 body，使用专属 popper 类承载两行成员信息及明暗主题。 */
:global(.candidate-select__popper.el-select__popper.el-popper) {
  --el-bg-color-overlay: var(--sg-surface-raised);
  --el-border-color-light: var(--sg-border-strong);
  --el-fill-color-light: var(--sg-fill-soft);
  --el-text-color-regular: var(--sg-text-secondary);
  --el-text-color-secondary: var(--sg-text-muted);
  background: var(--sg-surface-raised);
  border-color: var(--sg-border-strong);
  box-shadow: var(--sg-shadow);
}

:global(.candidate-select__popper .el-select-dropdown__list) {
  padding: 6px;
}

:global(.candidate-select__popper .el-select-dropdown__item) {
  display: flex;
  min-height: 52px;
  height: auto;
  align-items: center;
  padding: 8px 12px;
  line-height: 1.25;
  border-radius: 8px;
}

:global(.candidate-select__popper .el-select-dropdown__item.is-hovering) {
  background: var(--sg-fill-soft);
}

:global(.candidate-select__popper .el-select-dropdown__item.is-selected) {
  background: var(--sg-accent-soft);
}

:global(.candidate-select__popper .candidate-select__avatar) {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  color: var(--sg-on-accent);
  font-weight: 700;
  line-height: 1;
  background: var(--sg-accent-surface);
  border-radius: 50%;
  place-items: center;
}

:global(.candidate-select__popper .candidate-select__identity) {
  display: block;
  min-width: 0;
  margin-left: 10px;
  line-height: 1.25;
}

:global(.candidate-select__popper .candidate-select__identity strong),
:global(.candidate-select__popper .candidate-select__identity small) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.candidate-select__popper .candidate-select__identity strong) {
  color: var(--sg-text);
  font-size: 13px;
  font-weight: 650;
}

:global(.candidate-select__popper .candidate-select__identity small) {
  margin-top: 3px;
  color: var(--sg-text-secondary);
  font-size: 11px;
  font-weight: 400;
}

:global(.candidate-select__popper .el-select-dropdown__item.is-selected .candidate-select__identity strong) {
  color: var(--sg-accent);
}
</style>
