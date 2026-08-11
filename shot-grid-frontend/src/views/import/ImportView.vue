<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { commitImport, getImportBatch, previewImport } from '@/api/shot-grid/imports'
import { getErrorDetails } from '@/utils/requestErrors'
import { classifyImportCommitError, getLastCommittedBatch, getOrCreateImportOperation, rowIdentity, saveLastCommittedBatch, selectableRows, toSelectedRows } from '@/utils/importWorkflow'

const props = defineProps({ projectId: { type: String, required: true }, importType: { type: String, required: true } })
const route = useRoute()
const file = ref(null), preview = ref(null), result = ref(null), progress = ref(0), busy = ref(false)
const selectedKeys = ref([]), pageError = ref(''), conflict = ref(''), tokenExpired = ref(false)
const isShot = computed(() => props.importType === 'shot')
const availableRows = computed(() => selectableRows(preview.value?.rows || []))
const selectedRows = computed(() => availableRows.value.filter((row) => selectedKeys.value.includes(rowIdentity(row))))
const allSelected = computed(() => availableRows.value.length > 0 && selectedRows.value.length === availableRows.value.length)

const displayValue = (value) => value == null || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
const issueText = (issues) => issues?.map((issue) => issue.message).join('；') || '—'

function chooseFile(uploadFile) {
  file.value = uploadFile.raw
  preview.value = null; result.value = null; progress.value = 0; selectedKeys.value = []
  pageError.value = ''; conflict.value = ''; tokenExpired.value = false
}

async function runPreview() {
  if (!file.value) return ElMessage.warning('请先选择 .xlsx 文件')
  busy.value = true; pageError.value = ''; tokenExpired.value = false; conflict.value = ''
  try {
    preview.value = await previewImport(props.projectId, props.importType, file.value, ({ loaded, total }) => {
      progress.value = total ? Math.round(loaded / total * 100) : 0
    })
    selectedKeys.value = availableRows.value.map(rowIdentity)
  } catch (error) { pageError.value = getErrorDetails(error).message } finally { busy.value = false }
}

function toggleAll(value) { selectedKeys.value = value ? availableRows.value.map(rowIdentity) : [] }

async function runCommit() {
  if (!selectedRows.value.length) return ElMessage.warning('至少选择一条可提交记录')
  const rows = toSelectedRows(selectedRows.value)
  const operation = getOrCreateImportOperation(localStorage, {
    projectId: props.projectId, importType: props.importType, batchId: preview.value.batchId, selectedRows: rows
  })
  // operation 持久化后才发请求；超时或断网后的再次点击会继续使用完全相同的键和选择集。
  busy.value = true; pageError.value = ''; conflict.value = ''
  try {
    result.value = await commitImport(props.projectId, props.importType, preview.value.importToken, operation.selectedRows, operation.idempotencyKey)
    saveLastCommittedBatch(localStorage, props.projectId, result.value.batchId || preview.value.batchId)
  } catch (error) {
    const details = getErrorDetails(error)
    const classification = classifyImportCommitError(details)
    tokenExpired.value = classification.tokenExpired
    if (classification.conflict) conflict.value = `${details.errorKey ? `[${details.errorKey}] ` : ''}${details.message}`
    else pageError.value = details.message
  } finally { busy.value = false }
}

async function restoreResult() {
  const batchId = Number(route.query.batchId) || getLastCommittedBatch(localStorage, props.projectId)
  if (!batchId) return
  try {
    const batch = await getImportBatch(props.projectId, batchId)
    result.value = batch.resultSummary || batch.result || (batch.batchStatus === 'committed' ? batch : null)
  } catch (error) { pageError.value = `无法恢复导入结果：${getErrorDetails(error).message}` }
}

onMounted(restoreResult)
</script>

