<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { Document, UploadFilled } from '@element-plus/icons-vue'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import { createIdempotencyState } from '@/utils/idempotency'
import { tagTypeFromTone } from '@/utils/tag'
import { assetErrorState, assetTypeMeta, groupAssetPreviewRows } from '@/views/asset/assetPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import AssetDescriptionCell from '@/views/asset/components/AssetDescriptionCell.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  projectName: { type: String, default: '' }
})
const emit = defineEmits(['close', 'imported'])
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  operationGeneration: Number(props.operationGeneration)
})
const idempotency = createIdempotencyState(`asset-import-${operationContext.projectId}`)
const file = ref(null)
const preview = ref(null)
const selectedKeys = ref(new Set())
const uploadRef = ref(null)
const previewing = ref(false)
const committing = ref(false)
const downloading = ref(false)
const validationMessage = ref('')
const requestError = ref(null)
const commitResult = ref(null)
let previewController = null
let downloadController = null
let fileGeneration = 0
let syncingTableSelection = false
const previewTableRefs = new Map()

const groupedRows = computed(() => groupAssetPreviewRows(preview.value?.rows || []))
const selectedRows = computed(() => (preview.value?.rows || [])
  .filter(row => selectedKeys.value.has(rowKey(row)))
  .filter(row => row.canImport)
  .map(row => ({ sheetName: row.sheetName, rowNumber: row.rowNumber })))
const validRows = computed(() => (preview.value?.rows || []).filter(row => row.canImport))
const isBusy = computed(() => previewing.value || committing.value)
const typeSummary = computed(() => Object.entries(preview.value?.summary?.byType || {}))

function rowKey(row) {
  return `${row.sheetName}::${row.rowNumber}`
}

function rowCanSelect(row) {
  return Boolean(row.canImport)
}

function visibleWarnings(row) {
  return row.warnings || []
}

function visibleErrors(row) {
  return row.errors || []
}

function setPreviewTableRef(sheetName, instance) {
  if (instance) previewTableRefs.set(sheetName, instance)
  else previewTableRefs.delete(sheetName)
}

function handleSheetSelection(rows, selection) {
  if (syncingTableSelection) return
  const sheetKeys = new Set(rows.map(row => rowKey(row)))
  const next = new Set([...selectedKeys.value].filter(key => !sheetKeys.has(key)))
  selection.filter(row => rowCanSelect(row)).forEach(row => next.add(rowKey(row)))
  if (next.size === selectedKeys.value.size && [...next].every(key => selectedKeys.value.has(key))) return
  selectedKeys.value = next
}

async function syncPreviewTableSelections() {
  await nextTick()
  syncingTableSelection = true
  try {
    Object.entries(groupedRows.value).forEach(([sheetName, rows]) => {
      const table = previewTableRefs.get(sheetName)
      if (!table) return
      table.clearSelection()
      rows.filter(row => selectedKeys.value.has(rowKey(row))).forEach(row => table.toggleRowSelection(row, true))
    })
  } finally {
    syncingTableSelection = false
  }
}

function previewRowClass({ row }) {
  if (visibleErrors(row).length) return 'has-errors'
  if (visibleWarnings(row).length) return 'has-warnings'
  return ''
}

function resetPreview() {
  previewController?.abort()
  preview.value = null
  selectedKeys.value = new Set()
  previewTableRefs.clear()
  requestError.value = null
  validationMessage.value = ''
  commitResult.value = null
  idempotency.reset()
}

function chooseFile(uploadFile) {
  fileGeneration += 1
  resetPreview()
  const nextFile = uploadFile?.raw || uploadFile?.target?.files?.[0] || null
  if (!nextFile) {
    file.value = null
    return
  }
  if (!/\.xlsx$/i.test(nextFile.name)) {
    validationMessage.value = '资产导入只接受 .xlsx 工作簿'
    uploadRef.value?.clearFiles()
    file.value = null
    return
  }
  if (nextFile.size > 10 * 1024 * 1024) {
    validationMessage.value = 'Excel 文件不能超过 10 MiB'
    uploadRef.value?.clearFiles()
    file.value = null
    return
  }
  file.value = nextFile
  void nextTick(() => uploadRef.value?.clearFiles())
}

function clearSelectedFile() {
  fileGeneration += 1
  resetPreview()
  file.value = null
  uploadRef.value?.clearFiles()
}

