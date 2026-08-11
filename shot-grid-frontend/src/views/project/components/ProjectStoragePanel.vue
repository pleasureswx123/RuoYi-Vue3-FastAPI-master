<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'

import {
  getProjectStorage,
  getStorageOperationDetail,
  getStorageOperationPage,
  retryProjectStorage,
  retryStorageOperation
} from '@/api/shot-grid/projects'
import { createIdempotencyState } from '@/utils/idempotency'
import {
  canRetryDynamicStorageOperation,
  formatDateTime,
  operationStatusLabel,
  projectErrorState,
  storageMeta
} from '@/views/project/projectPresentation'
import ProjectModal from './ProjectModal.vue'
import ProjectStatePanel from './ProjectStatePanel.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  canDiagnose: { type: Boolean, default: false },
  canRetryProject: { type: Boolean, default: false },
  canRetryOperation: { type: Boolean, default: false }
})
const storage = ref(null)
const operations = ref([])
const total = ref(0)
const loading = ref(false)
const operationsLoading = ref(false)
const storageError = ref(null)
const operationsError = ref(null)
const retryTarget = ref(null)
const retryReason = ref('')
const retryBusy = ref(false)
const retryError = ref(null)
const operationDetail = ref(null)
const detailLoading = ref(false)
const filters = reactive({ pageNum: 1, pageSize: 10, operationStatus: '', operationType: '', orderByColumn: 'createTime', isAsc: 'descending' })
const projectRetryKey = createIdempotencyState('storage-project-retry')
const operationRetryKey = createIdempotencyState('storage-operation-retry')
let storageController = null
let operationsController = null
let detailController = null

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / filters.pageSize)))

async function loadStorage() {
  storageController?.abort()
  storageController = new AbortController()
  loading.value = true
  storageError.value = null
  try {
    const response = await getProjectStorage(props.projectId, { signal: storageController.signal })
    storage.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') storageError.value = projectErrorState(error, '项目存储状态加载失败')
  } finally { loading.value = false }
}

async function loadOperations() {
  if (!props.canDiagnose) return
  operationsController?.abort()
  operationsController = new AbortController()
  operationsLoading.value = true
  operationsError.value = null
  try {
    const response = await getStorageOperationPage(
      props.projectId,
      { ...filters, operationStatus: filters.operationStatus || undefined, operationType: filters.operationType || undefined },
      { signal: operationsController.signal }
    )
    operations.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') operationsError.value = projectErrorState(error, '目录操作诊断加载失败')
  } finally { operationsLoading.value = false }
}

async function refreshAll() {
  await Promise.all([loadStorage(), loadOperations()])
}

async function copyPath() {
  try {
    await navigator.clipboard.writeText(storage.value.projectPathSnapshot)
    ElMessage.success('NAS 路径已复制')
  } catch {
    ElMessage.error('浏览器未允许复制，请手动选择路径文本')
  }
}

function openProjectRetry() {
  retryTarget.value = { type: 'project', id: props.projectId }
  retryReason.value = ''
  retryError.value = null
}

function openOperationRetry(operation) {
  retryTarget.value = { type: 'operation', id: operation.operationId }
  retryReason.value = ''
  retryError.value = null
}

async function submitRetry() {
  const reason = retryReason.value.trim()
  if (!reason) {
    retryError.value = { title: '请填写重试原因', message: '人工重试原因会进入审计记录。' }
    return
  }
  retryBusy.value = true
  retryError.value = null
  try {
    if (retryTarget.value.type === 'project') {
      const payload = { reason, lockVersion: storage.value.lockVersion }
      await retryProjectStorage(props.projectId, payload, projectRetryKey.forPayload(payload))
    } else {
      const payload = { reason }
      await retryStorageOperation(retryTarget.value.id, payload, operationRetryKey.forPayload({ ...payload, operationId: retryTarget.value.id }))
    }
    retryTarget.value = null
    ElMessage.success('目录重试已受理')
    await refreshAll()
  } catch (error) {
    retryError.value = projectErrorState(error, '目录重试受理失败')
  } finally { retryBusy.value = false }
}

async function showOperationDetail(operation) {
  detailController?.abort()
  detailController = new AbortController()
  detailLoading.value = true
  operationsError.value = null
  try {
    const response = await getStorageOperationDetail(props.projectId, operation.operationId, { signal: detailController.signal })
    operationDetail.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') operationsError.value = projectErrorState(error, '目录操作详情加载失败')
  } finally { detailLoading.value = false }
}

function changePage(page) {
  if (page < 1 || page > pageCount.value) return
  filters.pageNum = page
  loadOperations()
}

onMounted(refreshAll)
onBeforeUnmount(() => { storageController?.abort(); operationsController?.abort(); detailController?.abort() })
</script>

