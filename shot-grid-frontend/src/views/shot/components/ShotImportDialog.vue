<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { Document, UploadFilled } from '@element-plus/icons-vue'
import { genFileId } from 'element-plus'

import { commitShotImport, downloadShotImportTemplate, previewShotImport } from '@/api/shot-grid/shots'
import { createIdempotencyState } from '@/utils/idempotency'
import { groupPreviewRows, shotErrorState } from '@/views/shot/shotPresentation'
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
const idempotency = createIdempotencyState(`shot-import-${operationContext.projectId}`)
const uploadRef = ref(null)
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
let syncingTableSelection = false
const previewTableRefs = new Map()

const groupedRows = computed(() => groupPreviewRows(preview.value?.rows || []))
const selectedPreviewRows = computed(() => (preview.value?.rows || [])
  .filter(row => selectedKeys.value.has(rowKey(row))))
const selectedRows = computed(() => selectedPreviewRows.value
  .filter(row => row.canImport)
  .map(row => ({ sheetName: row.sheetName, rowNumber: row.rowNumber })))
const validRows = computed(() => (preview.value?.rows || []).filter(row => row.canImport))
const isBusy = computed(() => previewing.value || committing.value || downloading.value)

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
    selectedKeys.value = new Set((response.data?.rows || []).filter(row => row.canImport).map(row => rowKey(row)))
    await syncPreviewTableSelections()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') requestError.value = shotErrorState(error, '镜头 Excel 预览失败')
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
    link.download = '镜头导入模板-shot-v3.xlsx'
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
  if (!preview.value?.importToken) { validationMessage.value = '预览已失效，请重新预览导入内容'; return }
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

onBeforeUnmount(() => { previewController?.abort(); downloadController?.abort() })
</script>

<template>
  <ProjectModal title="导入镜头 Excel" :description="`将 Excel 中的镜头数据导入 ${projectName || '当前项目'}，解析后可预览并选择需要导入的内容。`" :busy="isBusy" wide @close="emit('close')">
    <div class="import-flow">
      <section class="file-picker" :class="{ 'has-file': file }">
        <el-icon><UploadFilled /></el-icon>
        <div><strong>{{ file?.name || '选择镜头 Excel 工作簿' }}</strong><p>{{ file ? `${(file.size / 1024).toFixed(1)} KiB` : '仅支持 .xlsx，最大 10 MiB；每个可见 EPnnn 工作表表示一集。' }}</p></div>
        <el-button link type="primary" :loading="downloading" :disabled="isBusy" @click="downloadTemplate">下载官方模板</el-button>
        <el-upload ref="uploadRef" class="file-picker__upload" action="#" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :auto-upload="false" :show-file-list="false" :limit="1" :disabled="isBusy" :on-change="chooseFile" :on-exceed="replaceFile"><el-button :icon="UploadFilled" :disabled="isBusy">{{ file ? '更换文件' : '选择文件' }}</el-button></el-upload>
        <el-button type="primary" :loading="previewing" :disabled="!file || committing" @click="runPreview">{{ preview ? '重新预览' : '预览导入内容' }}</el-button>
      </section>

      <el-alert v-if="validationMessage || requestError" class="import-alert" :type="requestError ? 'error' : 'warning'" :closable="false" show-icon :title="requestError?.title || '请处理后再继续'"><div class="import-alert__content"><p>{{ requestError?.message || validationMessage }}</p></div></el-alert>

      <section v-if="commitResult" class="import-success" role="status">
        <div><p class="sg-eyebrow">IMPORT COMPLETE</p><h3>镜头导入完成</h3><p>{{ commitResult.idempotentReplay ? '系统已确认本次导入完成，未重复创建数据。' : '所选镜头已成功导入。' }}</p></div>
        <div class="import-success__metrics">
          <el-statistic title="已导入行" :value="Number(commitResult.committedRows || 0)" />
          <el-statistic title="新建集" :value="Number(commitResult.createdEpisodes || 0)" />
          <el-statistic title="新建场次" :value="Number(commitResult.createdScenes || 0)" />
          <el-statistic title="新建镜头" :value="Number(commitResult.createdShots || 0)" />
          <el-statistic title="待匹配场景" :value="Number(commitResult.createdAssetRequirements || 0)" />
        </div>
        <el-button type="primary" @click="emit('close')">完成</el-button>
      </section>

      <template v-else-if="preview">
        <section class="shot-preview-summary">
          <div><span class="shot-preview-summary__label">有效 / 总行</span><strong class="shot-preview-summary__value">{{ validRows.length }} / {{ preview.summary.totalRows }}</strong></div>
          <div><span class="shot-preview-summary__label">含警告行</span><el-tag class="shot-preview-summary__tag" size="small" effect="plain" round type="warning">{{ preview.summary.warningRows }}</el-tag></div>
          <div><span class="shot-preview-summary__label">错误行</span><el-tag class="shot-preview-summary__tag" size="small" effect="plain" round type="danger">{{ preview.summary.errorRows }}</el-tag></div>
          <div><span class="shot-preview-summary__label">集 / 场次 / 镜头</span><strong class="shot-preview-summary__value">{{ preview.summary.distinctEpisodes }} / {{ preview.summary.distinctScenes }} / {{ preview.summary.distinctShots }}</strong></div>
          <div><span class="shot-preview-summary__label">导入有效期</span><el-tooltip content="预览结果为临时数据，超过该时间后需要重新预览。" placement="top"><strong class="shot-preview-summary__value">{{ formatPreviewExpiry(preview.expiresAt) }}</strong></el-tooltip></div>
        </section>

        <section v-if="preview.workbookWarnings?.length" class="workbook-warnings">
          <strong>工作簿提醒</strong><ul><li v-for="issue in preview.workbookWarnings" :key="`${issue.errorKey}-${issue.message}`">{{ issue.message }}</li></ul>
        </section>

        <el-alert class="assignment-boundary" title="导入后可在镜头列表统一分配制作任务" type="info" show-icon :closable="false" />
        <div class="selection-toolbar"><span>已选择 {{ selectedRows.length }} 条</span></div>

        <section v-for="(rows, sheetName) in groupedRows" :key="sheetName" class="sheet-block">
          <header><div><el-icon><Document /></el-icon><strong>{{ sheetName }}</strong><span>{{ rows.length }} 行</span></div></header>
          <div class="preview-table-wrap">
            <el-table :ref="instance => setPreviewTableRef(sheetName, instance)" :data="rows" :row-key="rowKey" :row-class-name="previewRowClass" class="preview-table" max-height="320" @selection-change="selection => handleSheetSelection(rows, selection)">
              <el-table-column type="selection" width="55" :selectable="rowCanSelect" />
              <el-table-column label="场次" min-width="150"><template #default="{ row }">{{ row.normalized?.sceneCode || '—' }} {{ row.normalized?.sceneName || '' }}</template></el-table-column>
              <el-table-column label="镜头" width="100"><template #default="{ row }">{{ row.normalized?.shotCode || '—' }}</template></el-table-column>
              <el-table-column label="时长" width="100"><template #default="{ row }">{{ row.normalized ? `${row.normalized.durationMs} ms` : '—' }}</template></el-table-column>
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
              <el-table-column label="数据状态" min-width="250"><template #default="{ row }"><div class="issue-list"><el-tag v-if="row.canImport && !row.warnings.length" type="success" effect="plain" size="small">正常</el-tag><el-tag v-for="issue in visibleWarnings(row)" :key="`w-${issue.errorKey}-${issue.fieldName}`" type="warning" effect="plain" size="small">{{ issueText(issue) }}</el-tag><el-tag v-for="issue in visibleErrors(row)" :key="`e-${issue.errorKey}-${issue.fieldName}`" type="danger" effect="plain" size="small">{{ issueText(issue) }}</el-tag></div></template></el-table-column>
            </el-table>
          </div>
        </section>

        <footer><el-button :disabled="isBusy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="committing" :disabled="!selectedRows.length" @click="commitImport">确认导入 {{ selectedRows.length }} 条</el-button></footer>
      </template>
    </div>
  </ProjectModal>
