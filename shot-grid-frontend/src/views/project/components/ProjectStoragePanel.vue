<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'

import {
  getProjectStorage,
  getStorageOperationDetail,
  getStorageOperationPage,
  retryProjectStorage,
  retryStorageOperation
} from '@/api/shot-grid/projects'
import { copyTextToClipboard } from '@/utils/clipboard'
import { createIdempotencyState } from '@/utils/idempotency'
import { tagTypeFromTone } from '@/utils/tag'
import {
  canRetryDynamicStorageOperation,
  formatDateTime,
  operationStatusLabel,
  operationStatusMeta,
  operationTypeMeta,
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
const retryFormRef = ref(null)
const operationFilterFormRef = ref(null)
const retryForm = reactive({ reason: '' })
const retryBusy = ref(false)
const retryError = ref(null)
const operationDetail = ref(null)
const operationDetailTarget = ref(null)
const operationDetailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref(null)
const filters = reactive({ pageNum: 1, pageSize: 10, operationStatus: '', operationType: '', orderByColumn: 'createTime', isAsc: 'descending' })
const projectRetryKey = createIdempotencyState('storage-project-retry')
const operationRetryKey = createIdempotencyState('storage-operation-retry')
const retryRules = {
  reason: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (!normalized) callback(new Error('请填写重试原因'))
      else if (normalized.length > 500) callback(new Error('重试原因不能超过 500 个字符'))
      else callback()
    },
    trigger: 'change'
  }]
}
let storageController = null
let operationsController = null
let detailController = null

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
    if (error?.code !== 'ERR_CANCELED') operationsError.value = projectErrorState(error, '目录操作记录加载失败')
  } finally { operationsLoading.value = false }
}

async function refreshAll() {
  await Promise.all([loadStorage(), loadOperations()])
}

async function copyPath() {
  const copied = await copyTextToClipboard(storage.value?.projectPathSnapshot)
  if (copied) ElMessage.success('NAS 路径已复制')
  else ElMessage.error('复制未成功，请手动选择并复制路径')
}

function openProjectRetry() {
  retryTarget.value = { type: 'project', id: props.projectId }
  retryForm.reason = ''
  retryError.value = null
}

function openOperationRetry(operation) {
  retryTarget.value = { type: 'operation', id: operation.operationId }
  retryForm.reason = ''
  retryError.value = null
}

function closeRetryDialog() {
  retryFormRef.value?.resetFields()
  retryTarget.value = null
  retryError.value = null
}

async function submitRetry() {
  if (retryBusy.value || !retryTarget.value) return
  retryError.value = null
  retryBusy.value = true
  try {
    const isValid = retryFormRef.value
      ? await retryFormRef.value.validate().catch(() => false)
      : false
    const target = retryTarget.value
    if (!isValid || !target) return

    const reason = retryForm.reason.trim()
    if (target.type === 'project') {
      const payload = { reason, lockVersion: storage.value.lockVersion }
      await retryProjectStorage(props.projectId, payload, projectRetryKey.forPayload(payload))
    } else {
      const payload = { reason }
      await retryStorageOperation(target.id, payload, operationRetryKey.forPayload({ ...payload, operationId: target.id }))
    }
    closeRetryDialog()
    ElMessage.success('目录重试已受理')
    await refreshAll()
  } catch (error) {
    retryError.value = projectErrorState(error, '目录重试受理失败')
  } finally { retryBusy.value = false }
}

async function showOperationDetail(operation) {
  detailController?.abort()
  detailController = new AbortController()
  operationDetailTarget.value = operation
  operationDetail.value = null
  detailError.value = null
  operationDetailVisible.value = true
  detailLoading.value = true
  try {
    const response = await getStorageOperationDetail(props.projectId, operation.operationId, { signal: detailController.signal })
    operationDetail.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') detailError.value = projectErrorState(error, '目录操作详情加载失败')
  } finally { detailLoading.value = false }
}

function changePage(page) {
  filters.pageNum = page
  loadOperations()
}

function closeOperationDetail() {
  detailController?.abort()
  detailLoading.value = false
  operationDetailVisible.value = false
  operationDetail.value = null
  operationDetailTarget.value = null
  detailError.value = null
}

onMounted(refreshAll)
onBeforeUnmount(() => { storageController?.abort(); operationsController?.abort(); detailController?.abort() })
</script>

