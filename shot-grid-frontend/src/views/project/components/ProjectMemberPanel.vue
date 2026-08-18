<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'

import {
  addProjectMember,
  getProjectMembers,
  removeProjectMember,
  updateProjectMember
} from '@/api/shot-grid/projects'
import { projectErrorState, projectRoleMeta, formatDateTime } from '@/views/project/projectPresentation'
import MemberCandidateSelect from './MemberCandidateSelect.vue'
import ProjectModal from './ProjectModal.vue'
import ProjectStatePanel from './ProjectStatePanel.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  canManage: { type: Boolean, default: false },
  permissions: { type: Array, default: () => [] }
})
const members = ref([])
const loading = ref(false)
const mutationBusy = ref(false)
const errorState = ref(null)
const mutationError = ref(null)
const selectedCandidate = ref(null)
const editingMember = ref(null)
const addFormRef = ref(null)
const editFormRef = ref(null)
const addForm = reactive({ projectRole: 'creator' })
const editForm = reactive({ projectRole: 'creator' })
const memberRules = {
  projectRole: [{
    validator: (_rule, value, callback) => {
      if (!['creator', 'director'].includes(value)) callback(new Error('请选择有效的项目角色'))
      else callback()
    },
    trigger: 'change'
  }]
}
let controller = null

const wildcard = computed(() => props.permissions.includes('*:*:*'))
const canAdd = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:add')))
const canEdit = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:edit')))
const canRemove = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:remove')))
const selectedIds = computed(() => members.value.map(member => member.userId))

async function loadMembers() {
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  errorState.value = null
  try {
    const response = await getProjectMembers(props.projectId, {}, { signal: requestController.signal })
    members.value = Array.isArray(response.rows) ? response.rows : []
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') errorState.value = projectErrorState(error, '项目成员加载失败')
  } finally {
    if (controller === requestController) loading.value = false
  }
}

function chooseCandidate(candidate) {
  selectedCandidate.value = candidate
  addForm.projectRole = 'creator'
  mutationError.value = null
}

function openEdit(member) {
  editingMember.value = member
  editForm.projectRole = member.projectRole
  mutationError.value = null
}

function closeAddDialog() {
  addFormRef.value?.resetFields()
  selectedCandidate.value = null
  mutationError.value = null
}

function closeEditDialog() {
  editFormRef.value?.resetFields()
  editingMember.value = null
  mutationError.value = null
}

async function submitAdd() {
  if (mutationBusy.value || !selectedCandidate.value) return
  mutationError.value = null
  mutationBusy.value = true
  try {
    const isValid = addFormRef.value
      ? await addFormRef.value.validate().catch(() => false)
      : false
    const candidate = selectedCandidate.value
    if (!isValid || !candidate) return

    await addProjectMember(props.projectId, {
      userId: candidate.userId,
      projectRole: addForm.projectRole
    })
    closeAddDialog()
    ElMessage.success('项目成员已添加')
    await loadMembers()
  } catch (error) {
    mutationError.value = projectErrorState(error, '添加项目成员失败')
  } finally { mutationBusy.value = false }
}

async function submitEdit() {
  if (mutationBusy.value || !editingMember.value) return
  mutationError.value = null
  mutationBusy.value = true
  try {
    const isValid = editFormRef.value
      ? await editFormRef.value.validate().catch(() => false)
      : false
    const member = editingMember.value
    if (!isValid || !member) return

    await updateProjectMember(props.projectId, member.userId, {
      projectRole: editForm.projectRole
    })
    closeEditDialog()
    ElMessage.success('成员信息已更新')
    await loadMembers()
  } catch (error) {
    mutationError.value = projectErrorState(error, '更新项目成员失败')
  } finally { mutationBusy.value = false }
}

async function removeMember(member) {
  try {
    await ElMessageBox.confirm(`确认将“${member.nickName || member.userName}”移出项目吗？`, '移除项目成员', {
      confirmButtonText: '确认移除', cancelButtonText: '取消', type: 'warning'
    })
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    throw reason
  }
  mutationBusy.value = true
  mutationError.value = null
  try {
    await removeProjectMember(props.projectId, member.userId)
    ElMessage.success('项目成员已移除')
    await loadMembers()
  } catch (error) {
    mutationError.value = projectErrorState(error, '移除项目成员失败')
  } finally { mutationBusy.value = false }
}

