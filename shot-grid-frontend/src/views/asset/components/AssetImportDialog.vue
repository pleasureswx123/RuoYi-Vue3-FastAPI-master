<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { Document, UserFilled, UploadFilled } from '@element-plus/icons-vue'

import { commitAssetImport, downloadAssetImportTemplate, previewAssetImport } from '@/api/shot-grid/assets'
import { createIdempotencyState } from '@/utils/idempotency'
import { tagTypeFromTone } from '@/utils/tag'
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
const uploadRef = ref(null)
const batchAssignFormRef = ref(null)
const batchAssignForm = reactive({ assigneeUserId: '' })
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
const batchAssignRules = {
  assigneeUserId: [{ required: true, message: '请选择制作人或未分配', trigger: 'change' }]
}

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
  if (hasAssigneeChoice(row)) {
    const assigneeUserId = selectedAssigneeId(row)
    return assigneeUserId ? String(assigneeUserId) : ''
  }
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

function changeAssignee(row, value) {
  const selectedValue = value?.target ? value.target.value : value
  const userId = Number(selectedValue)
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
  batchAssignForm.assigneeUserId = ''
  showBatchAssign.value = true
  void nextTick(() => batchAssignFormRef.value?.clearValidate())
}

function closeBatchAssignDialog() {
  batchAssignFormRef.value?.resetFields()
  showBatchAssign.value = false
}

