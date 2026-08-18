<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { Document, UserFilled, UploadFilled, WarningFilled } from '@element-plus/icons-vue'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import { createIdempotencyState } from '@/utils/idempotency'
import { assetErrorState, assetTypeMeta, groupAssetPreviewRows } from '@/views/asset/assetPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  projectName: { type: String, default: '' },
  members: { type: Array, default: () => [] }
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
const assigneeByRow = ref(new Map())
const batchAssigneeUserId = ref('')
const showBatchAssign = ref(false)
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
  .filter(row => rowCanImport(row))
  .map(row => {
    const selected = { sheetName: row.sheetName, rowNumber: row.rowNumber }
    if (hasAssigneeChoice(row)) selected.assigneeUserId = selectedAssigneeId(row)
    return selected
  }))
const validRows = computed(() => (preview.value?.rows || []).filter(row => rowCanImport(row)))
const selectedPreviewRows = computed(() => (preview.value?.rows || [])
  .filter(row => selectedKeys.value.has(rowKey(row))))
const overriddenRowCount = computed(() => (preview.value?.rows || []).filter(row => (
  hasOnlyAssigneeErrors(row) && assigneeChoiceResolvesErrors(row)
)).length)
const assignableMembers = computed(() => props.members.filter(member => member.projectRole === 'creator'))
const isBusy = computed(() => previewing.value || committing.value)
const typeSummary = computed(() => Object.entries(preview.value?.summary?.byType || {}))

function rowKey(row) {
  return `${row.sheetName}::${row.rowNumber}`
}

function isAssigneeIssue(issue) {
  return issue?.fieldName === 'assigneeUserName'
}

function hasOnlyAssigneeErrors(row) {
  return Boolean(row.normalized && row.errors?.length && row.errors.every(isAssigneeIssue))
}

function hasAssigneeChoice(row) {
  return assigneeByRow.value.has(rowKey(row))
}

function selectedAssigneeId(row) {
  if (!hasAssigneeChoice(row)) return null
  const value = Number(assigneeByRow.value.get(rowKey(row)))
  return Number.isSafeInteger(value) && value > 0 ? value : null
}

function rowHasProductionItem(row) {
  return Boolean(String(row.normalized?.productionItem || '').trim())
}

function assigneeChoiceResolvesErrors(row) {
  return hasAssigneeChoice(row) && (!selectedAssigneeId(row) || rowHasProductionItem(row))
}

function assigneeSelectValue(row) {
  if (hasAssigneeChoice(row)) return selectedAssigneeId(row) || ''
  return row.normalized?.assigneeUserName ? '__unresolved__' : ''
}

function rowCanImport(row) {
  return Boolean(row.canImport || (hasOnlyAssigneeErrors(row) && assigneeChoiceResolvesErrors(row)))
}

function rowCanSelect(row) {
  return Boolean(rowCanImport(row) || hasOnlyAssigneeErrors(row))
}

function visibleWarnings(row) {
  return assigneeChoiceResolvesErrors(row) ? (row.warnings || []).filter(issue => !isAssigneeIssue(issue)) : (row.warnings || [])
}

function visibleErrors(row) {
  return assigneeChoiceResolvesErrors(row) ? (row.errors || []).filter(issue => !isAssigneeIssue(issue)) : (row.errors || [])
}

function assigneeLabel(userId) {
  const member = props.members.find(item => Number(item.userId) === Number(userId))
  if (!member) return ''
  return member.userName ? `${member.nickName || member.userName}（${member.userName}）` : member.nickName
}

function initializeAssignees(rows) {
  const assignableIds = new Set(assignableMembers.value.map(member => Number(member.userId)))
  const next = new Map()
  rows.forEach(row => {
    const userId = Number(row.normalized?.assigneeUserId)
    if (Number.isSafeInteger(userId) && userId > 0 && assignableIds.has(userId)) next.set(rowKey(row), userId)
    else if (row.normalized && !row.normalized.assigneeUserName) next.set(rowKey(row), null)
  })
  assigneeByRow.value = next
}

function changeAssignee(row, event) {
  const userId = Number(event.target.value)
  const nextAssignees = new Map(assigneeByRow.value)
  if (Number.isSafeInteger(userId) && userId > 0 && !rowHasProductionItem(row)) {
    nextAssignees.set(rowKey(row), null)
    validationMessage.value = `第 ${row.rowNumber} 行未填写制作分项，只能以未分配状态导入`
  } else {
    nextAssignees.set(rowKey(row), Number.isSafeInteger(userId) && userId > 0 ? userId : null)
    validationMessage.value = ''
  }
  assigneeByRow.value = nextAssignees
  const nextSelected = new Set(selectedKeys.value)
  if (rowCanImport(row)) nextSelected.add(rowKey(row))
  else nextSelected.delete(rowKey(row))
  selectedKeys.value = nextSelected
  void syncPreviewTableSelections()
}