onMounted(loadMembers)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <el-card class="detail-panel member-panel" shadow="never">
    <template #header>
      <header class="detail-panel__heading">
        <div><p class="sg-eyebrow">MEMBERS</p><h2>项目成员</h2><span>项目角色独立于平台系统角色。</span></div>
        <el-button :icon="Refresh" circle aria-label="刷新成员" :loading="loading" @click="loadMembers" />
      </header>
    </template>

    <ProjectStatePanel v-if="errorState" compact :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadMembers" />
    <template v-else>
      <el-card v-if="canAdd" class="member-add" shadow="never">
        <strong><el-icon><Plus /></el-icon> 添加项目成员</strong>
        <MemberCandidateSelect :project-id="projectId" :exclude-ids="selectedIds" @select="chooseCandidate" />
      </el-card>
      <el-skeleton v-if="loading && !members.length" :rows="4" animated />
      <el-empty v-else-if="!members.length" :image-size="72" description="项目当前没有可展示的活动成员" />
      <el-table v-else class="member-table" :data="members" row-key="userId" v-loading="loading" empty-text="项目当前没有可展示的活动成员">
        <el-table-column label="成员" min-width="170" fixed="left">
          <template #default="{ row }"><strong>{{ row.nickName || row.userName }}</strong><small>{{ row.userName }}</small></template>
        </el-table-column>
        <el-table-column label="项目角色" min-width="130">
          <template #default="{ row }"><el-tag size="small" effect="plain" round :type="projectRoleMeta(row.projectRole).type">{{ projectRoleMeta(row.projectRole).label }}</el-tag></template>
        </el-table-column>
        <el-table-column label="部门" min-width="130"><template #default="{ row }">{{ row.deptName || '—' }}</template></el-table-column>
        <el-table-column label="加入时间" min-width="170"><template #default="{ row }">{{ formatDateTime(row.joinedTime) }}</template></el-table-column>
        <el-table-column v-if="canEdit || canRemove" label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEdit" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canRemove" text type="danger" :disabled="mutationBusy" @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="mutationError && !selectedCandidate && !editingMember" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
    </template>

    <ProjectModal v-if="selectedCandidate" title="添加项目成员" :busy="mutationBusy" @close="closeAddDialog">
      <el-form ref="addFormRef" :model="addForm" :rules="memberRules" class="member-form" size="large" label-position="top">
        <div class="member-identity"><strong>{{ selectedCandidate.nickName || selectedCandidate.userName }}</strong><span>{{ selectedCandidate.userName }} · {{ selectedCandidate.deptName || '未分配部门' }}</span></div>
        <el-form-item label="项目角色" prop="projectRole" required><el-select v-model="addForm.projectRole" class="sg-select"><el-option :label="projectRoleMeta('creator').label" value="creator" /><el-option :label="projectRoleMeta('director').label" value="director" /></el-select></el-form-item>
        <el-alert v-if="mutationError" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
        <footer><el-button :disabled="mutationBusy" @click="closeAddDialog">取消</el-button><el-button type="primary" :loading="mutationBusy" @click="submitAdd">添加</el-button></footer>
      </el-form>
    </ProjectModal>

    <ProjectModal v-if="editingMember" title="编辑项目成员" :busy="mutationBusy" @close="closeEditDialog">
      <el-form ref="editFormRef" :model="editForm" :rules="memberRules" class="member-form" size="large" label-position="top">
        <div class="member-identity"><strong>{{ editingMember.nickName || editingMember.userName }}</strong><span>{{ editingMember.userName }}</span></div>
        <el-form-item label="项目角色" prop="projectRole" required><el-select v-model="editForm.projectRole" class="sg-select"><el-option :label="projectRoleMeta('creator').label" value="creator" /><el-option :label="projectRoleMeta('director').label" value="director" /></el-select></el-form-item>
        <el-alert v-if="mutationError" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
        <footer><el-button :disabled="mutationBusy" @click="closeEditDialog">取消</el-button><el-button type="primary" :loading="mutationBusy" @click="submitEdit">保存</el-button></footer>
      </el-form>
    </ProjectModal>
  </el-card>
</template>

<style scoped>
.detail-panel { background: var(--sg-surface); border-color: var(--sg-border); border-radius: var(--sg-radius-lg); }
.detail-panel :deep(.el-card__header) { padding: 20px 24px; border-bottom-color: var(--sg-border); }
.detail-panel :deep(.el-card__body) { display: grid; gap: 16px; padding: 20px 24px 24px; }
.detail-panel__heading { display:flex; gap:16px; align-items:flex-start; justify-content:space-between; }
.detail-panel__heading h2, .detail-panel__heading span { margin:0; }
.detail-panel__heading h2 { font-size:19px; }
.detail-panel__heading span { display:block; margin-top:6px; color:var(--sg-text-muted); font-size:12px; }
.member-add { background:rgba(255,255,255,.025); border-color:var(--sg-border); border-radius:12px; }
.member-add :deep(.el-card__body) { display:grid; gap:11px; padding:14px; }
.member-add strong { display:flex; gap:7px; align-items:center; font-size:13px; }
.member-table { --el-table-text-color:var(--sg-text-secondary); --el-table-header-text-color:var(--sg-text-muted); --el-table-border-color:var(--sg-border); width:100%; }
.member-table strong,.member-table small { display:block; }
.member-table strong { color:var(--sg-text); font-size:13px; }
.member-table small { margin-top:3px; color:var(--sg-text-muted); }
.member-form { display:grid; gap:18px; }
.member-form :deep(.el-form-item) { margin-bottom:0; }
.member-form :deep(.el-select) { width:100%; }
.member-identity { padding:14px; background:var(--sg-accent-soft); border-radius:10px; }
.member-identity strong, .member-identity span { display:block; }
.member-identity span { margin-top:4px; color:var(--sg-text-muted); font-size:12px; }
footer { display:flex; gap:10px; justify-content:flex-end; }
</style>
