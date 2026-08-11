<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { getMemberCandidatePage, getProjectMemberCandidatePage } from '@/api/shot-grid/projects'
import { projectErrorState } from '@/views/project/projectPresentation'

const props = defineProps({
  projectId: { type: Number, default: null },
  excludeIds: { type: Array, default: () => [] },
  placeholder: { type: String, default: '按账号或姓名搜索平台用户' }
})
const emit = defineEmits(['select'])
const keyword = ref('')
const candidates = ref([])
const loading = ref(false)
const searched = ref(false)
const errorState = ref(null)
let controller = null
let timer = null

const excluded = computed(() => new Set(props.excludeIds.map(Number)))
const visibleCandidates = computed(() =>
  candidates.value.filter(candidate => !excluded.value.has(Number(candidate.userId)))
)

async function search() {
  clearTimeout(timer)
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  searched.value = true
  errorState.value = null
  try {
    const params = { pageNum: 1, pageSize: 20, keyword: keyword.value.trim() || undefined }
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

function scheduleSearch() {
  clearTimeout(timer)
  timer = setTimeout(search, 260)
}

function choose(candidate) {
  emit('select', candidate)
  keyword.value = ''
  candidates.value = []
  searched.value = false
  errorState.value = null
}

onBeforeUnmount(() => {
  clearTimeout(timer)
  controller?.abort()
})
</script>

<template>
  <div class="candidate-select">
    <label>
      <el-icon><Search /></el-icon>
      <input
        v-model="keyword"
        :placeholder="placeholder"
        aria-label="搜索平台成员"
        @focus="!searched && search()"
        @input="scheduleSearch"
        @keydown.enter.prevent="search"
      />
      <span v-if="loading">查询中…</span>
    </label>
    <div v-if="errorState" class="candidate-select__error" role="alert">
      <span>{{ errorState.message }}</span>
      <button v-if="errorState.retryable" type="button" @click="search">重试</button>
    </div>
    <ul v-else-if="searched && !loading" class="candidate-select__results">
      <li v-for="candidate in visibleCandidates" :key="candidate.userId">
        <button type="button" @click="choose(candidate)">
          <span class="candidate-select__avatar">{{ (candidate.nickName || candidate.userName).slice(0, 1) }}</span>
          <span>
            <strong>{{ candidate.nickName || candidate.userName }}</strong>
            <small>{{ candidate.userName }} · {{ candidate.deptName || '未分配部门' }}</small>
          </span>
        </button>
      </li>
      <li v-if="visibleCandidates.length === 0" class="candidate-select__empty">没有匹配且尚未选择的有效账号</li>
    </ul>
  </div>
</template>

<style scoped>
.candidate-select { position: relative; }
.candidate-select > label {
  display: flex; height: 42px; gap: 9px; align-items: center; padding: 0 12px;
  background: rgba(255,255,255,.035); border: 1px solid var(--sg-border-strong); border-radius: 10px;
}
.candidate-select input { min-width: 0; flex: 1; color: var(--sg-text); background: transparent; border: 0; outline: 0; }
.candidate-select label > span { color: var(--sg-text-muted); font-size: 11px; }
.candidate-select__results {
  position: absolute; z-index: 20; right: 0; left: 0; max-height: 280px; margin: 6px 0 0; padding: 6px;
  overflow-y: auto; list-style: none; background: var(--sg-surface-raised); border: 1px solid var(--sg-border-strong);
  border-radius: 12px; box-shadow: var(--sg-shadow);
}
.candidate-select__results button { display: flex; width: 100%; gap: 10px; align-items: center; padding: 10px; color: var(--sg-text); text-align: left; cursor: pointer; background: transparent; border: 0; border-radius: 8px; }
.candidate-select__results button:hover { background: rgba(255,255,255,.05); }
.candidate-select__avatar { display: grid; width: 32px; height: 32px; flex: 0 0 auto; color: #17130e; font-weight: 700; background: var(--sg-accent); border-radius: 50%; place-items: center; }
.candidate-select__results strong, .candidate-select__results small { display: block; }
.candidate-select__results strong { font-size: 13px; }
.candidate-select__results small { margin-top: 3px; color: var(--sg-text-muted); font-size: 11px; }
.candidate-select__empty { padding: 14px; color: var(--sg-text-muted); font-size: 12px; text-align: center; }
.candidate-select__error { display: flex; gap: 10px; justify-content: space-between; margin-top: 6px; padding: 9px 11px; color: #ffb4b4; font-size: 11px; background: rgba(255,107,107,.08); border-radius: 8px; }
.candidate-select__error button { color: var(--sg-accent); cursor: pointer; background: transparent; border: 0; }
</style>
