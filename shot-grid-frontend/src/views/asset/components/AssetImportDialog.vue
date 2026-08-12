<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Document, UploadFilled, WarningFilled } from '@element-plus/icons-vue'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import { createIdempotencyState } from '@/utils/idempotency'
import { assetErrorState, assetTypeMeta, groupAssetPreviewRows, selectableAssetPreviewRows } from '@/views/asset/assetPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

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
const previewing = ref(false)
const committing = ref(false)
const downloading = ref(false)
const validationMessage = ref('')
const requestError = ref(null)
const commitResult = ref(null)
let previewController = null
let downloadController = null
let fileGeneration = 0

const groupedRows = computed(() => groupAssetPreviewRows(preview.value?.rows || []))
const selectedRows = computed(() => (preview.value?.rows || [])
  .filter(row => selectedKeys.value.has(rowKey(row)))
  .map(row => ({ sheetName: row.sheetName, rowNumber: row.rowNumber })))
const validRows = computed(() => selectableAssetPreviewRows(preview.value?.rows || []))
const isBusy = computed(() => previewing.value || committing.value)
const typeSummary = computed(() => Object.entries(preview.value?.summary?.byType || {}))

function rowKey(row) {
  return `${row.sheetName}::${row.rowNumber}`
}

function resetPreview() {
  previewController?.abort()
  preview.value = null
  selectedKeys.value = new Set()
  requestError.value = null
  validationMessage.value = ''
  commitResult.value = null
  idempotency.reset()
}