function openBatchAssignDialog() {
  if (!selectedPreviewRows.value.length) return
  batchAssigneeUserId.value = ''
  showBatchAssign.value = true
}

function closeBatchAssignDialog() {
  showBatchAssign.value = false
}

function confirmBatchAssign() {
  if (!batchAssigneeUserId.value) return
  const parsedUserId = Number(batchAssigneeUserId.value)
  const assigneeUserId = Number.isSafeInteger(parsedUserId) && parsedUserId > 0 ? parsedUserId : null
  const rows = (preview.value?.rows || []).filter(row => {
    if (!row.normalized || (row.errors?.length && !hasOnlyAssigneeErrors(row))) return false
    return selectedKeys.value.has(rowKey(row))
  })
  if (!rows.length) {
    validationMessage.value = '请先勾选需要批量设置的资产制作分项'
    return
  }
  if (assigneeUserId && rows.some(row => !rowHasProductionItem(row))) {
    validationMessage.value = '所选行包含未填写制作分项的记录；请补齐名称，或批量设置为“未分配”'
    return
  }
  const nextAssignees = new Map(assigneeByRow.value)
  rows.forEach(row => {
    nextAssignees.set(rowKey(row), assigneeUserId)
  })
  assigneeByRow.value = nextAssignees
  validationMessage.value = ''
  showBatchAssign.value = false
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
  assigneeByRow.value = new Map()
  batchAssigneeUserId.value = ''
  showBatchAssign.value = false
  previewTableRefs.clear()
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
    initializeAssignees(response.data?.rows || [])
    selectedKeys.value = new Set((response.data?.rows || []).filter(row => rowCanImport(row)).map(row => rowKey(row)))
    await syncPreviewTableSelections()
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
  <ProjectModal title="导入资产 Excel" :description="`预检 ${projectName || '当前项目'} 的工作簿，确认跨 Sheet 的资产与制作分项后，再以单事务创建资产、可选任务并自动匹配。`" :busy="isBusy" wide @close="emit('close')">
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
          <div><span>有效 / 总行</span><strong>{{ validRows.length }} / {{ preview.summary.totalRows }}</strong></div>
          <div><span>含警告行</span><strong data-tone="warning">{{ preview.summary.warningRows }}</strong></div>
          <div><span>错误行</span><strong data-tone="danger">{{ preview.summary.errorRows }}<small v-if="overriddenRowCount"> · 已处理 {{ overriddenRowCount }}</small></strong></div>
          <div><span>资产 / 制作分项</span><strong>{{ preview.summary.distinctAssets }} / {{ preview.summary.distinctAssetItems }}</strong></div>
          <div><span>预计自动匹配</span><strong>{{ preview.summary.estimatedAutoMatches }}</strong></div>
          <div><span>Token 到期</span><strong>{{ new Date(preview.expiresAt).toLocaleTimeString('zh-CN') }}</strong></div>
        </section>

        <section v-if="typeSummary.length" class="type-summary"><span v-for="([type,summary]) in typeSummary" :key="type" :data-tone="assetTypeMeta(type).tone"><strong>{{ assetTypeMeta(type).label }}</strong> {{ summary.assets }} 资产 / {{ summary.items }} 分项 / {{ summary.validRows }} 有效</span></section>
        <section v-if="preview.workbookWarnings?.length" class="workbook-warnings"><strong>工作簿级警告</strong><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }} <code>{{ issue.errorKey }}</code></li></ul></section>

        <div class="selection-toolbar"><span>已选 {{ selectedPreviewRows.length }} 行 · {{ selectedRows.length }} 条可导入</span><el-button v-if="selectedPreviewRows.length" type="primary" plain @click="openBatchAssignDialog">批量分配</el-button></div>

        <section v-for="(rows,sheetName) in groupedRows" :key="sheetName" class="sheet-block">
          <header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><span>{{ rows.length }} 行</span></div></header>
          <div class="preview-table-wrap">
            <el-table :ref="instance => setPreviewTableRef(sheetName, instance)" :data="rows" :row-key="rowKey" :row-class-name="previewRowClass" class="preview-table" max-height="340" @selection-change="selection => handleSheetSelection(rows, selection)">
              <el-table-column type="selection" width="55" :selectable="rowCanSelect" />
              <el-table-column label="类型" width="76"><template #default="{ row }">{{ assetTypeMeta(row.normalized?.assetType).label }}</template></el-table-column>
              <el-table-column label="资产" min-width="160"><template #default="{ row }">{{ row.normalized?.assetName || '—' }}</template></el-table-column>
              <el-table-column label="制作分项" min-width="190"><template #default="{ row }">{{ row.normalized?.productionItem || '待补充' }}</template></el-table-column>
              <el-table-column label="制作人" width="190"><template #default="{ row }"><select class="assignee-select" :value="assigneeSelectValue(row)" :aria-label="`选择 ${sheetName} 第 ${row.rowNumber} 行制作人`" :title="rowHasProductionItem(row) ? '选择制作人' : '制作分项为空时只能保持未分配'" :disabled="!row.normalized" @change="changeAssignee(row, $event)"><option v-if="!hasAssigneeChoice(row) && row.normalized?.assigneeUserName" value="__unresolved__" disabled>未匹配：{{ row.normalized.assigneeUserName }}</option><option value="">未分配</option><option v-for="member in assignableMembers" :key="member.userId" :value="member.userId" :disabled="!rowHasProductionItem(row)">{{ assigneeLabel(member.userId) }}</option></select></template></el-table-column>
              <el-table-column label="描述 / 备注" min-width="280"><template #default="{ row }"><div class="description-cell">{{ row.normalized?.itemDescription || row.normalized?.assetDescription || '—' }}<small>{{ row.normalized?.remark || '' }}</small></div></template></el-table-column>
              <el-table-column label="预检结果" min-width="250"><template #default="{ row }"><ul class="issue-list"><li v-if="selectedAssigneeId(row)" data-tone="success">已选择：{{ assigneeLabel(selectedAssigneeId(row)) }}</li><li v-else-if="hasAssigneeChoice(row)" data-tone="success">将以未分配状态导入</li><li v-else-if="row.canImport && !row.warnings.length">可导入</li><li v-for="issue in visibleWarnings(row)" :key="`w-${issue.errorKey}-${issue.fieldName}`" data-tone="warning">{{ issueText(issue) }}</li><li v-for="issue in visibleErrors(row)" :key="`e-${issue.errorKey}-${issue.fieldName}`" data-tone="danger">{{ issueText(issue) }}</li></ul></template></el-table-column>
            </el-table>
          </div>
        </section>

        <footer><div><strong>正式提交将全量回滚任一失败行</strong><p>系统内部以 Sheet 和源数据行共同定位；Token 与幂等键只保存在当前对话框内存。</p></div><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">正式导入 {{ selectedRows.length }} 行</el-button></footer>
      </template>
    </div>

    <el-dialog v-model="showBatchAssign" class="import-batch-assign-dialog" title="批量分配制作人" width="480px" append-to-body :z-index="3100" destroy-on-close @closed="batchAssigneeUserId = ''">
      <div class="batch-assign-content">
        <div class="batch-assign-summary"><span class="batch-assign-summary__icon"><el-icon><UserFilled /></el-icon></span><div><strong>已选择 {{ selectedPreviewRows.length }} 行</strong><p>确认后，仅当前勾选行的制作人会被更新。</p></div></div>
        <label class="batch-assign-field"><span>分配给</span><select v-model="batchAssigneeUserId" class="assignee-select batch-assignee-select" aria-label="批量分配资产制作人"><option disabled value="">请选择制作人</option><option value="__unassigned__">未分配</option><option v-for="member in assignableMembers" :key="member.userId" :value="String(member.userId)">{{ assigneeLabel(member.userId) }}</option></select><small>可选择“未分配”清空当前勾选行的制作人。</small></label>
      </div>
      <template #footer><div class="batch-assign-actions"><el-button @click="closeBatchAssignDialog">取消</el-button><el-button type="primary" :disabled="!batchAssigneeUserId" @click="confirmBatchAssign">确认分配</el-button></div></template>
    </el-dialog>
  </ProjectModal>
