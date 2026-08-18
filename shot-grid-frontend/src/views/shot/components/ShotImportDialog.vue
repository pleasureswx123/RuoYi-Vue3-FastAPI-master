<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { Document, UserFilled, UploadFilled } from '@element-plus/icons-vue'
import { genFileId } from 'element-plus'

import { commitShotImport, downloadShotImportTemplate, previewShotImport } from '@/api/shot-grid/shots'
import { createIdempotencyState } from '@/utils/idempotency'
import { groupPreviewRows, shotErrorState } from '@/views/shot/shotPresentation'
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
const idempotency = createIdempotencyState(`shot-import-${operationContext.projectId}`)
const uploadRef = ref(null)
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
let syncingTableSelection = false
const previewTableRefs = new Map()

const groupedRows = computed(() => groupPreviewRows(preview.value?.rows || []))
const selectedPreviewRows = computed(() => (preview.value?.rows || [])
  .filter(row => selectedKeys.value.has(rowKey(row))))
const selectedRows = computed(() => selectedPreviewRows.value
  .filter(row => rowCanImport(row))
  .map(row => {
    const selected = { sheetName: row.sheetName, rowNumber: row.rowNumber }
    if (hasAssigneeChoice(row)) selected.assigneeUserId = selectedAssigneeId(row)
    return selected
  }))
const validRows = computed(() => (preview.value?.rows || []).filter(row => rowCanImport(row)))
const overriddenRowCount = computed(() => (preview.value?.rows || []).filter(row => {
  return hasOnlyAssigneeErrors(row) && hasAssigneeChoice(row)
}).length)
const assignableMembers = computed(() => props.members.filter(member => member.projectRole === 'creator'))
const isBusy = computed(() => previewing.value || committing.value || downloading.value)
const batchAssignModel = computed(() => ({ assigneeUserId: batchAssigneeUserId.value }))

function rowKey(row) {
  return `${row.sheetName}::${row.rowNumber}`
}

function selectedAssigneeId(row) {
  if (!hasAssigneeChoice(row)) return null
  const value = Number(assigneeByRow.value.get(rowKey(row)))
  return Number.isSafeInteger(value) && value > 0 ? value : null
}

function hasAssigneeChoice(row) {
  return assigneeByRow.value.has(rowKey(row))
}

function assigneeSelectValue(row) {
  if (hasAssigneeChoice(row)) return selectedAssigneeId(row) || ''
  return row.normalized?.assigneeUserName ? '__unresolved__' : ''
}

function isAssigneeIssue(issue) {
  return issue?.fieldName === 'assigneeUserName'
}

function hasOnlyAssigneeErrors(row) {
  return Boolean(row.normalized && row.errors?.length && row.errors.every(isAssigneeIssue))
}

function rowCanImport(row) {
  return Boolean(row.canImport || (hasOnlyAssigneeErrors(row) && hasAssigneeChoice(row)))
}

function rowCanSelect(row) {
  return Boolean(rowCanImport(row) || hasOnlyAssigneeErrors(row))
}

function visibleWarnings(row) {
  return hasAssigneeChoice(row) ? (row.warnings || []).filter(issue => !isAssigneeIssue(issue)) : (row.warnings || [])
}

