<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Refresh, WarningFilled } from '@element-plus/icons-vue'

import { getTaskVersions, getVersionDetail } from '@/api/shot-grid/versions'
import VersionDetailCard from './VersionDetailCard.vue'
import { formatVersionDateTime, versionErrorState, versionStatusMeta } from './versionPresentation'

const props = defineProps({
  taskId: { type: Number, required: true },
  operationGeneration: { type: Number, default: 0 },
  refreshKey: { type: [Number, String], default: 0 },
  pageSize: { type: Number, default: 10 },
  canList: { type: Boolean, default: false },
  canQuery: { type: Boolean, default: false },
  canDownload: { type: Boolean, default: false }
})
const emit = defineEmits(['version-selected'])

const versions = ref([])
const total = ref(0)
const pageNum = ref(1)
const statusFilter = ref('')
const selectedVersionId = ref(null)
const versionDetail = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const listError = ref(null)
const detailError = ref(null)

let disposed = false
let contextGeneration = 0
let listController = null
let detailController = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / props.pageSize)))

function canceled(error, controller) {
  return error?.code === 'ERR_CANCELED' || controller?.signal.aborted
}

function stillCurrent(generation, targetTaskId, targetOperationGeneration) {
  return !disposed &&
    contextGeneration === generation &&
    Number(props.taskId) === targetTaskId &&
    Number(props.operationGeneration) === targetOperationGeneration
}

async function loadDetail(versionId, generation = contextGeneration) {
  detailController?.abort()
  versionDetail.value = null
  detailError.value = null
  const normalizedVersionId = Number(versionId)
  if (!props.canQuery || !normalizedVersionId) return
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const controller = new AbortController()
  detailController = controller
  detailLoading.value = true
  try {
    const response = await getVersionDetail(normalizedVersionId, { signal: controller.signal })
    if (
      detailController !== controller ||
      !stillCurrent(generation, targetTaskId, targetOperationGeneration) ||
      selectedVersionId.value !== normalizedVersionId
    ) return
    if (Number(response.data?.taskId) !== targetTaskId) {
      throw new Error('版本详情与当前任务不匹配')
    }
    versionDetail.value = response.data
    emit('version-selected', response.data, Object.freeze({
      taskId: targetTaskId,
      versionId: normalizedVersionId,
      operationGeneration: targetOperationGeneration
    }))
  } catch (error) {
    if (!canceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      detailError.value = versionErrorState(error, '版本详情加载失败')
    }
  } finally {
    if (detailController === controller) {
      detailController = null
      detailLoading.value = false
    }
  }
}

async function loadVersions({ preserveSelection = true } = {}) {
  listController?.abort()
  detailController?.abort()
  const generation = contextGeneration
  const targetTaskId = Number(props.taskId)
  const targetOperationGeneration = Number(props.operationGeneration)
  const controller = new AbortController()
  listController = controller
  loading.value = true
  listError.value = null
  if (!props.canList) {
    controller.abort()
    if (listController === controller) {
      listController = null
      loading.value = false
    }
    return
  }
  try {
    const params = {
      pageNum: pageNum.value,
      pageSize: props.pageSize,
      orderByColumn: 'versionNo',
      isAsc: 'descending'
    }
    if (statusFilter.value) params.versionStatus = statusFilter.value
    const response = await getTaskVersions(targetTaskId, params, { signal: controller.signal })
    if (listController !== controller || !stillCurrent(generation, targetTaskId, targetOperationGeneration)) return
    const rows = Array.isArray(response.rows) ? response.rows : []
    versions.value = rows
    total.value = Number(response.total || 0)
    const currentStillExists = preserveSelection && rows.some(row => Number(row.versionId) === selectedVersionId.value)
    selectedVersionId.value = currentStillExists ? selectedVersionId.value : Number(rows[0]?.versionId) || null
    if (selectedVersionId.value) await loadDetail(selectedVersionId.value, generation)
    else versionDetail.value = null
  } catch (error) {
    if (!canceled(error, controller) && stillCurrent(generation, targetTaskId, targetOperationGeneration)) {
      versions.value = []
      total.value = 0
      selectedVersionId.value = null
      versionDetail.value = null
      listError.value = versionErrorState(error, '版本历史加载失败')
    }
  } finally {
    if (listController === controller) {
      listController = null
      loading.value = false
    }
  }
}