async function runPreview() {
  validationMessage.value = ''
  requestError.value = null
  commitResult.value = null
  if (!file.value) {
    validationMessage.value = '请先选择资产 Excel 文件'
    return
  }
  previewController?.abort()
  preview.value = null
  selectedKeys.value = new Set()
  idempotency.reset()
  const controller = new AbortController()
  const targetFile = file.value
  const targetGeneration = fileGeneration
  previewController = controller
  previewing.value = true
  try {
    const response = await previewAssetImport(operationContext.projectId, targetFile, { signal: controller.signal })
    if (previewController !== controller || controller.signal.aborted || file.value !== targetFile || fileGeneration !== targetGeneration) return
    preview.value = response.data
    selectedKeys.value = new Set((response.data?.rows || []).filter(row => row.canImport).map(row => rowKey(row)))
    await syncPreviewTableSelections()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && fileGeneration === targetGeneration) {
      requestError.value = assetErrorState(error, '资产 Excel 预览失败')
    }
  } finally {
    if (previewController === controller) previewing.value = false
  }
}

async function downloadTemplate() {
  requestError.value = null
  downloadController?.abort()
  const controller = new AbortController()
  downloadController = controller
  downloading.value = true
  let objectUrl = null
  try {
    const blob = await downloadAssetImportTemplate({ signal: controller.signal })
    if (downloadController !== controller || controller.signal.aborted) return
    objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = '资产导入模板-asset-v2.xlsx'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
      requestError.value = assetErrorState(error, '资产导入模板下载失败')
    }
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    if (downloadController === controller) downloading.value = false
  }
}

async function commitImport() {
  validationMessage.value = ''
  requestError.value = null
  if (!preview.value?.importToken) {
    validationMessage.value = '预览已失效，请重新预览导入内容'
    return
  }
  if (!selectedRows.value.length) {
    validationMessage.value = '至少选择一条可导入资产制作分项'
    return
  }
  const payload = { importToken: preview.value.importToken, selectedRows: selectedRows.value }
  committing.value = true
  try {
    const response = await commitAssetImport(operationContext.projectId, payload, idempotency.forPayload(payload))
    commitResult.value = response.data
    emit('imported', response.data, operationContext)
  } catch (error) {
    requestError.value = assetErrorState(error, '资产 Excel 正式导入失败')
  } finally {
    committing.value = false
  }
}

function issueText(issue) {
  return [issue.fieldName, issue.message].filter(Boolean).join('：')
}

function formatPreviewExpiry(value) {
  const expiresAt = new Date(value)
  if (Number.isNaN(expiresAt.getTime())) return '请尽快完成导入'
  const now = new Date()
  const time = expiresAt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const sameDay = expiresAt.getFullYear() === now.getFullYear()
    && expiresAt.getMonth() === now.getMonth()
    && expiresAt.getDate() === now.getDate()
  if (sameDay) return `请于今日 ${time} 前完成导入`
  const date = expiresAt.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  return `请于 ${date} ${time} 前完成导入`
}

onBeforeUnmount(() => {
  previewController?.abort()
  downloadController?.abort()
})
</script>

