<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'

import {
  getAssetPage,
  getAssetRequirementPage,
  ignoreAssetRequirement,
  rematchAssetRequirements,
  resolveAssetRequirement
} from '@/api/shot-grid/assets'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { tagTypeFromTone } from '@/utils/tag'
import { assetErrorState, assetTypeMeta } from '@/views/asset/assetPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  canResolve: { type: Boolean, default: false },
  canIgnore: { type: Boolean, default: false },
  canRematch: { type: Boolean, default: false }
})
const emit = defineEmits(['close', 'updated'])
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const submitting = ref(false)
const error = ref(null)
const resolveVisible = ref(false)
const activeRequirement = ref(null)
const candidates = ref([])
const candidateLoading = ref(false)
const requirementFilterForm = ref(null)
const resolveFormRef = ref(null)
const resolveForm = reactive({ assetId: '', reason: '' })
const query = reactive({
  keyword: '',
  resolutionStatus: 'pending',
  assetType: '',
  pageNum: 1,
  pageSize: 20,
  orderByColumn: 'createTime',
  isAsc: 'descending'
})
const requirementFilterRules = {
  keyword: [{ max: 200, message: '搜索关键字不能超过 200 个字符', trigger: 'blur' }]
}
const resolveRules = {
  assetId: [{
    validator: (_rule, value, callback) => {
      if (!value) {
        callback(new Error('请选择同类型正式资产'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  reason: [{
    validator: (_rule, value, callback) => {
      if (!String(value || '').trim()) {
        callback(new Error('请填写解决原因'))
        return
      }
      callback()
    },
    trigger: 'blur'
  }]
}
let listController = null
let candidateController = null

function idempotencyKey(action, requirementId) {
  const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `asset-requirement-${action}-${props.projectId}-${requirementId}:${suffix}`
}

function stateMeta(status) {
  return {
    pending: { label: '待匹配', type: 'warning' },
    conflict: { label: '冲突', type: 'danger' },
    matched: { label: '已匹配', type: 'success' },
    ignored: { label: '已忽略', type: 'info' }
  }[status] || { label: status || '未知', type: 'info' }
}

function shotLabel(row) {
  return `EP${String(row.episodeNo).padStart(3, '0')} · 场${row.sceneNo} · 镜${row.shotNo}`
}

async function loadRequirements() {
  listController?.abort()
  const controller = new AbortController()
  listController = controller
  loading.value = true
  error.value = null
  try {
    const response = await getAssetRequirementPage(props.projectId, {
      keyword: query.keyword.trim() || undefined,
      resolutionStatus: query.resolutionStatus || undefined,
      assetType: query.assetType || undefined,
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: query.orderByColumn,
      isAsc: query.isAsc
    }, { signal: controller.signal })
    if (listController !== controller || controller.signal.aborted) return
    rows.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
  } catch (requestError) {
    if (requestError?.code !== 'ERR_CANCELED') error.value = assetErrorState(requestError, '资产需求加载失败')
  } finally {
    if (listController === controller) loading.value = false
  }
}

async function submitQuery() {
  const isValid = await requirementFilterForm.value?.validate().catch(() => false)
  if (!isValid) return
  query.pageNum = 1
  loadRequirements()
}

function changePage(page) {
  query.pageNum = page
  loadRequirements()
}

async function openResolve(row) {
  activeRequirement.value = row
  resolveForm.assetId = ''
  resolveForm.reason = ''
  candidates.value = []
  resolveVisible.value = true
  await nextTick()
  resolveFormRef.value?.clearValidate()
  candidateController?.abort()
  const controller = new AbortController()
  candidateController = controller
  candidateLoading.value = true
  try {
    const response = await getAssetPage(props.projectId, {
      assetType: row.assetType,
      pageNum: 1,
      pageSize: 100,
      orderByColumn: 'assetName',
      isAsc: 'ascending'
    }, { signal: controller.signal })
    if (candidateController === controller && !controller.signal.aborted) {
      candidates.value = (response.rows || []).filter(item => item.lifecycleStatus === 'active')
    }
  } catch (requestError) {
    if (requestError?.code !== 'ERR_CANCELED') ElMessage.error(assetErrorState(requestError, '候选资产加载失败').message)
  } finally {
    if (candidateController === controller) candidateLoading.value = false
  }
}

async function submitResolve() {
  if (submitting.value) return
  const isValid = await resolveFormRef.value?.validate().catch(() => false)
  if (!isValid) return
  submitting.value = true
  try {
    await resolveAssetRequirement(
      props.projectId,
      activeRequirement.value.requirementId,
      { assetId: Number(resolveForm.assetId), reason: resolveForm.reason.trim() },
      idempotencyKey('resolve', activeRequirement.value.requirementId)
    )
    resolveVisible.value = false
    ElMessage.success('资产需求已完成匹配')
    emit('updated')
    await loadRequirements()
  } catch (requestError) {
    ElMessage.error(assetErrorState(requestError, '资产需求匹配失败').message)
  } finally {
    submitting.value = false
  }
}

function closeResolve() {
  if (!submitting.value) resolveVisible.value = false
}

function resetResolveForm() {
  resolveForm.assetId = ''
  resolveForm.reason = ''
  activeRequirement.value = null
  candidates.value = []
  resolveFormRef.value?.clearValidate()
}

async function ignore(row) {
  try {
    const { value } = await ElMessageBox.prompt('请填写忽略原因，忽略后重新匹配不会覆盖该决定。', '忽略资产需求', {
      confirmButtonText: '确认忽略',
      cancelButtonText: '取消',
      inputPattern: /\S/,
      inputErrorMessage: '忽略原因不能为空',
      inputType: 'textarea'
    })
    submitting.value = true
    await ignoreAssetRequirement(
      props.projectId,
      row.requirementId,
      { reason: value.trim() },
      idempotencyKey('ignore', row.requirementId)
    )
    ElMessage.success('资产需求已忽略')
    emit('updated')
    await loadRequirements()
  } catch (requestError) {
    if (requestError !== 'cancel' && requestError !== 'close') {
      ElMessage.error(assetErrorState(requestError, '忽略资产需求失败').message)
    }
  } finally {
    submitting.value = false
  }
}

async function rematch() {
  submitting.value = true
  try {
    const response = await rematchAssetRequirements(props.projectId)
    ElMessage.success(`重新匹配完成：匹配 ${response.data.matchedCount}，待处理 ${response.data.pendingCount}，冲突 ${response.data.conflictCount}`)
    emit('updated')
    await loadRequirements()
  } catch (requestError) {
    ElMessage.error(assetErrorState(requestError, '重新匹配失败').message)
  } finally {
    submitting.value = false
  }
}

onMounted(loadRequirements)
onBeforeUnmount(() => {
  listController?.abort()
  candidateController?.abort()
})
</script>

<template>
  <ProjectModal title="资产待匹配需求" description="镜头导入不会隐式创建正式资产；在这里选择同类型正式资产、明确忽略，或重新执行项目级唯一匹配。" :busy="submitting" wide @close="emit('close')">
    <div class="requirement-dialog">
      <el-form ref="requirementFilterForm" :model="query" :rules="requirementFilterRules" class="requirement-filters" aria-label="资产需求筛选">
        <el-form-item prop="keyword"><el-input v-model="query.keyword" maxlength="200" clearable placeholder="搜索需求名称或匹配资产" :prefix-icon="Search" /></el-form-item>
        <el-form-item prop="resolutionStatus"><el-select v-model="query.resolutionStatus" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="待匹配" value="pending" /><el-option label="冲突" value="conflict" /><el-option label="已匹配" value="matched" /><el-option label="已忽略" value="ignored" /></el-select></el-form-item>
        <el-form-item prop="assetType"><el-select v-model="query.assetType" placeholder="全部类型"><el-option label="全部类型" value="" /><el-option label="角色" value="Character" /><el-option label="场景" value="Environment" /><el-option label="道具" value="Prop" /></el-select></el-form-item>
        <el-form-item class="requirement-filter-actions"><el-button :loading="loading" :icon="Search" @click="submitQuery">查询</el-button><el-button v-if="canRematch" :loading="submitting" :icon="Refresh" @click="rematch">重新匹配</el-button></el-form-item>
      </el-form>

      <el-alert v-if="error" :title="error.title" :description="error.message" type="error" show-icon :closable="false" />
      <el-table v-else :data="rows" v-loading="loading" empty-text="当前条件下没有资产需求" max-height="470">
        <el-table-column label="来源镜头" min-width="150"><template #default="{ row }"><strong>{{ shotLabel(row) }}</strong><small>#{{ row.shotId }}</small></template></el-table-column>
        <el-table-column label="类型 / 原始名称" min-width="190"><template #default="{ row }"><el-tag size="small" effect="plain" round :type="tagTypeFromTone(assetTypeMeta(row.assetType).tone)">{{ assetTypeMeta(row.assetType).label }}</el-tag><strong>{{ row.rawName }}</strong></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" effect="plain" round :type="stateMeta(row.resolutionStatus).type">{{ stateMeta(row.resolutionStatus).label }}</el-tag></template></el-table-column>
        <el-table-column label="处理结果" min-width="190"><template #default="{ row }"><strong>{{ row.assetName || '—' }}</strong><small>{{ row.resolutionReason || '尚未处理' }}</small></template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><template v-if="['pending','conflict'].includes(row.resolutionStatus)"><el-button v-if="canResolve" text type="primary" @click="openResolve(row)">选择资产</el-button><el-button v-if="canIgnore" text type="danger" @click="ignore(row)">忽略</el-button></template><span v-else>已处理</span></template></el-table-column>
      </el-table>

      <el-pagination v-if="total" background layout="total, prev, pager, next" :total="total" :page-size="query.pageSize" :current-page="query.pageNum" @current-change="changePage" />
    </div>

    <el-dialog v-model="resolveVisible" title="选择正式资产" width="520px" append-to-body :close-on-click-modal="!submitting" :close-on-press-escape="!submitting" :show-close="!submitting" @closed="resetResolveForm">
      <el-form ref="resolveFormRef" :model="resolveForm" :rules="resolveRules" label-position="top" aria-label="资产需求匹配表单">
        <el-form-item label="待匹配需求"><el-input :model-value="`${assetTypeMeta(activeRequirement?.assetType).label} · ${activeRequirement?.rawName || ''}`" disabled /></el-form-item>
        <el-form-item label="同类型正式资产" prop="assetId"><el-select v-model="resolveForm.assetId" filterable class="full-width" :loading="candidateLoading" :disabled="submitting" placeholder="请选择正式资产"><el-option v-for="asset in candidates" :key="asset.assetId" :label="asset.assetName" :value="String(asset.assetId)" /></el-select></el-form-item>
        <el-form-item label="解决原因" prop="reason"><el-input v-model="resolveForm.reason" type="textarea" :rows="3" maxlength="500" show-word-limit :disabled="submitting" placeholder="说明为何选择该资产" /></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="submitting" @click="closeResolve">取消</el-button><el-button type="primary" :loading="submitting" @click="submitResolve">确认匹配</el-button></template>
    </el-dialog>
  </ProjectModal>
</template>

<style scoped>
.requirement-dialog{display:grid;gap:16px}.requirement-filters{display:grid;grid-template-columns:minmax(220px,1fr) 150px 140px auto;gap:9px}.requirement-filters:deep(.el-form-item){min-width:0;margin-bottom:0}.requirement-filters:deep(.el-form-item__content),.requirement-filters:deep(.el-select),.requirement-filters:deep(.el-input){width:100%}.requirement-filter-actions:deep(.el-form-item__content){flex-wrap:nowrap}.el-table strong,.el-table small{display:block}.el-table strong{margin-top:5px}.el-table small{margin-top:4px;color:var(--sg-text-muted);line-height:1.45}.el-pagination{justify-content:flex-end}.full-width{width:100%}@media(max-width:760px){.requirement-filters{grid-template-columns:1fr}.requirement-filter-actions:deep(.el-form-item__content){flex-wrap:wrap}.el-pagination{justify-content:center}}
</style>