<template>
  <section class="detail-panel storage-panel">
    <header class="detail-panel__heading">
      <div><p class="sg-eyebrow">FILE & NAS</p><h2>存储状态与目录诊断</h2><span>浏览器只提供查看和复制 UNC 路径，不假装直接打开共享目录。</span></div>
      <el-button :icon="Refresh" circle aria-label="刷新存储状态" :loading="loading || operationsLoading" @click="refreshAll" />
    </header>

    <ProjectStatePanel v-if="storageError" compact :title="storageError.title" :message="storageError.message" :retryable="storageError.retryable" @retry="loadStorage" />
    <div v-else-if="storage" class="storage-summary">
      <div><span class="storage-dot" :data-tone="storageMeta(storage.storageStatus).tone"></span><strong>{{ storageMeta(storage.storageStatus).label }}</strong><small>更新于 {{ formatDateTime(storage.updateTime) }}</small></div>
      <div v-if="storage.projectPathSnapshot" class="storage-path"><code>{{ storage.projectPathSnapshot }}</code><el-button text :icon="CopyDocument" @click="copyPath">复制路径</el-button></div>
      <div v-if="storage.lastErrorMessage" class="storage-error"><strong>{{ storage.lastErrorKey || 'STORAGE_ERROR' }}</strong><span>{{ storage.lastErrorMessage }}</span></div>
      <el-button v-if="canRetryProject && storage.storageStatus === 'failed'" type="warning" @click="openProjectRetry">重试项目初始目录</el-button>
    </div>
    <p v-else class="panel-muted">正在读取项目存储状态…</p>

    <template v-if="canDiagnose">
      <div class="operation-toolbar">
        <strong>目录操作记录</strong>
        <select v-model="filters.operationStatus" aria-label="目录操作状态" @change="filters.pageNum = 1; loadOperations()">
          <option value="">全部状态</option><option value="pending">等待执行</option><option value="processing">执行中</option><option value="succeeded">成功</option><option value="retry_wait">等待重试</option><option value="failed">失败</option><option value="compensation_pending">等待补偿</option><option value="compensated">已补偿</option><option value="compensation_failed">补偿失败</option>
        </select>
        <select v-model="filters.operationType" aria-label="目录操作类型" @change="filters.pageNum = 1; loadOperations()">
          <option value="">全部类型</option><option value="initialize_project">项目初始化</option><option value="ensure_episode_directory">集目录</option><option value="ensure_shot_directory">镜头目录</option><option value="ensure_asset_directory">资产目录</option><option value="reconcile_directory">目录对账</option>
        </select>
      </div>
      <ProjectStatePanel v-if="operationsError" compact :title="operationsError.title" :message="operationsError.message" :retryable="operationsError.retryable" @retry="loadOperations" />
      <p v-else-if="operationsLoading && !operations.length" class="panel-muted">正在加载目录操作…</p>
      <p v-else-if="!operations.length" class="panel-muted">当前筛选范围没有目录操作记录。</p>
      <div v-else class="operation-list">
        <article v-for="operation in operations" :key="operation.operationId">
          <button class="operation-main" type="button" @click="showOperationDetail(operation)">
            <span><strong>#{{ operation.operationId }} · {{ operationStatusLabel(operation.operationStatus) }}</strong><small>{{ operation.operationType }} · {{ operation.targetRelativePath }}</small></span>
            <span><strong>尝试 {{ operation.attemptCount }} 次</strong><small>{{ formatDateTime(operation.updateTime) }}</small></span>
          </button>
          <el-button v-if="canRetryOperation && canRetryDynamicStorageOperation(operation)" text type="warning" @click="openOperationRetry(operation)">人工重试</el-button>
        </article>
      </div>
      <nav v-if="total > filters.pageSize" class="operation-pagination"><el-button :disabled="filters.pageNum <= 1" @click="changePage(filters.pageNum - 1)">上一页</el-button><span>{{ filters.pageNum }} / {{ pageCount }}</span><el-button :disabled="filters.pageNum >= pageCount" @click="changePage(filters.pageNum + 1)">下一页</el-button></nav>
    </template>
    <p v-else class="diagnostic-note">目录操作诊断仅对项目总监或跨项目管理员开放。</p>

    <ProjectModal v-if="retryTarget" title="人工重试目录操作" description="重试会创建新的目录操作记录，不覆盖原失败记录。" :busy="retryBusy" @close="retryTarget = null">
      <form class="retry-form" @submit.prevent="submitRetry"><label><span>重试原因 *</span><textarea v-model="retryReason" rows="4" maxlength="500" /></label><div v-if="retryError" class="inline-error" role="alert"><strong>{{ retryError.title }}</strong><span>{{ retryError.message }}</span><el-button v-if="retryError.status === 409" text @click="retryTarget = null; refreshAll()">刷新最新状态</el-button></div><footer><el-button :disabled="retryBusy" @click="retryTarget = null">取消</el-button><el-button type="primary" native-type="submit" :loading="retryBusy">提交重试</el-button></footer></form>
    </ProjectModal>

    <ProjectModal v-if="operationDetail" title="目录操作详情" @close="operationDetail = null">
      <dl class="operation-detail"><div><dt>操作 ID</dt><dd>{{ operationDetail.operationId }}</dd></div><div><dt>状态</dt><dd>{{ operationStatusLabel(operationDetail.operationStatus) }}</dd></div><div><dt>目标相对路径</dt><dd>{{ operationDetail.targetRelativePath }}</dd></div><div><dt>执行次数</dt><dd>{{ operationDetail.attemptCount }}</dd></div><div><dt>开始时间</dt><dd>{{ formatDateTime(operationDetail.startedTime) }}</dd></div><div><dt>完成时间</dt><dd>{{ formatDateTime(operationDetail.completedTime) }}</dd></div><div v-if="operationDetail.lastErrorMessage"><dt>最近错误</dt><dd>{{ operationDetail.lastErrorKey }} · {{ operationDetail.lastErrorMessage }}</dd></div></dl>
    </ProjectModal>
    <span v-if="detailLoading" class="sr-only" role="status">正在加载目录操作详情</span>
  </section>