<template>
  <ProjectModal title="导入资产 Excel" :description="`将 Excel 中的资产与制作分项导入 ${projectName || '当前项目'}，解析后可预览并选择需要导入的内容。`" :busy="isBusy" wide @close="emit('close')">
    <div class="asset-import">
      <el-card class="file-picker" :class="{ 'has-file': file }" shadow="never">
        <el-icon><UploadFilled /></el-icon>
        <div><strong>{{ file?.name || '选择资产 Excel 工作簿' }}</strong><p>{{ file ? `${(file.size / 1024).toFixed(1)} KiB` : '仅支持 .xlsx，最大 10 MiB。' }}</p></div>
        <el-button text :loading="downloading" :disabled="isBusy" @click="downloadTemplate">下载官方模板</el-button>
        <el-upload ref="uploadRef" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :auto-upload="false" :show-file-list="false" :disabled="isBusy" :on-change="chooseFile">
          <el-button :disabled="isBusy">{{ file ? '更换文件' : '选择文件' }}</el-button>
        </el-upload>
        <el-button v-if="file" text type="danger" :disabled="isBusy" @click="clearSelectedFile">清除</el-button>
        <el-button type="primary" :loading="previewing" :disabled="!file || committing" @click="runPreview">{{ preview ? '重新预览' : '预览导入内容' }}</el-button>
      </el-card>

      <el-alert v-if="validationMessage || requestError" class="import-error" :title="requestError?.title || '请处理后再继续'" type="error" show-icon :closable="false"><span>{{ requestError?.message || validationMessage }}</span></el-alert>

      <el-result v-if="commitResult" class="import-success" icon="success" title="资产导入完成" sub-title="所选资产和制作分项已成功导入，需求匹配结果已更新。">
        <template #extra>
          <el-descriptions class="import-success__metrics" :column="3" border>
            <el-descriptions-item label="提交行">{{ commitResult.committedRows }}</el-descriptions-item><el-descriptions-item label="新增分项">{{ commitResult.createdAssetItems }}</el-descriptions-item><el-descriptions-item label="分配状态"><el-tag size="small" type="info" effect="plain" round>待分配</el-tag></el-descriptions-item><el-descriptions-item label="缺名称警告">{{ commitResult.missingProductionItemWarnings }}</el-descriptions-item><el-descriptions-item label="自动匹配">{{ commitResult.autoMatchedRequirements }}</el-descriptions-item><el-descriptions-item label="待处理 / 冲突">{{ commitResult.pendingRequirements }} / {{ commitResult.conflictRequirements }}</el-descriptions-item>
          </el-descriptions>
          <div class="created-types"><el-tag v-for="(count,type) in commitResult.createdAssetsByType" :key="type" size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(type).tone)">{{ assetTypeMeta(type).label }} {{ count }}</el-tag><el-tag size="small" effect="plain" round type="info">复用资产 {{ commitResult.reusedAssets }}</el-tag></div>
          <el-button type="primary" @click="emit('close')">完成</el-button>
        </template>
      </el-result>

      <template v-else-if="preview">
        <el-descriptions class="preview-summary" :column="3" border>
          <el-descriptions-item label="有效 / 总行"><strong>{{ validRows.length }} / {{ preview.summary.totalRows }}</strong></el-descriptions-item>
          <el-descriptions-item label="含警告行"><el-tag size="small" effect="plain" round type="warning">{{ preview.summary.warningRows }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="错误行"><el-tag size="small" effect="plain" round type="danger">{{ preview.summary.errorRows }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="资产 / 制作分项"><strong>{{ preview.summary.distinctAssets }} / {{ preview.summary.distinctAssetItems }}</strong></el-descriptions-item>
          <el-descriptions-item label="预计自动匹配"><strong>{{ preview.summary.estimatedAutoMatches }}</strong></el-descriptions-item>
          <el-descriptions-item label="导入有效期"><el-tooltip content="预览结果为临时数据，超过该时间后需要重新预览。" placement="top"><strong>{{ formatPreviewExpiry(preview.expiresAt) }}</strong></el-tooltip></el-descriptions-item>
        </el-descriptions>

        <section v-if="typeSummary.length" class="type-summary"><el-tag v-for="([type,summary]) in typeSummary" :key="type" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(type).tone)"><strong>{{ assetTypeMeta(type).label }}</strong> {{ summary.assets }} 资产 / {{ summary.items }} 分项 / {{ summary.validRows }} 有效</el-tag></section>
        <el-alert v-if="preview.workbookWarnings?.length" class="workbook-warnings" title="工作簿级警告" type="warning" show-icon :closable="false"><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }}</li></ul></el-alert>

        <el-alert class="assignment-boundary" title="导入后可在资产列表统一分配制作任务" type="info" show-icon :closable="false" />
        <div class="selection-toolbar"><span>已选择 {{ selectedRows.length }} 条</span></div>

        <el-card v-for="(rows,sheetName) in groupedRows" :key="sheetName" class="sheet-block" shadow="never">
          <template #header><header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><el-tag size="small" type="info" effect="plain" round>{{ rows.length }} 行</el-tag></div></header></template>
          <div class="preview-table-wrap">
            <el-table :ref="instance => setPreviewTableRef(sheetName, instance)" :data="rows" :row-key="rowKey" :row-class-name="previewRowClass" class="preview-table" max-height="340" @selection-change="selection => handleSheetSelection(rows, selection)">
              <el-table-column type="selection" width="55" :selectable="rowCanSelect" />
              <el-table-column label="类型" width="88"><template #default="{ row }"><el-tag v-if="row.normalized?.assetType" size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(row.normalized.assetType).tone)">{{ assetTypeMeta(row.normalized.assetType).label }}</el-tag><span v-else>—</span></template></el-table-column>
              <el-table-column label="资产" min-width="160"><template #default="{ row }">{{ row.normalized?.assetName || '—' }}</template></el-table-column>
              <el-table-column label="制作分项" min-width="190"><template #default="{ row }">{{ row.normalized?.productionItem || '待补充' }}</template></el-table-column>
              <el-table-column label="资产描述 / 分项补充要求" min-width="280"><template #default="{ row }"><div class="description-cell"><AssetDescriptionCell :common-description="row.normalized?.assetDescription" :item-description="row.normalized?.itemDescription" is-item /><small v-if="row.normalized?.remark">备注：{{ row.normalized.remark }}</small></div></template></el-table-column>
              <el-table-column label="数据状态" min-width="260"><template #default="{ row }"><div class="issue-list"><el-tag v-if="row.canImport && !row.warnings.length" size="small" type="success" effect="plain" round>正常</el-tag><el-tag v-for="issue in visibleWarnings(row)" :key="`w-${issue.errorKey}-${issue.fieldName}`" size="small" type="warning" effect="plain" round>{{ issueText(issue) }}</el-tag><el-tag v-for="issue in visibleErrors(row)" :key="`e-${issue.errorKey}-${issue.fieldName}`" size="small" type="danger" effect="plain" round>{{ issueText(issue) }}</el-tag></div></template></el-table-column>
            </el-table>
          </div>
        </el-card>

        <footer><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">确认导入 {{ selectedRows.length }} 条</el-button></footer>
      </template>
    </div>

  </ProjectModal>