<template>
  <el-card class="detail-panel storage-panel" shadow="never">
    <template #header>
      <header class="detail-panel__heading">
        <div><p class="sg-eyebrow">FILE & NAS</p><h2>项目存储与目录状态</h2><span>可在此查看或复制项目 NAS 路径，并跟踪目录创建与重试记录。</span></div>
        <el-button :icon="Refresh" circle aria-label="刷新存储状态" :loading="loading || operationsLoading" @click="refreshAll" />
      </header>
    </template>

    <ProjectStatePanel v-if="storageError" compact :title="storageError.title" :message="storageError.message" :retryable="storageError.retryable" @retry="loadStorage" />
    <el-skeleton v-else-if="loading && !storage" :rows="3" animated />
    <el-card v-else-if="storage" class="storage-summary" shadow="never">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="存储状态"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(storageMeta(storage.storageStatus).tone)">{{ storageMeta(storage.storageStatus).label }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="最后更新">{{ formatDateTime(storage.updateTime) }}</el-descriptions-item>
        <el-descriptions-item v-if="storage.projectPathSnapshot" label="项目路径" :span="2">
          <div class="storage-path"><code>{{ storage.projectPathSnapshot }}</code><el-button text :icon="CopyDocument" @click="copyPath">复制路径</el-button></div>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="storage.lastErrorMessage" title="项目存储异常" :description="storage.lastErrorMessage" type="error" show-icon :closable="false" />
      <el-button v-if="canRetryProject && storage.storageStatus === 'failed'" type="warning" @click="openProjectRetry">重试项目初始目录</el-button>
    </el-card>
    <el-empty v-else :image-size="64" description="当前项目尚无存储信息" />

    <template v-if="canDiagnose">
      <el-form ref="operationFilterFormRef" :model="filters" class="operation-toolbar" size="large" inline aria-label="目录操作筛选">
        <strong>目录操作记录</strong>
        <el-form-item prop="operationStatus">
          <el-select v-model="filters.operationStatus" class="sg-select" placeholder="全部状态" aria-label="目录操作状态" @change="filters.pageNum = 1; loadOperations()">
            <el-option label="全部状态" value="" /><el-option label="等待执行" value="pending" /><el-option label="执行中" value="processing" /><el-option label="成功" value="succeeded" /><el-option label="等待重试" value="retry_wait" /><el-option label="失败" value="failed" /><el-option label="等待恢复" value="compensation_pending" /><el-option label="已恢复" value="compensated" /><el-option label="恢复失败" value="compensation_failed" />
          </el-select>
        </el-form-item>
        <el-form-item prop="operationType">
          <el-select v-model="filters.operationType" class="sg-select" placeholder="全部类型" aria-label="目录操作类型" @change="filters.pageNum = 1; loadOperations()">
            <el-option label="全部类型" value="" /><el-option label="项目初始化" value="initialize_project" /><el-option label="集目录" value="ensure_episode_directory" /><el-option label="镜头目录" value="ensure_shot_directory" /><el-option label="资产目录" value="ensure_asset_directory" /><el-option label="目录核验" value="reconcile_directory" />
          </el-select>
        </el-form-item>
      </el-form>
      <ProjectStatePanel v-if="operationsError" compact :title="operationsError.title" :message="operationsError.message" :retryable="operationsError.retryable" @retry="loadOperations" />
      <template v-else>
        <el-table class="operation-table" :data="operations" row-key="operationId" v-loading="operationsLoading" empty-text="当前筛选范围没有目录操作记录">
          <el-table-column label="操作 ID" width="105"><template #default="{ row }"><el-button link type="primary" @click="showOperationDetail(row)">#{{ row.operationId }}</el-button></template></el-table-column>
          <el-table-column label="类型" min-width="135"><template #default="{ row }"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(operationTypeMeta(row.operationType).tone)">{{ operationTypeMeta(row.operationType).label }}</el-tag></template></el-table-column>
          <el-table-column label="状态" min-width="120"><template #default="{ row }"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(operationStatusMeta(row.operationStatus).tone)">{{ operationStatusLabel(row.operationStatus) }}</el-tag></template></el-table-column>
          <el-table-column label="目标相对路径" min-width="240" show-overflow-tooltip prop="targetRelativePath" />
          <el-table-column label="执行次数" width="95" align="center"><template #default="{ row }">{{ row.attemptCount }}</template></el-table-column>
          <el-table-column label="更新时间" min-width="170"><template #default="{ row }">{{ formatDateTime(row.updateTime) }}</template></el-table-column>
          <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="showOperationDetail(row)">详情</el-button><el-button v-if="canRetryOperation && canRetryDynamicStorageOperation(row)" text type="warning" @click="openOperationRetry(row)">人工重试</el-button></template></el-table-column>
        </el-table>
        <el-pagination v-if="total > filters.pageSize" class="operation-pagination" background layout="total, prev, pager, next" :current-page="filters.pageNum" :page-size="filters.pageSize" :total="total" :disabled="operationsLoading" @current-change="changePage" />
      </template>
    </template>
    <el-alert v-else class="diagnostic-note" title="目录操作记录仅对项目管理人或跨项目管理员开放" type="info" show-icon :closable="false" />

    <ProjectModal v-if="retryTarget" title="人工重试目录操作" description="重试后会新增一条操作记录，原失败记录将继续保留。" :busy="retryBusy" @close="closeRetryDialog">
      <el-form ref="retryFormRef" :model="retryForm" :rules="retryRules" class="retry-form" label-position="top">
        <el-form-item label="重试原因" prop="reason" required><el-input v-model="retryForm.reason" type="textarea" :rows="4" maxlength="500" show-word-limit /></el-form-item>
        <el-alert v-if="retryError" :title="retryError.title" type="error" show-icon :closable="false"><span>{{ retryError.message }}</span><el-button v-if="retryError.status === 409" link type="danger" @click="closeRetryDialog(); refreshAll()">刷新最新状态</el-button></el-alert>
        <footer><el-button :disabled="retryBusy" @click="closeRetryDialog">取消</el-button><el-button type="primary" :loading="retryBusy" @click="submitRetry">提交重试</el-button></footer>
      </el-form>
    </ProjectModal>

    <ProjectModal v-if="operationDetailVisible" title="目录操作详情" @close="closeOperationDetail">
      <el-skeleton v-if="detailLoading" :rows="6" animated />
      <el-alert v-else-if="detailError" :title="detailError.title" type="error" show-icon :closable="false"><span>{{ detailError.message }}</span><el-button v-if="detailError.retryable && operationDetailTarget" link type="danger" @click="showOperationDetail(operationDetailTarget)">重新加载</el-button></el-alert>
      <el-descriptions v-else-if="operationDetail" class="operation-detail" :column="1" border>
        <el-descriptions-item label="操作 ID">{{ operationDetail.operationId }}</el-descriptions-item>
        <el-descriptions-item label="操作类型"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(operationTypeMeta(operationDetail.operationType).tone)">{{ operationTypeMeta(operationDetail.operationType).label }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(operationStatusMeta(operationDetail.operationStatus).tone)">{{ operationStatusLabel(operationDetail.operationStatus) }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="目标相对路径">{{ operationDetail.targetRelativePath }}</el-descriptions-item>
        <el-descriptions-item label="执行次数">{{ operationDetail.attemptCount }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatDateTime(operationDetail.startedTime) }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ formatDateTime(operationDetail.completedTime) }}</el-descriptions-item>
        <el-descriptions-item v-if="operationDetail.lastErrorMessage" label="最近错误">{{ operationDetail.lastErrorMessage }}</el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="目录操作详情不可用" />
    </ProjectModal>
  </el-card>