function chooseFile(event) {
  fileGeneration += 1
  resetPreview()
  const nextFile = event.target.files?.[0] || null
  if (!nextFile) {
    file.value = null
    return
  }
  if (!/\.xlsx$/i.test(nextFile.name)) {
    validationMessage.value = '资产导入只接受 .xlsx 工作簿'
    event.target.value = ''
    file.value = null
    return
  }
  if (nextFile.size > 10 * 1024 * 1024) {
    validationMessage.value = 'Excel 文件不能超过 10 MiB'
    event.target.value = ''
    file.value = null
    return
  }
  file.value = nextFile
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
    selectedKeys.value = new Set(selectableAssetPreviewRows(response.data?.rows).map(row => rowKey(row)))
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && fileGeneration === targetGeneration) {
      requestError.value = assetErrorState(error, '资产 Excel 预检查失败')
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
    link.download = '资产导入模板-asset-v1.xlsx'
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

function toggleRow(row) {
  if (!row.canImport) return
  const next = new Set(selectedKeys.value)
  const key = rowKey(row)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedKeys.value = next
}

function toggleSheet(rows) {
  const selectable = rows.filter(row => row.canImport)
  const allSelected = selectable.length > 0 && selectable.every(row => selectedKeys.value.has(rowKey(row)))
  const next = new Set(selectedKeys.value)
  selectable.forEach(row => allSelected ? next.delete(rowKey(row)) : next.add(rowKey(row)))
  selectedKeys.value = next
}

function toggleAll() {
  if (selectedRows.value.length === validRows.value.length) selectedKeys.value = new Set()
  else selectedKeys.value = new Set(validRows.value.map(row => rowKey(row)))
}

async function commitImport() {
  validationMessage.value = ''
  requestError.value = null
  if (!preview.value?.importToken) {
    validationMessage.value = '预检 Token 不存在，请重新预检'
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

function detailsText(details) {
  if (!details) return ''
  if (typeof details === 'string') return details
  try {
    return JSON.stringify(details)
  } catch {
    return '后端返回了额外诊断信息'
  }
}

onBeforeUnmount(() => {
  previewController?.abort()
  downloadController?.abort()
})
</script>

<template>
  <ProjectModal title="导入资产 Excel" :description="`预检 ${projectName || '当前项目'} 的工作簿，确认跨 Sheet 物理行后再以单事务创建资产、制作分项、可选任务和自动匹配。`" :busy="isBusy" wide @close="emit('close')">
    <div class="asset-import">
      <section class="file-picker" :class="{ 'has-file': file }">
        <el-icon><UploadFilled /></el-icon>
        <div><strong>{{ file?.name || '选择资产 Excel 工作簿' }}</strong><p>{{ file ? `${(file.size / 1024).toFixed(1)} KiB` : '仅支持 .xlsx，最大 10 MiB；正式模板主数据区为 A:G。' }}</p></div>
        <el-button text :loading="downloading" :disabled="isBusy" @click="downloadTemplate">下载官方模板</el-button>
        <label><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :disabled="isBusy" @change="chooseFile" /><span>{{ file ? '更换文件' : '选择文件' }}</span></label>
        <el-button type="primary" :loading="previewing" :disabled="!file || committing" @click="runPreview">{{ preview ? '重新预检' : '开始预检' }}</el-button>
      </section>
      <p class="template-boundary">官方模板沿用 docs/ 资产样表的 A:G 结构与合并分项方式，示例内容已经匿名化；下载后请先替换所有“示例”数据再预检。</p>

      <div v-if="validationMessage || requestError" class="import-error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ requestError?.title || '请检查导入条件' }}</strong><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><p v-if="requestError?.details">{{ detailsText(requestError.details) }}</p></div></div>

      <section v-if="commitResult" class="import-success" role="status">
        <div><p class="sg-eyebrow">IMPORT COMPLETE</p><h3>资产已按单事务完成导入</h3><p>正式提交成功；资产、制作分项、可选任务和需求匹配结果已经由后端持久化。</p></div>
        <dl><div><dt>提交行</dt><dd>{{ commitResult.committedRows }}</dd></div><div><dt>新增分项</dt><dd>{{ commitResult.createdAssetItems }}</dd></div><div><dt>新增任务</dt><dd>{{ commitResult.createdTasks }}</dd></div><div><dt>缺名称警告</dt><dd>{{ commitResult.missingProductionItemWarnings }}</dd></div><div><dt>自动匹配</dt><dd>{{ commitResult.autoMatchedRequirements }}</dd></div><div><dt>待处理 / 冲突</dt><dd>{{ commitResult.pendingRequirements }} / {{ commitResult.conflictRequirements }}</dd></div></dl>
        <div class="created-types"><span v-for="(count,type) in commitResult.createdAssetsByType" :key="type">{{ assetTypeMeta(type).label }} {{ count }}</span><span>复用资产 {{ commitResult.reusedAssets }}</span></div>
        <el-button type="primary" @click="emit('close')">完成</el-button>
      </section>

      <template v-else-if="preview">
        <section class="preview-summary">
          <div><span>有效 / 总行</span><strong>{{ preview.summary.validRows }} / {{ preview.summary.totalRows }}</strong></div>
          <div><span>含警告行</span><strong data-tone="warning">{{ preview.summary.warningRows }}</strong></div>
          <div><span>错误行</span><strong data-tone="danger">{{ preview.summary.errorRows }}</strong></div>
          <div><span>资产 / 制作分项</span><strong>{{ preview.summary.distinctAssets }} / {{ preview.summary.distinctAssetItems }}</strong></div>
          <div><span>预计自动匹配</span><strong>{{ preview.summary.estimatedAutoMatches }}</strong></div>
          <div><span>Token 到期</span><strong>{{ new Date(preview.expiresAt).toLocaleTimeString('zh-CN') }}</strong></div>
        </section>

        <section v-if="typeSummary.length" class="type-summary"><span v-for="([type,summary]) in typeSummary" :key="type" :data-tone="assetTypeMeta(type).tone"><strong>{{ assetTypeMeta(type).label }}</strong> {{ summary.assets }} 资产 / {{ summary.items }} 分项 / {{ summary.validRows }} 有效</span></section>
        <section v-if="preview.workbookWarnings?.length" class="workbook-warnings"><strong>工作簿级警告</strong><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }} <code>{{ issue.errorKey }}</code></li></ul></section>

        <div class="selection-toolbar"><span>已选 {{ selectedRows.length }} 条可导入行</span><button type="button" @click="toggleAll">{{ selectedRows.length === validRows.length ? '取消全选' : '选择全部有效行' }}</button></div>

        <section v-for="(rows,sheetName) in groupedRows" :key="sheetName" class="sheet-block">
          <header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><span>{{ rows.length }} 行</span></div><button type="button" @click="toggleSheet(rows)">{{ rows.filter(row => row.canImport).every(row => selectedKeys.has(rowKey(row))) ? '取消本 Sheet' : '选择本 Sheet 有效行' }}</button></header>
          <div class="preview-table-wrap"><table><thead><tr><th>选择</th><th>物理行</th><th>类型</th><th>资产</th><th>制作分项</th><th>制作人</th><th>描述 / 备注</th><th>预检结果</th></tr></thead><tbody><tr v-for="row in rows" :key="rowKey(row)" :class="{ 'has-errors': row.errors.length, 'has-warnings': row.warnings.length && !row.errors.length }"><td><input type="checkbox" :checked="selectedKeys.has(rowKey(row))" :disabled="!row.canImport" :aria-label="`选择 ${sheetName} 第 ${row.rowNumber} 行`" @change="toggleRow(row)" /></td><td>{{ row.rowNumber }}</td><td>{{ assetTypeMeta(row.normalized?.assetType).label }}</td><td>{{ row.normalized?.assetName || '—' }}</td><td>{{ row.normalized?.productionItem || '待补充' }}</td><td>{{ row.normalized?.assigneeUserName || '未分配' }}</td><td class="description-cell">{{ row.normalized?.itemDescription || row.normalized?.assetDescription || '—' }}<small>{{ row.normalized?.remark || '' }}</small></td><td><ul class="issue-list"><li v-if="row.canImport && !row.warnings.length">可导入</li><li v-for="issue in row.warnings" :key="`w-${issue.errorKey}-${issue.fieldName}`" data-tone="warning">{{ issueText(issue) }}</li><li v-for="issue in row.errors" :key="`e-${issue.errorKey}-${issue.fieldName}`" data-tone="danger">{{ issueText(issue) }}</li></ul></td></tr></tbody></table></div>
        </section>

        <footer><div><strong>正式提交将全量回滚任一失败行</strong><p>选中行以 Sheet 名和物理行号共同标识；Token 与幂等键只保存在当前对话框内存。</p></div><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">正式导入 {{ selectedRows.length }} 行</el-button></footer>
      </template>
    </div>
  </ProjectModal>
</template>

<style scoped>
.asset-import{display:grid;gap:18px}.file-picker{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto;gap:14px;align-items:center;padding:18px;background:rgba(255,255,255,.025);border:1px dashed var(--sg-border-strong);border-radius:14px}.file-picker.has-file{border-style:solid;border-color:rgba(255,182,87,.35)}.file-picker>.el-icon{color:var(--sg-accent);font-size:28px}.file-picker strong,.file-picker p{display:block;margin:0}.file-picker p{margin-top:5px;color:var(--sg-text-muted);font-size:11px}.file-picker label input{position:absolute;width:1px;height:1px;opacity:0}.file-picker label span,.selection-toolbar button,.sheet-block header button{color:var(--sg-accent);font-size:12px;cursor:pointer}.file-picker label span{display:block;padding:9px 12px;background:var(--sg-accent-soft);border-radius:8px}.template-boundary{margin:-8px 0 0;padding:10px 12px;color:var(--sg-accent);font-size:11px;background:var(--sg-accent-soft);border-radius:8px}.import-error{display:grid;grid-template-columns:auto 1fr;gap:12px;padding:15px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:11px}.import-error p{margin:4px 0 0;font-size:12px}.import-error code,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}.import-success{display:grid;gap:16px;padding:22px;background:rgba(98,212,155,.07);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success h3,.import-success p{margin:0}.import-success>div>p:last-child{margin-top:6px;color:var(--sg-text-secondary);font-size:12px}.import-success dl{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:0}.import-success dl div{padding:11px;background:rgba(0,0,0,.15);border-radius:8px}.import-success dt{color:var(--sg-text-muted);font-size:10px}.import-success dd{margin:4px 0 0;font-size:18px}.created-types,.type-summary{display:flex;gap:8px;flex-wrap:wrap}.created-types span,.type-summary span{padding:7px 9px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.04);border-radius:8px}.type-summary span[data-tone=character]{color:var(--sg-accent);background:var(--sg-accent-soft)}.type-summary span[data-tone=environment]{color:#80bfff;background:rgba(128,191,255,.08)}.type-summary span[data-tone=prop]{color:#8dd8a9;background:rgba(98,212,155,.08)}.preview-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}.preview-summary div{padding:13px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.preview-summary span,.preview-summary strong{display:block}.preview-summary span{color:var(--sg-text-muted);font-size:10px}.preview-summary strong{margin-top:5px}.preview-summary strong[data-tone=warning]{color:var(--sg-accent)}.preview-summary strong[data-tone=danger]{color:var(--sg-danger)}.workbook-warnings{padding:14px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:10px}.workbook-warnings ul{margin:8px 0 0;padding-left:18px}.selection-toolbar,.sheet-block header,footer{display:flex;gap:14px;align-items:center;justify-content:space-between}.selection-toolbar{color:var(--sg-text-muted);font-size:12px}.selection-toolbar button,.sheet-block header button{padding:0;background:transparent;border:0}.sheet-block{overflow:hidden;border:1px solid var(--sg-border);border-radius:12px}.sheet-block header{padding:12px 14px;background:rgba(255,255,255,.03)}.sheet-block header div{display:flex;gap:8px;align-items:center}.sheet-block header span{color:var(--sg-text-muted);font-size:11px}.preview-table-wrap{overflow:auto;max-height:340px}table{width:100%;min-width:1040px;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid var(--sg-border);font-size:11px;text-align:left;vertical-align:top}th{position:sticky;z-index:1;top:0;color:var(--sg-text-muted);background:#15191f}td{color:var(--sg-text-secondary)}tr.has-errors{background:rgba(255,107,107,.045)}tr.has-warnings{background:rgba(255,182,87,.035)}.description-cell{max-width:260px;line-height:1.55}.description-cell small{display:block;color:var(--sg-text-muted)}.issue-list{min-width:180px;margin:0;padding:0;list-style:none}.issue-list li{margin-bottom:4px;color:var(--sg-success)}.issue-list li[data-tone=warning]{color:var(--sg-accent)}.issue-list li[data-tone=danger]{color:var(--sg-danger)}footer{padding-top:6px}footer>div{flex:1}footer strong,footer p{display:block;margin:0}footer p{margin-top:4px;color:var(--sg-text-muted);font-size:11px}@media(max-width:900px){.file-picker{grid-template-columns:auto 1fr}.preview-summary,.import-success dl{grid-template-columns:repeat(2,minmax(0,1fr))}footer{align-items:stretch;flex-direction:column}}
</style>