async function confirmBatchAssign() {
  const isValid = await batchAssignFormRef.value?.validate().catch(() => false)
  if (!isValid) return
  const parsedUserId = Number(batchAssignForm.assigneeUserId)
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
  closeBatchAssignDialog()
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
  batchAssignForm.assigneeUserId = ''
  showBatchAssign.value = false
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
      <el-card class="file-picker" :class="{ 'has-file': file }" shadow="never">
        <el-icon><UploadFilled /></el-icon>
        <div><strong>{{ file?.name || '选择资产 Excel 工作簿' }}</strong><p>{{ file ? `${(file.size / 1024).toFixed(1)} KiB` : '仅支持 .xlsx，最大 10 MiB；正式模板主数据区为 A:G。' }}</p></div>
        <el-button text :loading="downloading" :disabled="isBusy" @click="downloadTemplate">下载官方模板</el-button>
        <el-upload ref="uploadRef" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :auto-upload="false" :show-file-list="false" :disabled="isBusy" :on-change="chooseFile">
          <el-button :disabled="isBusy">{{ file ? '更换文件' : '选择文件' }}</el-button>
        </el-upload>
        <el-button v-if="file" text type="danger" :disabled="isBusy" @click="clearSelectedFile">清除</el-button>
        <el-button type="primary" :loading="previewing" :disabled="!file || committing" @click="runPreview">{{ preview ? '重新预检' : '开始预检' }}</el-button>
      </el-card>
      <el-alert class="template-boundary" title="模板边界" description="官方模板沿用 docs/ 资产样表的 A:G 结构与合并分项方式，示例内容已经匿名化；下载后请先替换所有“示例”数据再预检。" type="info" show-icon :closable="false" />

      <el-alert v-if="validationMessage || requestError" class="import-error" :title="requestError?.title || '请检查导入条件'" type="error" show-icon :closable="false"><span>{{ requestError?.message || validationMessage }}</span><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><span v-if="requestError?.details">{{ detailsText(requestError.details) }}</span></el-alert>

      <el-result v-if="commitResult" class="import-success" icon="success" title="资产已按单事务完成导入" sub-title="资产、制作分项、可选任务和需求匹配结果已经由后端持久化。">
        <template #extra>
          <el-descriptions class="import-success__metrics" :column="3" border>
            <el-descriptions-item label="提交行">{{ commitResult.committedRows }}</el-descriptions-item><el-descriptions-item label="新增分项">{{ commitResult.createdAssetItems }}</el-descriptions-item><el-descriptions-item label="新增任务">{{ commitResult.createdTasks }}</el-descriptions-item><el-descriptions-item label="缺名称警告">{{ commitResult.missingProductionItemWarnings }}</el-descriptions-item><el-descriptions-item label="自动匹配">{{ commitResult.autoMatchedRequirements }}</el-descriptions-item><el-descriptions-item label="待处理 / 冲突">{{ commitResult.pendingRequirements }} / {{ commitResult.conflictRequirements }}</el-descriptions-item>
          </el-descriptions>
          <div class="created-types"><el-tag v-for="(count,type) in commitResult.createdAssetsByType" :key="type" size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(type).tone)">{{ assetTypeMeta(type).label }} {{ count }}</el-tag><el-tag size="small" effect="plain" round type="info">复用资产 {{ commitResult.reusedAssets }}</el-tag></div>
          <el-button type="primary" @click="emit('close')">完成</el-button>
        </template>
      </el-result>

      <template v-else-if="preview">
        <el-descriptions class="preview-summary" :column="3" border>
          <el-descriptions-item label="有效 / 总行"><strong>{{ validRows.length }} / {{ preview.summary.totalRows }}</strong></el-descriptions-item>
          <el-descriptions-item label="含警告行"><el-tag size="small" effect="plain" round type="warning">{{ preview.summary.warningRows }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="错误行"><el-tag size="small" effect="plain" round type="danger">{{ preview.summary.errorRows }}<template v-if="overriddenRowCount"> · 已处理 {{ overriddenRowCount }}</template></el-tag></el-descriptions-item>
          <el-descriptions-item label="资产 / 制作分项"><strong>{{ preview.summary.distinctAssets }} / {{ preview.summary.distinctAssetItems }}</strong></el-descriptions-item>
          <el-descriptions-item label="预计自动匹配"><strong>{{ preview.summary.estimatedAutoMatches }}</strong></el-descriptions-item>
          <el-descriptions-item label="Token 到期"><strong>{{ new Date(preview.expiresAt).toLocaleTimeString('zh-CN') }}</strong></el-descriptions-item>
        </el-descriptions>

        <section v-if="typeSummary.length" class="type-summary"><el-tag v-for="([type,summary]) in typeSummary" :key="type" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(type).tone)"><strong>{{ assetTypeMeta(type).label }}</strong> {{ summary.assets }} 资产 / {{ summary.items }} 分项 / {{ summary.validRows }} 有效</el-tag></section>
        <el-alert v-if="preview.workbookWarnings?.length" class="workbook-warnings" title="工作簿级警告" type="warning" show-icon :closable="false"><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }} <code>{{ issue.errorKey }}</code></li></ul></el-alert>

        <div class="selection-toolbar"><span>已选 {{ selectedPreviewRows.length }} 行 · {{ selectedRows.length }} 条可导入</span><el-button v-if="selectedPreviewRows.length" type="primary" plain @click="openBatchAssignDialog">批量分配</el-button></div>

        <el-card v-for="(rows,sheetName) in groupedRows" :key="sheetName" class="sheet-block" shadow="never">
          <template #header><header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><el-tag size="small" type="info" effect="plain" round>{{ rows.length }} 行</el-tag></div></header></template>
          <div class="preview-table-wrap">
            <el-table :ref="instance => setPreviewTableRef(sheetName, instance)" :data="rows" :row-key="rowKey" :row-class-name="previewRowClass" class="preview-table" max-height="340" @selection-change="selection => handleSheetSelection(rows, selection)">
              <el-table-column type="selection" width="55" :selectable="rowCanSelect" />
              <el-table-column label="类型" width="88"><template #default="{ row }"><el-tag v-if="row.normalized?.assetType" size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(row.normalized.assetType).tone)">{{ assetTypeMeta(row.normalized.assetType).label }}</el-tag><span v-else>—</span></template></el-table-column>
              <el-table-column label="资产" min-width="160"><template #default="{ row }">{{ row.normalized?.assetName || '—' }}</template></el-table-column>
              <el-table-column label="制作分项" min-width="190"><template #default="{ row }">{{ row.normalized?.productionItem || '待补充' }}</template></el-table-column>
              <el-table-column label="制作人" width="210"><template #default="{ row }"><el-select class="assignee-select" :model-value="assigneeSelectValue(row)" :aria-label="`选择 ${sheetName} 第 ${row.rowNumber} 行制作人`" :title="rowHasProductionItem(row) ? '选择制作人' : '制作分项为空时只能保持未分配'" :disabled="!row.normalized" @change="value => changeAssignee(row, value)"><el-option v-if="!hasAssigneeChoice(row) && row.normalized?.assigneeUserName" :label="`未匹配：${row.normalized.assigneeUserName}`" value="__unresolved__" disabled /><el-option label="未分配" value="" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="assigneeLabel(member.userId)" :value="String(member.userId)" :disabled="!rowHasProductionItem(row)" /></el-select></template></el-table-column>
              <el-table-column label="描述 / 备注" min-width="280"><template #default="{ row }"><div class="description-cell">{{ row.normalized?.itemDescription || row.normalized?.assetDescription || '—' }}<small>{{ row.normalized?.remark || '' }}</small></div></template></el-table-column>
              <el-table-column label="预检结果" min-width="260"><template #default="{ row }"><div class="issue-list"><el-tag v-if="selectedAssigneeId(row)" size="small" type="success" effect="plain" round>已选择：{{ assigneeLabel(selectedAssigneeId(row)) }}</el-tag><el-tag v-else-if="hasAssigneeChoice(row)" size="small" type="success" effect="plain" round>将以未分配状态导入</el-tag><el-tag v-else-if="row.canImport && !row.warnings.length" size="small" type="success" effect="plain" round>可导入</el-tag><el-tag v-for="issue in visibleWarnings(row)" :key="`w-${issue.errorKey}-${issue.fieldName}`" size="small" type="warning" effect="plain" round>{{ issueText(issue) }}</el-tag><el-tag v-for="issue in visibleErrors(row)" :key="`e-${issue.errorKey}-${issue.fieldName}`" size="small" type="danger" effect="plain" round>{{ issueText(issue) }}</el-tag></div></template></el-table-column>
            </el-table>
          </div>
        </el-card>

        <footer><div><strong>正式提交将全量回滚任一失败行</strong><p>系统内部以 Sheet 和源数据行共同定位；Token 与幂等键只保存在当前对话框内存。</p></div><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">正式导入 {{ selectedRows.length }} 行</el-button></footer>
      </template>
    </div>

    <el-dialog v-model="showBatchAssign" class="import-batch-assign-dialog" title="批量分配制作人" width="480px" append-to-body :z-index="3100" destroy-on-close @closed="batchAssignForm.assigneeUserId = ''">
      <div class="batch-assign-content">
        <div class="batch-assign-summary"><span class="batch-assign-summary__icon"><el-icon><UserFilled /></el-icon></span><div><strong>已选择 {{ selectedPreviewRows.length }} 行</strong><p>确认后，仅当前勾选行的制作人会被更新。</p></div></div>
        <el-form ref="batchAssignFormRef" :model="batchAssignForm" :rules="batchAssignRules" label-position="top" aria-label="批量分配资产制作人表单"><el-form-item label="分配给" prop="assigneeUserId"><el-select v-model="batchAssignForm.assigneeUserId" class="batch-assignee-select" placeholder="请选择制作人"><el-option label="未分配" value="__unassigned__" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="assigneeLabel(member.userId)" :value="String(member.userId)" /></el-select><small>可选择“未分配”清空当前勾选行的制作人。</small></el-form-item></el-form>
      </div>
      <template #footer><div class="batch-assign-actions"><el-button @click="closeBatchAssignDialog">取消</el-button><el-button type="primary" :disabled="!batchAssignForm.assigneeUserId" @click="confirmBatchAssign">确认分配</el-button></div></template>
    </el-dialog>
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
.batch-assign-content { display: grid; gap: 18px; }
.batch-assign-summary { display: flex; gap: 13px; align-items: center; padding: 15px; background: linear-gradient(135deg,rgba(255,182,87,.12),rgba(255,182,87,.035)); border: 1px solid rgba(255,182,87,.22); border-radius: 12px; }
.batch-assign-summary__icon { display: grid; width: 38px; height: 38px; flex: 0 0 auto; color: var(--sg-accent); font-size: 18px; background: rgba(255,182,87,.13); border-radius: 10px; place-items: center; }
.batch-assign-summary strong { display: block; font-size: 14px; }
.batch-assign-summary p { margin: 5px 0 0; color: var(--sg-text-secondary); font-size: 11px; line-height: 1.5; }
.batch-assign-actions { display: flex; gap: 10px; justify-content: flex-end; }
footer { padding-top: 6px; }
footer > div { flex: 1; }
footer strong, footer p { display: block; margin: 0; }
footer p { margin-top: 4px; color: var(--sg-text-muted); font-size: 11px; }
:deep(.preview-table) { --el-table-border-color: var(--sg-border); --el-table-text-color: var(--sg-text-secondary); --el-table-header-text-color: var(--sg-text-muted); font-size: 11px; }
:deep(.preview-table .el-table__cell) { vertical-align: top; }
:deep(.preview-table .has-errors td.el-table__cell) { background: rgba(255,107,107,.045); }
:deep(.preview-table .has-warnings td.el-table__cell) { background: rgba(255,182,87,.035); }
@media (max-width: 900px) { .selection-toolbar, footer { align-items: stretch; flex-direction: column; } }
.file-picker { padding:0;background:rgba(255,255,255,.025);border-style:dashed;border-color:var(--sg-border-strong) }
.file-picker:deep(.el-card__body){display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto auto;gap:12px;align-items:center;padding:18px}
.file-picker:deep(.el-upload){display:block}.file-picker:deep(.el-upload .el-button){width:100%}.file-picker:deep(.el-icon){color:var(--sg-accent);font-size:28px}
.template-boundary{margin:-8px 0 0;padding:10px 12px}.import-error{display:block;padding:10px 12px}.import-error:deep(.el-alert__description){display:grid;gap:4px}.import-error code,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}
.import-success{display:block;padding:10px;background:rgba(98,212,155,.05);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success:deep(.el-result__extra){display:grid;width:100%;gap:14px;margin-top:20px}.import-success__metrics{width:100%}.created-types{justify-content:center}
.preview-summary{display:block}.preview-summary:deep(.el-descriptions__body),.preview-summary:deep(.el-descriptions__cell),.import-success__metrics:deep(.el-descriptions__body),.import-success__metrics:deep(.el-descriptions__cell){background:rgba(255,255,255,.025)!important;border-color:var(--sg-border)!important}.preview-summary:deep(.el-descriptions__label),.import-success__metrics:deep(.el-descriptions__label){color:var(--sg-text-muted);font-size:10px}.preview-summary:deep(.el-descriptions__content),.import-success__metrics:deep(.el-descriptions__content){color:var(--sg-text-secondary)}
.workbook-warnings{padding:10px 12px}.workbook-warnings:deep(.el-alert__description){margin-top:6px}.sheet-block{background:transparent;border-color:var(--sg-border)}.sheet-block:deep(.el-card__header){padding:0;border-bottom-color:var(--sg-border)}.sheet-block:deep(.el-card__body){padding:0}.assignee-select{width:100%;min-height:0;padding:0;background:transparent;border:0}.issue-list{display:flex;min-width:180px;gap:5px;align-items:flex-start;flex-direction:column}.issue-list:deep(.el-tag){height:auto;min-height:22px;white-space:normal;text-align:left}.batch-assignee-select{width:100%;height:auto;padding:0;border:0}.batch-assign-content:deep(.el-form-item){margin-bottom:0}.batch-assign-content:deep(.el-form-item__content){display:grid;gap:6px}.batch-assign-content small{color:var(--sg-text-muted);font-size:10px}
@media(max-width:900px){.file-picker:deep(.el-card__body){grid-template-columns:auto 1fr}.preview-summary:deep(.el-descriptions__table),.import-success__metrics:deep(.el-descriptions__table){table-layout:auto}}
</style>
