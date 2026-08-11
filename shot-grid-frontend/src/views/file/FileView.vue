<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { downloadBusinessFile, listBusinessFiles } from '@/api/shot-grid/discovery'
import EmptyState from '@/components/EmptyState.vue'
import { createLatestRequest, debounce } from '@/utils/latestRequest'

const route = useRoute()
const rows = ref([]), total = ref(0), loading = ref(false), error = ref(''), keyword = ref(String(route.query.keyword || '')), pageNum = ref(1), pageSize = ref(20)
const gate = createLatestRequest()
async function load() {
  loading.value = true; error.value = ''
  try {
    const result = await gate.run(signal => listBusinessFiles({ pageNum: pageNum.value, pageSize: pageSize.value, keyword: keyword.value || undefined }, { signal }))
    if (result.accepted) { rows.value = result.value?.rows || []; total.value = result.value?.total || 0 }
  } catch (e) { error.value = e.status === 403 ? '你没有查看业务文件的权限' : '文件列表加载失败' }
  finally { loading.value = false }
}
const search = debounce(() => { pageNum.value = 1; load() }, 350)
watch(keyword, search)
async function copyPath(path) {
  try { await navigator.clipboard.writeText(path); ElMessage.success('NAS 路径已复制') }
  catch { ElMessage.error('复制失败，请手动选择路径') }
}
async function downloadFile(row) {
  const blob = await downloadBusinessFile(row.downloadUrl)
  const url = URL.createObjectURL(blob), link = document.createElement('a')
  link.href = url; link.download = row.businessFileName; link.click(); URL.revokeObjectURL(url)
}
onMounted(load); onBeforeUnmount(() => { search.cancel(); gate.cancel() })
</script>
<template>
  <section class="page"><span class="eyebrow">FILES & NAS</span><h1>文件与 NAS</h1><p class="lead">文件通过受保护入口下载；NAS 路径仅支持查看和复制，不提供未经确认的直接打开操作。</p>
    <el-input v-model="keyword" clearable placeholder="搜索文件名、任务或项目" class="search-input" />
    <el-result v-if="error" icon="error" title="无法加载文件" :sub-title="error"><template #extra><el-button type="primary" @click="load">重试</el-button></template></el-result>
    <div v-else v-loading="loading"><EmptyState v-if="!loading && !rows.length" title="暂无业务文件" description="请调整关键词，或确认项目成员权限。" />
      <el-table v-else :data="rows"><el-table-column prop="businessFileName" label="业务文件名" min-width="230"/><el-table-column prop="fileRole" label="用途" width="130"/><el-table-column label="版本" width="90"><template #default="{row}">V{{ String(row.versionNo).padStart(3, '0') }}</template></el-table-column><el-table-column prop="taskName" label="任务" min-width="160"/><el-table-column prop="projectName" label="项目" min-width="150"/><el-table-column prop="nasStatus" label="NAS 状态" width="120"/><el-table-column label="NAS 路径" min-width="220"><template #default="{row}"><template v-if="row.canViewNasPath && row.nasPath"><code>{{ row.nasPath }}</code> <el-button link @click="copyPath(row.nasPath)">复制</el-button></template><span v-else>无权查看</span></template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="primary" @click="downloadFile(row)">下载</el-button></template></el-table-column></el-table>
      <el-pagination v-if="total" v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" :page-sizes="[10,20,50]" layout="total, sizes, prev, pager, next" @change="load" />
    </div>
  </section>
</template>