function visibleErrors(row) {
  return hasAssigneeChoice(row) ? (row.errors || []).filter(issue => !isAssigneeIssue(issue)) : (row.errors || [])
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

function changeAssignee(row, rawValue) {
  const userId = Number(rawValue)
  const nextAssignees = new Map(assigneeByRow.value)
  if (Number.isSafeInteger(userId) && userId > 0) nextAssignees.set(rowKey(row), userId)
  else nextAssignees.set(rowKey(row), null)
  assigneeByRow.value = nextAssignees

  const nextSelected = new Set(selectedKeys.value)
  if (rowCanImport(row)) nextSelected.add(rowKey(row))
  else if (!row.canImport) nextSelected.delete(rowKey(row))
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
    validationMessage.value = '请先勾选需要批量设置的镜头'
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

function chooseFile(uploadFile) {
  resetPreview()
  const nextFile = uploadFile?.raw || null
  if (!nextFile) { file.value = null; return }
  if (!/\.xlsx$/i.test(nextFile.name)) {
    validationMessage.value = '镜头导入只接受 .xlsx 工作簿'
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
}

function replaceFile(files) {
  const nextFile = files?.[0]
  if (!nextFile) return
  uploadRef.value?.clearFiles()
  nextFile.uid = genFileId()
  uploadRef.value?.handleStart(nextFile)
}

async function runPreview() {
  validationMessage.value = ''
  requestError.value = null
  commitResult.value = null
  if (!file.value) { validationMessage.value = '请先选择镜头 Excel 文件'; return }
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller
  previewing.value = true
  try {
    const response = await previewShotImport(operationContext.projectId, file.value, { signal: controller.signal })
    preview.value = response.data
    initializeAssignees(response.data?.rows || [])
    selectedKeys.value = new Set((response.data?.rows || []).filter(row => rowCanImport(row)).map(row => rowKey(row)))
    await syncPreviewTableSelections()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') requestError.value = shotErrorState(error, '镜头 Excel 预检查失败')
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
  try {
    const blob = await downloadShotImportTemplate({ signal: controller.signal })
    if (downloadController !== controller || controller.signal.aborted) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '镜头导入模板-shot-v1.xlsx'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
      requestError.value = shotErrorState(error, '镜头 Excel 模板下载失败')
    }
  } finally {
    if (downloadController === controller) downloading.value = false
  }
}

async function commitImport() {
  validationMessage.value = ''
  requestError.value = null
  if (!preview.value?.importToken) { validationMessage.value = '预检 Token 不存在，请重新预检'; return }
  if (selectedPreviewRows.value.length !== selectedRows.value.length) {
    validationMessage.value = '选中行仍有未解决的制作人问题，请先改选或清空制作人'
    return
  }
  if (!selectedRows.value.length) { validationMessage.value = '至少选择一条可导入镜头'; return }
  const payload = { importToken: preview.value.importToken, selectedRows: selectedRows.value }
  committing.value = true
  try {
    const response = await commitShotImport(operationContext.projectId, payload, idempotency.forPayload(payload))
    commitResult.value = response.data
    emit('imported', response.data, operationContext)
  } catch (error) {
    requestError.value = shotErrorState(error, '镜头 Excel 正式导入失败')
  } finally { committing.value = false }
}

function issueText(issue) {
  return [issue.fieldName, issue.message].filter(Boolean).join('：')
}

function detailsText(details) {
  if (!details) return ''
  if (typeof details === 'string') return details
  try { return JSON.stringify(details) } catch { return '后端返回了额外诊断信息' }
}

onBeforeUnmount(() => { previewController?.abort(); downloadController?.abort() })
</script>

<template>
  <ProjectModal title="导入镜头 Excel" :description="`预检 ${projectName || '当前项目'} 的全部可见 EPnnn Sheet，确认跨 Sheet 行后再以单事务正式提交。`" :busy="isBusy" wide @close="emit('close')">
    <div class="import-flow">
      <section class="file-picker" :class="{ 'has-file': file }">
        <el-icon><UploadFilled /></el-icon>
        <div><strong>{{ file?.name || '选择镜头 Excel 工作簿' }}</strong><p>{{ file ? `${(file.size / 1024).toFixed(1)} KiB` : '仅支持 .xlsx，最大 10 MiB；每个可见 EPnnn Sheet 表示一集。' }}</p></div>
        <el-button link type="primary" :loading="downloading" :disabled="isBusy" @click="downloadTemplate">下载官方模板</el-button>
        <el-upload ref="uploadRef" class="file-picker__upload" action="#" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :auto-upload="false" :show-file-list="false" :limit="1" :disabled="isBusy" :on-change="chooseFile" :on-exceed="replaceFile"><el-button :icon="UploadFilled" :disabled="isBusy">{{ file ? '更换文件' : '选择文件' }}</el-button></el-upload>
        <el-button type="primary" :loading="previewing" :disabled="!file || committing" @click="runPreview">{{ preview ? '重新预检' : '开始预检' }}</el-button>
      </section>

      <el-alert v-if="validationMessage || requestError" class="import-alert" :type="requestError ? 'error' : 'warning'" :closable="false" show-icon :title="requestError?.title || '请检查导入条件'"><div class="import-alert__content"><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><small v-if="requestError?.details">{{ detailsText(requestError.details) }}</small></div></el-alert>

      <section v-if="commitResult" class="import-success" role="status">
        <div><p class="sg-eyebrow">IMPORT COMPLETE</p><h3>镜头已按单事务完成导入</h3><p>{{ commitResult.idempotentReplay ? '本次返回来自后端幂等结果快照，没有重复创建数据。' : '正式提交成功；页面列表已可以刷新。' }}</p></div>
        <div class="import-success__metrics">
          <el-statistic title="提交行" :value="Number(commitResult.committedRows || 0)" />
          <el-statistic title="新建集" :value="Number(commitResult.createdEpisodes || 0)" />
          <el-statistic title="新建场次" :value="Number(commitResult.createdScenes || 0)" />
          <el-statistic title="新建镜头" :value="Number(commitResult.createdShots || 0)" />
          <el-statistic title="新建任务" :value="Number(commitResult.createdTasks || 0)" />
          <el-statistic title="待匹配场景" :value="Number(commitResult.createdAssetRequirements || 0)" />
        </div>
        <el-button type="primary" @click="emit('close')">完成</el-button>
      </section>

      <template v-else-if="preview">
        <section class="shot-preview-summary">
          <div><span class="shot-preview-summary__label">有效 / 总行</span><strong class="shot-preview-summary__value">{{ validRows.length }} / {{ preview.summary.totalRows }}</strong></div>
          <div><span class="shot-preview-summary__label">含警告行</span><el-tag class="shot-preview-summary__tag" size="small" effect="plain" round type="warning">{{ preview.summary.warningRows }}</el-tag></div>
          <div><span class="shot-preview-summary__label">错误行</span><el-tag class="shot-preview-summary__tag" size="small" effect="plain" round type="danger">{{ preview.summary.errorRows }}<template v-if="overriddenRowCount"> · 已改选 {{ overriddenRowCount }}</template></el-tag></div>
          <div><span class="shot-preview-summary__label">集 / 场次 / 镜头</span><strong class="shot-preview-summary__value">{{ preview.summary.distinctEpisodes }} / {{ preview.summary.distinctScenes }} / {{ preview.summary.distinctShots }}</strong></div>
          <div><span class="shot-preview-summary__label">Token 到期</span><strong class="shot-preview-summary__value">{{ new Date(preview.expiresAt).toLocaleTimeString('zh-CN') }}</strong></div>
        </section>

        <section v-if="preview.workbookWarnings?.length" class="workbook-warnings">
          <strong>工作簿级警告</strong><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }} <code>{{ issue.errorKey }}</code></li></ul>
        </section>

        <div class="selection-toolbar"><span>已选 {{ selectedPreviewRows.length }} 行 · {{ selectedRows.length }} 条可导入</span><el-button v-if="selectedPreviewRows.length" type="primary" plain @click="openBatchAssignDialog">批量分配</el-button></div>

        <section v-for="(rows, sheetName) in groupedRows" :key="sheetName" class="sheet-block">
          <header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><span>{{ rows.length }} 行</span></div></header>
          <div class="preview-table-wrap">
            <el-table :ref="instance => setPreviewTableRef(sheetName, instance)" :data="rows" :row-key="rowKey" :row-class-name="previewRowClass" class="preview-table" max-height="320" @selection-change="selection => handleSheetSelection(rows, selection)">
              <el-table-column type="selection" width="55" :selectable="rowCanSelect" />
              <el-table-column label="场次" min-width="150"><template #default="{ row }">{{ row.normalized?.sceneCode || '—' }} {{ row.normalized?.sceneName || '' }}</template></el-table-column>
              <el-table-column label="镜头" width="100"><template #default="{ row }">{{ row.normalized?.shotCode || '—' }}</template></el-table-column>
              <el-table-column label="时长" width="100"><template #default="{ row }">{{ row.normalized ? `${row.normalized.durationMs} ms` : '—' }}</template></el-table-column>
              <el-table-column label="制作人" width="210"><template #default="{ row }"><el-select class="import-assignee-select" :model-value="assigneeSelectValue(row)" :aria-label="`选择 ${sheetName} 第 ${row.rowNumber} 行制作人`" :disabled="!row.normalized" placeholder="未分配" @change="value => changeAssignee(row, value)"><el-option v-if="!hasAssigneeChoice(row) && row.normalized?.assigneeUserName" label="未匹配：制作人不在项目成员中" value="__unresolved__" disabled /><el-option label="未分配" value="" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="assigneeLabel(member.userId)" :value="member.userId" /></el-select></template></el-table-column>
              <el-table-column label="制作内容" min-width="280"><template #default="{ row }"><div class="description-cell">{{ row.normalized?.description || '—' }}</div></template></el-table-column>
              <el-table-column label="景别" width="100"><template #default="{ row }">{{ row.normalized?.shotSize || '—' }}</template></el-table-column>
              <el-table-column label="机位" width="110"><template #default="{ row }">{{ row.normalized?.cameraPosition || '—' }}</template></el-table-column>
              <el-table-column label="镜头运动" width="120"><template #default="{ row }">{{ row.normalized?.cameraMovement || '—' }}</template></el-table-column>
              <el-table-column label="焦段" width="90"><template #default="{ row }">{{ row.normalized?.focalLength || '—' }}</template></el-table-column>
              <el-table-column label="台词 / 对白" min-width="180"><template #default="{ row }"><div class="long-text-cell">{{ row.normalized?.dialogue || '—' }}</div></template></el-table-column>
              <el-table-column label="音效" min-width="160"><template #default="{ row }"><div class="long-text-cell">{{ row.normalized?.soundEffect || '—' }}</div></template></el-table-column>
              <el-table-column label="色调参考" min-width="160"><template #default="{ row }"><div class="long-text-cell">{{ row.normalized?.colorReference || '—' }}</div></template></el-table-column>
              <el-table-column label="备注" min-width="160"><template #default="{ row }"><div class="long-text-cell">{{ row.normalized?.remark || '—' }}</div></template></el-table-column>
              <el-table-column label="场景需求" min-width="160"><template #default="{ row }">{{ row.normalized?.assetRequirements?.map(item => item.rawName).join('、') || '—' }}</template></el-table-column>
              <el-table-column label="预检结果" min-width="250"><template #default="{ row }"><div class="issue-list"><el-tag v-if="selectedAssigneeId(row)" type="success" effect="plain" size="small">已选择：{{ assigneeLabel(selectedAssigneeId(row)) }}</el-tag><el-tag v-else-if="hasAssigneeChoice(row)" type="success" effect="plain" size="small">将以未分配状态导入</el-tag><el-tag v-else-if="row.canImport && !row.warnings.length" type="success" effect="plain" size="small">可导入</el-tag><el-tag v-for="issue in visibleWarnings(row)" :key="`w-${issue.errorKey}-${issue.fieldName}`" type="warning" effect="plain" size="small">{{ issueText(issue) }}</el-tag><el-tag v-for="issue in visibleErrors(row)" :key="`e-${issue.errorKey}-${issue.fieldName}`" type="danger" effect="plain" size="small">{{ issueText(issue) }}</el-tag></div></template></el-table-column>
            </el-table>
          </div>
        </section>

        <footer><div><strong>正式提交将全量回滚任一失败行</strong><p>系统内部以 Sheet 和源数据行共同定位，重复点击会复用同一幂等键。</p></div><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">正式导入 {{ selectedRows.length }} 行</el-button></footer>
      </template>
    </div>

    <el-dialog v-model="showBatchAssign" class="import-batch-assign-dialog" title="批量分配制作人" width="480px" append-to-body :z-index="3100" destroy-on-close @closed="batchAssigneeUserId = ''">
      <div class="batch-assign-content">
        <div class="batch-assign-summary"><span class="batch-assign-summary__icon"><el-icon><UserFilled /></el-icon></span><div><strong>已选择 {{ selectedPreviewRows.length }} 行</strong><p>确认后，仅当前勾选行的制作人会被更新。</p></div></div>
        <el-form :model="batchAssignModel" class="batch-assign-form" size="large" label-position="top"><el-form-item label="分配给" prop="assigneeUserId"><el-select v-model="batchAssigneeUserId" class="sg-select batch-assignee-select" aria-label="批量分配镜头制作人" placeholder="请选择制作人"><el-option label="未分配" value="__unassigned__" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="assigneeLabel(member.userId)" :value="String(member.userId)" /></el-select><small>可选择“未分配”清空当前勾选行的制作人。</small></el-form-item></el-form>
      </div>
      <template #footer><div class="batch-assign-actions"><el-button size="large" @click="closeBatchAssignDialog">取消</el-button><el-button size="large" type="primary" :disabled="!batchAssigneeUserId" @click="confirmBatchAssign">确认分配</el-button></div></template>
    </el-dialog>
  </ProjectModal>
</template>

<style scoped>
.import-flow{display:grid;gap:18px}.file-picker{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto;gap:14px;align-items:center;padding:18px;background:rgba(255,255,255,.025);border:1px dashed var(--sg-border-strong);border-radius:14px}.file-picker.has-file{border-style:solid;border-color:rgba(255,182,87,.35)}.file-picker>.el-icon{color:var(--sg-accent);font-size:28px}.file-picker strong,.file-picker p{display:block;margin:0}.file-picker p{margin-top:5px;color:var(--sg-text-muted);font-size:11px}.file-picker label input{position:absolute;width:1px;height:1px;opacity:0}.file-picker label span{color:var(--sg-accent);font-size:12px;cursor:pointer}.file-picker label span{display:block;padding:9px 12px;background:var(--sg-accent-soft);border-radius:8px}.import-alert__content{display:grid;gap:5px}.import-alert__content p{margin:0;font-size:12px}.import-alert__content code,.import-alert__content small,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}.import-success{display:grid;gap:18px;padding:22px;background:rgba(98,212,155,.07);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success h3,.import-success p{margin:0}.import-success>div>p:last-child{margin-top:6px;color:var(--sg-text-secondary);font-size:12px}.import-success dl{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:0}.import-success dl div{padding:11px;background:rgba(0,0,0,.15);border-radius:8px}.import-success dt{color:var(--sg-text-muted);font-size:10px}.import-success dd{margin:4px 0 0;font-size:18px}.preview-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.preview-summary div{padding:13px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.preview-summary span,.preview-summary strong{display:block}.preview-summary span{color:var(--sg-text-muted);font-size:10px}.preview-summary strong{margin-top:5px}.preview-summary strong small{font-size:10px;font-weight:500}.preview-summary strong[data-tone=warning]{color:var(--sg-accent)}.preview-summary strong[data-tone=danger]{color:var(--sg-danger)}.workbook-warnings{padding:14px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:10px}.workbook-warnings ul{margin:8px 0 0;padding-left:18px}.selection-toolbar,.sheet-block header,footer{display:flex;gap:14px;align-items:center;justify-content:space-between}.selection-toolbar{min-height:32px;color:var(--sg-text-muted);font-size:12px;flex-wrap:wrap}.sheet-block{overflow:hidden;border:1px solid var(--sg-border);border-radius:12px}.sheet-block header{padding:12px 14px;background:rgba(255,255,255,.03)}.sheet-block header div{display:flex;gap:8px;align-items:center}.sheet-block header span{color:var(--sg-text-muted);font-size:11px}.preview-table-wrap{overflow:hidden}.assignee-select{width:170px;min-height:32px;padding:0 8px;color:var(--sg-text);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:7px}.assignee-select:focus{border-color:var(--sg-accent);outline:0}.assignee-select:disabled{cursor:not-allowed;opacity:.5}.description-cell{min-width:260px;max-width:320px;line-height:1.55}.long-text-cell{min-width:150px;max-width:240px;line-height:1.55;white-space:pre-wrap}.issue-list{min-width:180px;margin:0;padding:0;list-style:none}.issue-list li{margin-bottom:4px;color:var(--sg-success)}.issue-list li[data-tone=success]{color:var(--sg-success)}.issue-list li[data-tone=warning]{color:var(--sg-accent)}.issue-list li[data-tone=danger]{color:var(--sg-danger)}.batch-assign-content{display:grid;gap:12px}.batch-assign-content p{margin:0;color:var(--sg-text-muted);font-size:12px}.batch-assign-content label{display:grid;gap:8px}.batch-assign-content label span{color:var(--sg-text-secondary);font-size:12px}footer{padding-top:6px}footer>div{flex:1}footer strong,footer p{display:block;margin:0}footer p{margin-top:4px;color:var(--sg-text-muted);font-size:11px}:deep(.preview-table){--el-table-border-color:var(--sg-border);--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);font-size:11px}:deep(.preview-table .el-table__cell){vertical-align:top}:deep(.preview-table .has-errors td.el-table__cell){background:rgba(255,107,107,.045)}:deep(.preview-table .has-warnings td.el-table__cell){background:rgba(255,182,87,.035)}@media(max-width:760px){.file-picker{grid-template-columns:auto 1fr}.preview-summary,.import-success dl{grid-template-columns:repeat(2,minmax(0,1fr))}.selection-toolbar,footer{align-items:stretch;flex-direction:column}}
.batch-assign-content{display:grid;gap:18px}.batch-assign-summary{display:flex;gap:13px;align-items:center;padding:15px;background:linear-gradient(135deg,rgba(255,182,87,.12),rgba(255,182,87,.035));border:1px solid rgba(255,182,87,.22);border-radius:12px}.batch-assign-summary__icon{display:grid;width:38px;height:38px;flex:0 0 auto;color:var(--sg-accent);font-size:18px;background:rgba(255,182,87,.13);border-radius:10px;place-items:center}.batch-assign-summary strong{display:block;font-size:14px}.batch-assign-summary p{margin:5px 0 0;color:var(--sg-text-secondary);font-size:11px;line-height:1.5}.batch-assign-field{display:grid;gap:8px}.batch-assign-field>span{color:var(--sg-text-secondary);font-size:12px;font-weight:600}.batch-assign-field small{color:var(--sg-text-muted);font-size:10px}.batch-assignee-select{width:100%}.batch-assign-actions{display:flex;gap:10px;justify-content:flex-end}
.shot-preview-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.shot-preview-summary > div {
  padding: 13px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--sg-border);
  border-radius: 10px;
}

