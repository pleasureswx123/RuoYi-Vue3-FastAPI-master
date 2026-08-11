<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { globalSearch } from '@/api/shot-grid/discovery'
import { createLatestRequest, debounce } from '@/utils/latestRequest'

const router = useRouter(), keyword = ref(''), rows = ref([]), loading = ref(false), error = ref(''), open = ref(false)
const gate = createLatestRequest()
const routes = { shot: 'ShotDetail', asset: 'AssetDetail', task: 'TaskDetail', version: 'VersionReview', file: 'Files' }
const labels = { shot: '镜头', asset: '资产', task: '任务', version: '版本', file: '文件' }
async function search() {
  const value = keyword.value.trim(); open.value = Boolean(value)
  if (!value) { gate.cancel(); rows.value = []; return }
  loading.value = true; error.value = ''
  try { const result = await gate.run(signal => globalSearch({ keyword: value, pageNum: 1, pageSize: 12, resourceType: 'all' }, { signal })); if (result.accepted) rows.value = result.value?.rows || [] }
  catch { error.value = '搜索失败，请重试' }
  finally { loading.value = false }
}
const delayedSearch = debounce(search, 350); watch(keyword, delayedSearch)
const message = computed(() => loading.value ? '搜索中…' : error.value || (!rows.value.length ? '没有匹配结果' : ''))
function visit(row) {
  const name = routes[row.resourceType]
  if (row.resourceType === 'file') {
    router.push({ name, query: { keyword: row.title } }); open.value = false; keyword.value = ''; return
  }
  const params = row.resourceType === 'shot' ? { shotId: row.resourceId } : row.resourceType === 'asset' ? { assetId: row.resourceId } : row.resourceType === 'task' ? { taskId: row.resourceId } : { versionId: row.resourceId }
  const query = { projectId: row.projectId }
  router.push({ name, params, query }); open.value = false; keyword.value = ''
}
onBeforeUnmount(() => { delayedSearch.cancel(); gate.cancel() })
</script>
<template><div class="global-search"><el-input v-model="keyword" clearable aria-label="全局搜索" placeholder="搜索镜头、资产、任务、版本" @focus="open = Boolean(keyword)" />
  <div v-if="open" class="search-results"><p v-if="message">{{ message }}</p><button v-for="row in rows" :key="`${row.resourceType}-${row.resourceId}`" type="button" @click="visit(row)"><span>{{ labels[row.resourceType] }}</span><strong>{{ row.title }}</strong><small>{{ row.subtitle }}</small></button><button v-if="error" type="button" @click="search">重试</button></div>
</div></template>