function selectVersion(versionId) {
  const normalized = Number(versionId)
  if (!normalized || normalized === selectedVersionId.value) return
  selectedVersionId.value = normalized
  loadDetail(normalized)
}

function applyStatusFilter() {
  pageNum.value = 1
  selectedVersionId.value = null
  loadVersions({ preserveSelection: false })
}

function changePage(delta) {
  const next = Math.min(totalPages.value, Math.max(1, pageNum.value + delta))
  if (next === pageNum.value) return
  pageNum.value = next
  loadVersions({ preserveSelection: false })
}

function resetForContext() {
  contextGeneration += 1
  listController?.abort()
  detailController?.abort()
  listController = null
  detailController = null
  loading.value = false
  detailLoading.value = false
  versions.value = []
  total.value = 0
  pageNum.value = 1
  statusFilter.value = ''
  selectedVersionId.value = null
  versionDetail.value = null
  listError.value = null
  detailError.value = null
  loadVersions({ preserveSelection: false })
}

watch(
  () => [props.taskId, props.operationGeneration, props.canList, props.canQuery],
  resetForContext,
  { immediate: true }
)
watch(() => props.refreshKey, () => loadVersions({ preserveSelection: true }))

onBeforeUnmount(() => {
  disposed = true
  contextGeneration += 1
  listController?.abort()
  detailController?.abort()
})
</script>

<template>
  <section class="version-history-panel">
    <header class="history-heading">
      <div><p class="sg-eyebrow">IMMUTABLE HISTORY</p><h3>版本历史</h3><p>版本号由后端分配；修订只新增版本，不覆盖历史文件。</p></div>
      <div class="history-tools">
        <select v-model="statusFilter" aria-label="筛选版本状态" @change="applyStatusFilter">
          <option value="">全部状态</option>
          <option value="pending_review">待审核</option>
          <option value="rejected">已退回</option>
          <option value="final">最终版本</option>
        </select>
        <el-button v-if="canList" :icon="Refresh" :loading="loading" @click="loadVersions()">刷新</el-button>
      </div>
    </header>

    <div v-if="!canList" class="history-error" role="status">
      <el-icon><WarningFilled /></el-icon><div><strong>当前账号没有版本列表权限</strong><p>未发起版本历史请求。</p></div>
    </div>
    <div v-else-if="listError" class="history-error" role="alert">
      <el-icon><WarningFilled /></el-icon><div><strong>{{ listError.title }}</strong><p>{{ listError.message }}</p><code v-if="listError.errorKey">{{ listError.errorKey }}</code></div>
    </div>

    <div class="history-layout">
      <aside class="version-rail" :aria-busy="loading">
        <button
          v-for="version in versions"
          :key="version.versionId"
          type="button"
          :class="{ active: selectedVersionId === Number(version.versionId) }"
          @click="selectVersion(version.versionId)"
        >
          <span><strong>{{ version.versionNumber }}</strong><small>{{ version.submitterName || `用户 #${version.submittedBy}` }}</small></span>
          <em :data-tone="versionStatusMeta(version.versionStatus).tone">{{ versionStatusMeta(version.versionStatus).label }}</em>
          <p>{{ version.changelog }}</p>
          <time>{{ formatVersionDateTime(version.submittedTime) }}</time>
        </button>
        <div v-if="!loading && !versions.length && !listError" class="history-empty">该任务还没有正式版本。</div>
        <div v-if="loading && !versions.length" class="history-empty">正在加载版本历史…</div>
        <footer v-if="total > pageSize">
          <button type="button" :disabled="pageNum <= 1" @click="changePage(-1)">上一页</button>
          <span>{{ pageNum }} / {{ totalPages }}</span>
          <button type="button" :disabled="pageNum >= totalPages" @click="changePage(1)">下一页</button>
        </footer>
      </aside>

      <main class="history-detail">
        <div v-if="detailLoading" class="detail-placeholder">正在加载版本详情…</div>
        <div v-else-if="detailError" class="detail-placeholder is-error" role="alert">
          <strong>{{ detailError.title }}</strong><p>{{ detailError.message }}</p><code v-if="detailError.errorKey">{{ detailError.errorKey }}</code>
        </div>
        <VersionDetailCard v-else-if="versionDetail" :version="versionDetail" :can-download="canDownload" />
        <div v-else-if="!canQuery" class="detail-placeholder">当前账号没有版本详情权限。</div>
        <div v-else class="detail-placeholder">选择左侧版本查看文件和审核单信息。</div>
      </main>
    </div>
  </section>
