<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Document, Film, Search } from '@element-plus/icons-vue'

import { searchShotGrid } from '@/api/shot-grid/search'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  permissions: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const router = useRouter()
const inputRef = ref(null)
const keyword = ref('')
const loading = ref(false)
const errorMessage = ref('')
const searched = ref(false)
const groups = ref(emptyGroups())
let debounceTimer = null
let activeController = null
let requestGeneration = 0

const visible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value)
})
const wildcard = computed(() => props.permissions.includes('*:*:*'))
const groupDefinitions = computed(() => [
  { key: 'shots', label: '镜头', icon: Film, permissions: ['shotgrid:shot:list', 'shotgrid:shot:query'] },
  { key: 'assets', label: '资产', icon: Box, permissions: ['shotgrid:asset:list', 'shotgrid:asset:query'] },
  { key: 'files', label: '文件', icon: Document, permissions: ['shotgrid:storage:path', 'shotgrid:version:query'] }
].filter(item => wildcard.value || item.permissions.every(permission => props.permissions.includes(permission))))
const totalResults = computed(() => groupDefinitions.value.reduce(
  (total, group) => total + (groups.value[group.key]?.items?.length || 0),
  0
))

function emptyGroups() {
  return {
    shots: { items: [], hasMore: false },
    assets: { items: [], hasMore: false },
    files: { items: [], hasMore: false }
  }
}

function cancelPending() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = null
  activeController?.abort()
  activeController = null
  requestGeneration += 1
}

function scheduleSearch() {
  cancelPending()
  errorMessage.value = ''
  const normalized = keyword.value.trim()
  if (normalized.length < 2) {
    loading.value = false
    searched.value = false
    groups.value = emptyGroups()
    return
  }
  loading.value = true
  const generation = requestGeneration
  debounceTimer = setTimeout(() => performSearch(normalized, generation), 250)
}

async function performSearch(normalized, generation) {
  activeController = new AbortController()
  try {
    const response = await searchShotGrid(normalized, { signal: activeController.signal, limit: 8 })
    if (generation !== requestGeneration) return
    const data = response.data || {}
    groups.value = {
      shots: data.shots || { items: [], hasMore: false },
      assets: data.assets || { items: [], hasMore: false },
      files: data.files || { items: [], hasMore: false }
    }
    searched.value = true
  } catch (error) {
    if (generation !== requestGeneration || error?.name === 'CanceledError' || error?.name === 'AbortError') return
    errorMessage.value = error?.message || '搜索失败，请稍后重试'
    groups.value = emptyGroups()
    searched.value = true
  } finally {
    if (generation === requestGeneration) {
      loading.value = false
      activeController = null
    }
  }
}

async function handleOpened() {
  await nextTick()
  inputRef.value?.focus?.()
}

function handleClosed() {
  cancelPending()
  keyword.value = ''
  loading.value = false
  searched.value = false
  errorMessage.value = ''
  groups.value = emptyGroups()
}

async function openResult(item) {
  visible.value = false
  await router.push(item.targetPath)
}

watch(keyword, scheduleSearch)
onBeforeUnmount(cancelPending)
</script>

<template>
  <el-dialog
    v-model="visible"
    class="global-search-dialog"
    width="min(760px, calc(100vw - 32px))"
    title="全局搜索"
    append-to-body
    destroy-on-close
    @opened="handleOpened"
    @closed="handleClosed"
  >
    <el-input
      ref="inputRef"
      v-model="keyword"
      size="large"
      clearable
      :prefix-icon="Search"
      placeholder="搜索镜头编号或描述、资产名称、正式版本文件"
      aria-label="全局搜索关键字"
    />
    <p class="search-hint">输入至少 2 个字符；结果仅来自你有权访问的项目和资源。</p>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="5" animated class="search-loading" />
    <el-empty
      v-else-if="searched && totalResults === 0"
      :image-size="72"
      description="没有找到匹配的镜头、资产或文件"
    />
    <el-empty v-else-if="!searched" class="search-placeholder" :image-size="64" description="输入关键词，快速定位跨项目业务对象" />
    <el-scrollbar v-else max-height="56vh" class="search-results">
      <section
        v-for="definition in groupDefinitions"
        :key="definition.key"
        v-show="groups[definition.key].items.length > 0"
        class="search-group"
      >
        <header>
          <span><el-icon><component :is="definition.icon" /></el-icon>{{ definition.label }}</span>
          <small v-if="groups[definition.key].hasMore">仅显示前 8 条</small>
        </header>
        <el-button
          v-for="item in groups[definition.key].items"
          :key="`${item.resultType}-${item.resultId}`"
          text
          class="search-result"
          @click="openResult(item)"
        >
          <span class="search-result__content">
            <span class="search-result__main">
              <strong>{{ item.title }}</strong>
              <small v-if="item.subtitle">{{ item.subtitle }}</small>
            </span>
            <el-tag class="search-result__project" size="small" effect="plain" type="info" round>
              {{ item.projectCode }} · {{ item.projectName }}
            </el-tag>
          </span>
        </el-button>
      </section>
    </el-scrollbar>
  </el-dialog>
</template>

<style scoped lang="scss">
.search-hint {
  margin: 9px 2px 18px;
  color: var(--sg-text-muted);
  font-size: 12px;
}

.search-loading { padding: 12px 4px; }

.search-placeholder {
  min-height: 220px;
}

.search-group + .search-group { margin-top: 20px; }

.search-group header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  padding: 0 4px;
  color: var(--sg-text-secondary);
  font-size: 12px;
}

.search-group header span {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  font-weight: 700;
}

.search-group header small { color: var(--sg-text-muted); }

.search-result.el-button {
  display: block;
  width: 100%;
  height: auto;
  min-height: 58px;
  margin: 2px 0;
  padding: 9px 12px;
  color: var(--sg-text);
  text-align: left;
}

.search-result__content {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
}

.search-result__main {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.search-result__main strong,
.search-result__main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result__main small {
  color: var(--sg-text-muted);
  font-size: 12px;
}

.search-result__project.el-tag {
  flex: 0 0 auto;
  margin-left: 16px;
}

@media (max-width: 600px) {
  .search-result__project { display: none; }
}
</style>