.shot-preview-summary__label,
.shot-preview-summary__value { display: block; }

.shot-preview-summary__label {
  color: var(--sg-text-muted);
  font-size: 10px;
}

.shot-preview-summary__value,
.shot-preview-summary__tag { margin-top: 5px; }

.file-picker__upload { justify-self: start; }
.import-assignee-select { width: 190px; }
.issue-list { display: flex; min-width: 180px; flex-wrap: wrap; gap: 5px; }
.issue-list .el-tag { max-width: 100%; height: auto; min-height: 24px; white-space: normal; }
.batch-assign-form:deep(.el-form-item) { margin-bottom: 0; }
.batch-assign-form:deep(.el-form-item__label) { color: var(--sg-text-secondary); font-size: 12px; font-weight: 600; }
.batch-assign-form:deep(.el-form-item__content) { display: grid; width: 100%; gap: 8px; }
.batch-assign-form:deep(.el-select) { width: 100%; }
.batch-assign-form small { color: var(--sg-text-muted); font-size: 10px; }
.import-success__metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
.import-success__metrics :deep(.el-statistic) { padding: 11px; background: rgba(0, 0, 0, 0.15); border-radius: 8px; }
.import-success__metrics :deep(.el-statistic__head) { margin-bottom: 4px; color: var(--sg-text-muted); font-size: 10px; }
.import-success__metrics :deep(.el-statistic__number) { color: var(--sg-text); font-size: 18px; }

@media (max-width: 760px) {
  .shot-preview-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .import-success__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