</template>

<style scoped lang="scss">
.version-history-panel { padding: 24px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-lg); }
.history-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.history-heading h3 { margin: 3px 0 7px; font-size: 20px; }
.history-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.history-tools { display: flex; gap: 9px; }
.history-tools select { padding: 8px 28px 8px 10px; color: var(--sg-text-secondary); background: var(--sg-surface-raised); border: 1px solid var(--sg-border); border-radius: 8px; }
.history-error { display: flex; padding: 13px 15px; margin-top: 16px; color: #ffb5ad; background: rgba(244, 92, 92, 0.08); border-radius: 9px; gap: 10px; }
.history-error strong,
.history-error p { display: block; margin: 0; }
.history-error p { margin-top: 4px; font-size: 11px; }
.history-error code { color: inherit; font-size: 10px; }
.history-layout { display: grid; margin-top: 20px; grid-template-columns: minmax(230px, 0.34fr) minmax(0, 1fr); gap: 14px; }
.version-rail { display: grid; align-content: start; gap: 8px; }
.version-rail > button { display: grid; width: 100%; padding: 14px; color: var(--sg-text); text-align: left; cursor: pointer; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--sg-border); border-radius: 10px; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.version-rail > button:hover,
.version-rail > button.active { background: rgba(255, 182, 87, 0.06); border-color: rgba(255, 182, 87, 0.35); }
.version-rail strong,
.version-rail small { display: block; }
.version-rail strong { font-size: 14px; }
.version-rail small { margin-top: 4px; color: var(--sg-text-muted); font-size: 10px; }
.version-rail em { align-self: start; padding: 4px 7px; color: var(--sg-text-muted); font-size: 9px; font-style: normal; background: rgba(255, 255, 255, 0.04); border-radius: 999px; }
.version-rail em[data-tone='success'] { color: #7ee0ac; }
.version-rail em[data-tone='warning'] { color: #f4c878; }
.version-rail em[data-tone='danger'] { color: #ff9a90; }
.version-rail p { display: -webkit-box; grid-column: 1 / -1; margin: 2px 0 0; overflow: hidden; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.version-rail time { grid-column: 1 / -1; color: var(--sg-text-muted); font-size: 9px; }
.version-rail footer { display: flex; align-items: center; justify-content: space-between; padding: 8px 2px; color: var(--sg-text-muted); font-size: 10px; }
.version-rail footer button { padding: 5px 8px; color: var(--sg-text-secondary); cursor: pointer; background: transparent; border: 1px solid var(--sg-border); border-radius: 7px; }
.version-rail footer button:disabled { cursor: not-allowed; opacity: 0.4; }
.history-empty,
.detail-placeholder { display: grid; min-height: 180px; padding: 24px; color: var(--sg-text-muted); text-align: center; background: rgba(255, 255, 255, 0.018); border: 1px dashed var(--sg-border); border-radius: var(--sg-radius-md); place-items: center; }
.detail-placeholder.is-error { color: #ffb5ad; }
.detail-placeholder p { margin: 5px 0 0; font-size: 11px; }
.detail-placeholder code { font-size: 10px; }

@media (max-width: 900px) {
  .history-heading { align-items: stretch; flex-direction: column; }
  .history-layout { grid-template-columns: 1fr; }
  .version-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .version-rail footer,
  .history-empty { grid-column: 1 / -1; }
}

@media (max-width: 600px) {
  .version-rail { grid-template-columns: 1fr; }
}
</style>