</template>

<style scoped>
.detail-panel { background:var(--sg-surface); border-color:var(--sg-border); border-radius:var(--sg-radius-lg); }
.detail-panel :deep(.el-card__header){padding:20px 24px;border-bottom-color:var(--sg-border)}.detail-panel :deep(.el-card__body){display:grid;gap:16px;padding:20px 24px 24px}
.detail-panel__heading { display:flex; gap:16px; align-items:flex-start; justify-content:space-between; }
.detail-panel__heading h2, .detail-panel__heading span { margin:0; }
.detail-panel__heading h2 { font-size:19px; }
.detail-panel__heading span { display:block; margin-top:6px; color:var(--sg-text-muted); font-size:12px; }
.storage-summary { background:rgba(255,255,255,.025); border-color:var(--sg-border); border-radius:12px; }.storage-summary :deep(.el-card__body){display:grid;gap:14px;padding:16px}
.storage-path { display:flex; gap:12px; align-items:center; justify-content:space-between; }.storage-path code{overflow-wrap:anywhere;color:var(--sg-text-secondary);font-size:12px}
.operation-toolbar { display:flex; gap:10px; align-items:center; margin-top:8px; }.operation-toolbar strong{margin-right:auto}.operation-toolbar .sg-select{width:180px}.operation-toolbar :deep(.el-form-item){margin:0}
.operation-table{--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);--el-table-border-color:var(--sg-border);width:100%}
.operation-pagination{justify-content:flex-end}.diagnostic-note{margin-top:2px}
.retry-form{display:grid;gap:18px}.retry-form :deep(.el-form-item){margin-bottom:0}.retry-form :deep(.el-textarea__inner){resize:vertical}.retry-form footer{display:flex;gap:10px;justify-content:flex-end}
.operation-detail{width:100%}
@media(max-width:680px){.operation-toolbar,.storage-path{align-items:stretch;flex-direction:column}.operation-toolbar strong{margin-right:0}.operation-toolbar .sg-select{width:100%}}
</style>