</template>

<style scoped>
.asset-import { display: grid; gap: 18px; }
.file-picker.has-file { border-style: solid; border-color: rgba(255,182,87,.35); }
.file-picker strong, .file-picker p { display: block; margin: 0; }
.file-picker p { margin-top: 5px; color: var(--sg-text-muted); font-size: 11px; }
.created-types, .type-summary { display: flex; gap: 8px; flex-wrap: wrap; }
.created-types :deep(.el-tag), .type-summary :deep(.el-tag) { height: auto; min-height: 24px; white-space: normal; }
.workbook-warnings ul { margin: 8px 0 0; padding-left: 18px; }
.selection-toolbar, .sheet-block header, footer { display: flex; gap: 14px; align-items: center; justify-content: space-between; }
.selection-toolbar { min-height: 32px; color: var(--sg-text-muted); font-size: 12px; flex-wrap: wrap; }
.sheet-block header { padding: 12px 14px; background: rgba(255,255,255,.03); }
.sheet-block header div { display: flex; gap: 8px; align-items: center; }
.preview-table-wrap { overflow: hidden; }
.description-cell { max-width: 280px; line-height: 1.55; }
.description-cell small { display: block; color: var(--sg-text-muted); }
footer { justify-content: flex-end; padding-top: 6px; }
:deep(.preview-table) { --el-table-border-color: var(--sg-border); --el-table-text-color: var(--sg-text-secondary); --el-table-header-text-color: var(--sg-text-muted); font-size: 11px; }
:deep(.preview-table .el-table__cell) { vertical-align: top; }
:deep(.preview-table .has-errors td.el-table__cell) { background: rgba(255,107,107,.045); }
:deep(.preview-table .has-warnings td.el-table__cell) { background: rgba(255,182,87,.035); }
@media (max-width: 900px) { .selection-toolbar, footer { align-items: stretch; flex-direction: column; } }
.file-picker { padding:0;background:rgba(255,255,255,.025);border-style:dashed;border-color:var(--sg-border-strong) }
.file-picker:deep(.el-card__body){display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto auto;gap:12px;align-items:center;padding:18px}
.file-picker:deep(.el-upload){display:block}.file-picker:deep(.el-upload .el-button){width:100%}.file-picker:deep(.el-icon){color:var(--sg-accent);font-size:28px}
.import-error{display:block;padding:10px 12px}.import-error:deep(.el-alert__description){display:grid;gap:4px}.import-error code,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}
.import-success{display:block;padding:10px;background:rgba(98,212,155,.05);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success:deep(.el-result__extra){display:grid;width:100%;gap:14px;margin-top:20px}.import-success__metrics{width:100%}.created-types{justify-content:center}
.preview-summary{display:block}.preview-summary:deep(.el-descriptions__body),.preview-summary:deep(.el-descriptions__cell),.import-success__metrics:deep(.el-descriptions__body),.import-success__metrics:deep(.el-descriptions__cell){background:rgba(255,255,255,.025)!important;border-color:var(--sg-border)!important}.preview-summary:deep(.el-descriptions__label),.import-success__metrics:deep(.el-descriptions__label){color:var(--sg-text-muted);font-size:10px}.preview-summary:deep(.el-descriptions__content),.import-success__metrics:deep(.el-descriptions__content){color:var(--sg-text-secondary)}
.workbook-warnings{padding:10px 12px}.workbook-warnings:deep(.el-alert__description){margin-top:6px}.sheet-block{background:transparent;border-color:var(--sg-border)}.sheet-block:deep(.el-card__header){padding:0;border-bottom-color:var(--sg-border)}.sheet-block:deep(.el-card__body){padding:0}.issue-list{display:flex;min-width:180px;gap:5px;align-items:flex-start;flex-direction:column}.issue-list:deep(.el-tag){height:auto;min-height:22px;white-space:normal;text-align:left}
@media(max-width:900px){.file-picker:deep(.el-card__body){grid-template-columns:auto 1fr}.preview-summary:deep(.el-descriptions__table),.import-success__metrics:deep(.el-descriptions__table){table-layout:auto}}
</style>