</template>

<style scoped>
.import-flow{display:grid;gap:18px}.file-picker{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto auto;gap:14px;align-items:center;padding:18px;background:rgba(255,255,255,.025);border:1px dashed var(--sg-border-strong);border-radius:14px}.file-picker.has-file{border-style:solid;border-color:rgba(255,182,87,.35)}.file-picker>.el-icon{color:var(--sg-accent);font-size:28px}.file-picker strong,.file-picker p{display:block;margin:0}.file-picker p{margin-top:5px;color:var(--sg-text-muted);font-size:11px}.import-alert__content{display:grid;gap:5px}.import-alert__content p{margin:0;font-size:12px}.import-alert__content code,.import-alert__content small,.workbook-warnings code{color:var(--sg-text-muted);font-size:10px}.import-success{display:grid;gap:18px;padding:22px;background:rgba(98,212,155,.07);border:1px solid rgba(98,212,155,.2);border-radius:14px}.import-success h3,.import-success p{margin:0}.import-success>div>p:last-child{margin-top:6px;color:var(--sg-text-secondary);font-size:12px}.workbook-warnings{padding:14px;color:var(--sg-accent);font-size:12px;background:var(--sg-accent-soft);border-radius:10px}.workbook-warnings ul{margin:8px 0 0;padding-left:18px}.selection-toolbar,.sheet-block header,footer{display:flex;gap:14px;align-items:center;justify-content:space-between}.selection-toolbar{min-height:32px;color:var(--sg-text-muted);font-size:12px;flex-wrap:wrap}.sheet-block{overflow:hidden;border:1px solid var(--sg-border);border-radius:12px}.sheet-block header{padding:12px 14px;background:rgba(255,255,255,.03)}.sheet-block header div{display:flex;gap:8px;align-items:center}.sheet-block header span{color:var(--sg-text-muted);font-size:11px}.preview-table-wrap{overflow:hidden}.description-cell{min-width:260px;max-width:320px;line-height:1.55}.long-text-cell{min-width:150px;max-width:240px;line-height:1.55;white-space:pre-wrap}footer{justify-content:flex-end;padding-top:6px}:deep(.preview-table){--el-table-border-color:var(--sg-border);--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);font-size:11px}:deep(.preview-table .el-table__cell){vertical-align:top}:deep(.preview-table .has-errors td.el-table__cell){background:rgba(255,107,107,.045)}:deep(.preview-table .has-warnings td.el-table__cell){background:rgba(255,182,87,.035)}@media(max-width:760px){.file-picker{grid-template-columns:auto 1fr}.selection-toolbar,footer{align-items:stretch;flex-direction:column}}
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
.issue-list { display: flex; min-width: 180px; flex-wrap: wrap; gap: 5px; }
.issue-list .el-tag { max-width: 100%; height: auto; min-height: 24px; white-space: normal; }
.assignment-boundary { margin-top: -4px; }
.import-success__metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.import-success__metrics :deep(.el-statistic) { padding: 11px; background: rgba(0, 0, 0, 0.15); border-radius: 8px; }
.import-success__metrics :deep(.el-statistic__head) { margin-bottom: 4px; color: var(--sg-text-muted); font-size: 10px; }
.import-success__metrics :deep(.el-statistic__number) { color: var(--sg-text); font-size: 18px; }

@media (max-width: 760px) {
  .shot-preview-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .import-success__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