</template>

<style scoped>
.asset-import{display:grid;gap:18px}.file-picker{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto;gap:14px;align-items:center;padding:18px;background:rgba(255,255,255,.025);border:1px dashed var(--sg-border-strong);border-radius:14px}.file-picker.has-file{border-style:solid;border-color:rgba(255,182,87,.35)}.file-picker>.el-icon{color:var(--sg-accent);font-size:28px}.file-picker strong,.file-picker p{display:block;margin:0}.file-picker p{margin-top:5px;color:var(--sg-text-muted);font-size:11px}.file-picker label input{position:absolute;width:1px;height:1px;opacity:0}.file-picker label span{color:var(--sg-accent);font-size:12px;cursor:pointer}.file-picker label span{display:block;padding:9px 12px;background:var(--sg-accent-soft);border-radius:8px}.template-boundary{margin:-8px 0 0;padding:10px 12px;color:var(--sg-accent);font-size:11px;background:var(--sg-accent-soft);border-radius:8px}.import-error{display:grid;grid-template-columns:auto 1fr;gap:12px;padding:15px;color:#ffb4b4;background:rgba(255,107,107,.08);border-radius:11px}.import-error p{margin:4px 0 0;font-size:12px}.import-error code,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}.import-success{display:grid;gap:16px;padding:22px;background:rgba(98,212,155,.07);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success h3,.import-success p{margin:0}.import-success>div>p:last-child{margin-top:6px;color:var(--sg-text-secondary);font-size:12px}.import-success dl{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:0}.import-success dl div{padding:11px;background:rgba(0,0,0,.15);border-radius:8px}.import-success dt{color:var(--sg-text-muted);font-size:10px}.import-success dd{margin:4px 0 0;font-size:18px}.created-types,.type-summary{display:flex;gap:8px;flex-wrap:wrap}.created-types span,.type-summary span{padding:7px 9px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.04);border-radius:8px}.type-summary span[data-tone=character]{color:var(--sg-accent);background:var(--sg-accent-soft)}.type-summary span[data-tone=environment]{color:#80bfff;background:rgba(128,191,255,.08)}.type-summary span[data-tone=prop]{color:#8dd8a9;background:rgba(98,212,155,.08)}.preview-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}.preview-summary div{padding:13px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.preview-summary span,.preview-summary strong{display:block}.preview-summary span{color:var(--sg-text-muted);font-size:10px}.preview-summary strong{margin-top:5px}.preview-summary strong small{font-size:10px;font-weight:500}.preview-summary strong[data-tone=warning]{color:var(--sg-accent)}.preview-summary strong[data-tone=danger]{color:var(--sg-danger)}.workbook-warnings{padding:14px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:10px}.workbook-warnings ul{margin:8px 0 0;padding-left:18px}.selection-toolbar,.sheet-block header,footer{display:flex;gap:14px;align-items:center;justify-content:space-between}.selection-toolbar{min-height:32px;color:var(--sg-text-muted);font-size:12px;flex-wrap:wrap}.sheet-block{overflow:hidden;border:1px solid var(--sg-border);border-radius:12px}.sheet-block header{padding:12px 14px;background:rgba(255,255,255,.03)}.sheet-block header div{display:flex;gap:8px;align-items:center}.sheet-block header span{color:var(--sg-text-muted);font-size:11px}.preview-table-wrap{overflow:hidden}.assignee-select{width:170px;min-height:32px;padding:0 8px;color:var(--sg-text);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:7px}.assignee-select:focus{border-color:var(--sg-accent);outline:0}.assignee-select:disabled{cursor:not-allowed;opacity:.5}.description-cell{max-width:280px;line-height:1.55}.description-cell small{display:block;color:var(--sg-text-muted)}.issue-list{min-width:180px;margin:0;padding:0;list-style:none}.issue-list li{margin-bottom:4px;color:var(--sg-success)}.issue-list li[data-tone=success]{color:var(--sg-success)}.issue-list li[data-tone=warning]{color:var(--sg-accent)}.issue-list li[data-tone=danger]{color:var(--sg-danger)}.batch-assign-content{display:grid;gap:18px}.batch-assign-summary{display:flex;gap:13px;align-items:center;padding:15px;background:linear-gradient(135deg,rgba(255,182,87,.12),rgba(255,182,87,.035));border:1px solid rgba(255,182,87,.22);border-radius:12px}.batch-assign-summary__icon{display:grid;width:38px;height:38px;flex:0 0 auto;color:var(--sg-accent);font-size:18px;background:rgba(255,182,87,.13);border-radius:10px;place-items:center}.batch-assign-summary strong{display:block;font-size:14px}.batch-assign-summary p{margin:5px 0 0;color:var(--sg-text-secondary);font-size:11px;line-height:1.5}.batch-assign-field{display:grid;gap:8px}.batch-assign-field>span{color:var(--sg-text-secondary);font-size:12px;font-weight:600}.batch-assign-field small{color:var(--sg-text-muted);font-size:10px}.batch-assignee-select{width:100%;height:42px;padding:0 12px;border-color:var(--sg-border-strong);border-radius:10px}.batch-assign-actions{display:flex;gap:10px;justify-content:flex-end}footer{padding-top:6px}footer>div{flex:1}footer strong,footer p{display:block;margin:0}footer p{margin-top:4px;color:var(--sg-text-muted);font-size:11px}:deep(.preview-table){--el-table-bg-color:transparent;--el-table-tr-bg-color:transparent;--el-table-header-bg-color:#15191f;--el-table-row-hover-bg-color:rgba(255,255,255,.035);--el-table-border-color:var(--sg-border);--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);font-size:11px}:deep(.preview-table .el-table__cell){vertical-align:top}:deep(.preview-table .has-errors td.el-table__cell){background:rgba(255,107,107,.045)}:deep(.preview-table .has-warnings td.el-table__cell){background:rgba(255,182,87,.035)}@media(max-width:900px){.file-picker{grid-template-columns:auto 1fr}.preview-summary,.import-success dl{grid-template-columns:repeat(2,minmax(0,1fr))}.selection-toolbar,footer{align-items:stretch;flex-direction:column}}
</style>