</template>

<style scoped>
.detail-panel { padding:24px; background:var(--sg-surface); border:1px solid var(--sg-border); border-radius:var(--sg-radius-lg); }
.detail-panel__heading { display:flex; gap:16px; align-items:flex-start; justify-content:space-between; margin-bottom:20px; }
.detail-panel__heading h2, .detail-panel__heading span { margin:0; }
.detail-panel__heading h2 { font-size:19px; }
.detail-panel__heading span { display:block; margin-top:6px; color:var(--sg-text-muted); font-size:12px; }
.storage-summary { display:grid; gap:14px; padding:18px; background:rgba(255,255,255,.025); border:1px solid var(--sg-border); border-radius:12px; }
.storage-summary > div:first-child { display:flex; gap:9px; align-items:center; }
.storage-summary small { color:var(--sg-text-muted); font-size:11px; }
.storage-dot { width:8px; height:8px; background:var(--sg-text-muted); border-radius:50%; }.storage-dot[data-tone='success']{background:var(--sg-success)}.storage-dot[data-tone='warning']{background:var(--sg-accent)}.storage-dot[data-tone='danger']{background:var(--sg-danger)}
.storage-path { display:flex; gap:12px; align-items:center; justify-content:space-between; padding:10px 12px; background:rgba(0,0,0,.2); border-radius:9px; }.storage-path code{overflow-wrap:anywhere;color:var(--sg-text-secondary);font-size:12px}
.storage-error,.inline-error { display:grid;gap:5px;padding:12px;color:#ffb4b4;font-size:12px;background:rgba(255,107,107,.08);border-radius:9px }
.operation-toolbar { display:flex; gap:10px; align-items:center; margin:24px 0 12px; }.operation-toolbar strong{margin-right:auto}.operation-toolbar select{height:36px;padding:0 9px;color:var(--sg-text-secondary);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:8px}
.operation-list { display:grid; gap:8px; }.operation-list article{display:flex;gap:10px;align-items:center;padding:9px 12px;background:rgba(255,255,255,.02);border:1px solid var(--sg-border);border-radius:10px}
.operation-main{display:flex;min-width:0;flex:1;gap:20px;align-items:center;justify-content:space-between;color:var(--sg-text);text-align:left;cursor:pointer;background:transparent;border:0}.operation-main span{min-width:0}.operation-main strong,.operation-main small{display:block}.operation-main strong{font-size:12px}.operation-main small{margin-top:4px;overflow:hidden;color:var(--sg-text-muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}
.operation-pagination{display:flex;gap:12px;align-items:center;justify-content:center;margin-top:14px;color:var(--sg-text-muted);font-size:11px}.panel-muted,.diagnostic-note{padding:24px;color:var(--sg-text-muted);font-size:12px;text-align:center}.diagnostic-note{margin:18px 0 0;padding:12px;background:rgba(255,255,255,.02);border-radius:8px}
.retry-form,.retry-form label{display:grid;gap:8px}.retry-form{gap:18px}.retry-form label span{font-size:13px;font-weight:600}.retry-form textarea{padding:12px;color:var(--sg-text);resize:vertical;background:rgba(255,255,255,.035);border:1px solid var(--sg-border-strong);border-radius:10px}.retry-form footer{display:flex;gap:10px;justify-content:flex-end}
.operation-detail{display:grid;gap:0;margin:0}.operation-detail div{display:grid;grid-template-columns:130px 1fr;gap:12px;padding:11px 0;border-bottom:1px solid var(--sg-border)}.operation-detail dt{color:var(--sg-text-muted);font-size:11px}.operation-detail dd{margin:0;overflow-wrap:anywhere;color:var(--sg-text-secondary);font-size:12px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:680px){.operation-toolbar,.operation-main,.storage-path{align-items:stretch;flex-direction:column}.operation-toolbar strong{margin-right:0}.operation-main span:last-child{text-align:left}}
</style>