<template>
  <section class="page import-page">
    <header class="page-heading"><div><span class="eyebrow">EXCEL IMPORT</span><h1>{{ isShot ? '镜头' : '资产' }}导入</h1><p class="lead">先预检、确认每条物理记录，再以一个事务正式提交。</p></div></header>
    <el-alert v-if="isShot" type="info" :closable="false" show-icon title="镜头模板规则：每个可见 Sheet 表示一集，Sheet 名使用 EP001 格式；只解析从 A1 开始、遇到首个空表头结束的连续主数据区（当前模板 A:P）。" />
    <el-alert v-else type="info" :closable="false" show-icon title="资产模板规则：解析从 A1 开始的连续主数据区；制作分项缺失是警告，仍允许选择并提交。" />
    <div class="import-upload">
      <el-upload :auto-upload="false" :limit="1" accept=".xlsx" :on-change="chooseFile" :on-remove="chooseFile"><el-button>选择 Excel</el-button></el-upload>
      <el-button type="primary" :loading="busy" :disabled="!file" @click="runPreview">开始预检</el-button>
      <el-progress v-if="progress" :percentage="progress" />
    </div>
    <el-alert v-if="tokenExpired" type="error" :closable="false" show-icon title="Preview Token 已过期，请重新选择文件并执行预检后再提交。" />
    <el-alert v-if="conflict" type="warning" :closable="false" show-icon :title="`数据库状态冲突：${conflict}`" />
    <el-alert v-if="pageError" type="error" :closable="false" show-icon :title="pageError" />

    <template v-if="preview">
      <div class="summary-strip"><b>总行数 {{ preview.summary.totalRows }}</b><span>可提交 {{ preview.summary.validRows }}</span><span>警告 {{ preview.summary.warningRows }}</span><span>错误 {{ preview.summary.errorRows }}</span><span>Token 到期：{{ preview.expiresAt }}</span></div>
      <el-alert v-for="warning in preview.workbookWarnings" :key="warning.errorKey + warning.message" type="warning" :closable="false" :title="warning.message" />
      <div class="selection-actions"><el-checkbox :model-value="allSelected" @change="toggleAll">选择全部可提交行</el-checkbox><span>已选 {{ selectedRows.length }} 行；错误行始终不可选择</span></div>
      <el-table :data="preview.rows" row-key="rowKey" border>
        <el-table-column label="选择" width="68"><template #default="{ row }"><el-checkbox v-model="selectedKeys" :value="rowIdentity(row)" :disabled="!row.canImport || !!row.errors?.length" /></template></el-table-column>
        <el-table-column prop="sheetName" label="Sheet" width="100"/><el-table-column prop="rowNumber" label="Excel 物理行" width="110"/>
        <el-table-column label="原始值" min-width="220"><template #default="{ row }"><pre>{{ displayValue(row.rawValues || row.raw || row.originalValues) }}</pre></template></el-table-column>
        <el-table-column label="规范化值" min-width="280"><template #default="{ row }"><pre>{{ displayValue(row.normalized) }}</pre></template></el-table-column>
        <el-table-column label="错误" min-width="180"><template #default="{ row }"><span class="issue issue--error">{{ issueText(row.errors) }}</span></template></el-table-column>
        <el-table-column label="警告" min-width="180"><template #default="{ row }"><span class="issue issue--warning">{{ issueText(row.warnings) }}</span></template></el-table-column>
      </el-table>
      <div class="commit-bar"><span>正式提交采用全事务：任一选中行失败将全部回滚。</span><el-button type="primary" :loading="busy" :disabled="!selectedRows.length || tokenExpired" @click="runCommit">提交 {{ selectedRows.length }} 行</el-button></div>
    </template>

    <el-result v-if="result" icon="success" title="导入结果已持久化" :sub-title="`批次 ${result.batchId}`">
      <template #extra><router-link v-if="!isShot" :to="`/projects/${projectId}/asset-requirements`"><el-button type="primary" plain>处理待匹配需求</el-button></router-link><div v-if="!isShot" class="result-grid"><b>新增资产 {{ Object.values(result.createdAssetsByType || {}).reduce((a, b) => a + b, 0) }}</b><span>制作分项 {{ result.createdAssetItems || 0 }}</span><span>唯一自动匹配 {{ result.autoMatchedRequirements || 0 }}</span><span>待匹配 {{ result.pendingRequirements || 0 }}</span><span>冲突 {{ result.conflictRequirements || 0 }}</span></div><div v-else>新增镜头 {{ result.createdShots || 0 }} · 提交 {{ result.committedRows || 0 }} 行<span v-if="result.idempotentReplay">（幂等重放）</span></div></template>
    </el-result>
  </section>
</template>
