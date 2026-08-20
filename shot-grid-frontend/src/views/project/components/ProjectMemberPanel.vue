<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'

import {
  addProjectMember,
  getProjectMemberRoleOptions,
  getProjectMembers,
  removeProjectMember,
  updateProjectMember
} from '@/api/shot-grid/projects'
import {
  formatDateTime,
  normalizeProjectRoleOptions,
  projectErrorState,
  projectRoleMeta,
  projectRoleOptionLabel,
  REQUIRED_PROJECT_ROLES
} from '@/views/project/projectPresentation'
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
const roleOptions = ref([])
const roleOptionsLoading = ref(false)
const roleOptionsLoaded = ref(false)
const roleOptionsError = ref(null)
const selectedCandidate = ref(null)
const editingMember = ref(null)
const addFormRef = ref(null)
const editFormRef = ref(null)
const addForm = reactive({ projectRole: '' })
const editForm = reactive({ projectRole: '' })
const memberRules = {
  projectRole: [{
    validator: (_rule, value, callback) => {
      if (!roleOptionsReady.value) callback(new Error('项目角色配置未就绪'))
      else if (!isConfiguredProjectRole(value)) callback(new Error('请选择有效的项目角色'))
      else callback()
    },
    trigger: 'change'
  }]
}
let membersController = null
let roleOptionsController = null
let membersGeneration = 0
let roleOptionsGeneration = 0
let addDialogGeneration = 0
let editDialogGeneration = 0

const wildcard = computed(() => props.permissions.includes('*:*:*'))
const canAdd = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:add')))
const canEdit = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:edit')))
const canRemove = computed(() => props.canManage && (wildcard.value || props.permissions.includes('shotgrid:member:remove')))
const requiresRoleOptions = computed(() => canAdd.value || canEdit.value)
const selectedIds = computed(() => members.value.map(member => member.userId))
const missingProjectRoles = computed(() => {
  const configured = new Set(roleOptions.value.map(option => option.projectRole))
  return REQUIRED_PROJECT_ROLES.filter(role => !configured.has(role))
})
const roleOptionsReady = computed(() =>
  roleOptionsLoaded.value &&
  !roleOptionsLoading.value &&
  !roleOptionsError.value &&
  missingProjectRoles.value.length === 0
)
const roleConfigurationMessage = computed(() => {
  if (!requiresRoleOptions.value || !roleOptionsLoaded.value || roleOptionsLoading.value || roleOptionsError.value || roleOptionsReady.value) return ''
  const labels = missingProjectRoles.value.map(role => projectRoleMeta(role).label).join('、')
  return `项目角色配置不完整：缺少“${labels}”角色，请联系管理员完成配置。`
})
const defaultCreatorRole = computed(() =>
  roleOptions.value.find(option => option.projectRole === 'creator')?.projectRole || ''
)

function isConfiguredProjectRole(role) {
  return roleOptions.value.some(option => option.projectRole === role)
}

async function loadMembers() {
  membersController?.abort()
  const generation = ++membersGeneration
  const requestController = new AbortController()
  membersController = requestController
  loading.value = true
  errorState.value = null
  try {
    const response = await getProjectMembers(props.projectId, {}, { signal: requestController.signal })
    if (generation !== membersGeneration) return
    members.value = Array.isArray(response.rows) ? response.rows : []
  } catch (error) {
    if (generation === membersGeneration && error?.code !== 'ERR_CANCELED') {
      errorState.value = projectErrorState(error, '项目成员加载失败')
    }
  } finally {
    if (generation === membersGeneration) loading.value = false
  }
}

function resetRoleForms() {
  const defaultRole = defaultCreatorRole.value
  if (selectedCandidate.value) addForm.projectRole = defaultRole
  if (editingMember.value && !isConfiguredProjectRole(editForm.projectRole)) {
    editForm.projectRole = editingMember.value.projectRole
  }
  addFormRef.value?.clearValidate()
  editFormRef.value?.clearValidate()
}

async function loadRoleOptions() {
  if (!requiresRoleOptions.value) return
  roleOptionsController?.abort()
  const generation = ++roleOptionsGeneration
  const requestController = new AbortController()
  roleOptionsController = requestController
  roleOptionsLoading.value = true
  roleOptionsLoaded.value = false
  roleOptionsError.value = null
  roleOptions.value = []
  try {
    const response = await getProjectMemberRoleOptions(props.projectId, { signal: requestController.signal })
    if (generation !== roleOptionsGeneration) return
    roleOptions.value = normalizeProjectRoleOptions(response.data)
    roleOptionsLoaded.value = true
    resetRoleForms()
  } catch (error) {
    if (generation === roleOptionsGeneration && error?.code !== 'ERR_CANCELED') {
      roleOptionsLoaded.value = true
      roleOptionsError.value = projectErrorState(error, '项目角色配置加载失败')
    }
  } finally {
    if (generation === roleOptionsGeneration) roleOptionsLoading.value = false
  }
}

function refreshPanel() {
  loadMembers()
  if (requiresRoleOptions.value) loadRoleOptions()
}

function chooseCandidate(candidate) {
  if (!roleOptionsReady.value) return
  addDialogGeneration += 1
  selectedCandidate.value = candidate
  addForm.projectRole = defaultCreatorRole.value
  mutationError.value = null
}

function openEdit(member) {
  editDialogGeneration += 1
  editingMember.value = member
  editForm.projectRole = member.projectRole
  mutationError.value = null
}

function closeAddDialog() {
  addDialogGeneration += 1
  addFormRef.value?.resetFields()
  addForm.projectRole = defaultCreatorRole.value
  selectedCandidate.value = null
  mutationError.value = null
}

function closeEditDialog() {
  editDialogGeneration += 1
  editFormRef.value?.resetFields()
  editForm.projectRole = defaultCreatorRole.value
  editingMember.value = null
  mutationError.value = null
}

async function submitAdd() {
  if (mutationBusy.value || !selectedCandidate.value || !roleOptionsReady.value) return
  const generation = addDialogGeneration
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
    if (generation !== addDialogGeneration) return
    closeAddDialog()
    ElMessage.success('项目成员已添加')
    await loadMembers()
  } catch (error) {
    mutationError.value = projectErrorState(error, '添加项目成员失败')
  } finally { mutationBusy.value = false }
}

async function submitEdit() {
  if (mutationBusy.value || !editingMember.value || !roleOptionsReady.value) return
  const generation = editDialogGeneration
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
    if (generation !== editDialogGeneration) return
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

watch(
  () => props.projectId,
  () => {
    membersGeneration += 1
    roleOptionsGeneration += 1
    membersController?.abort()
    roleOptionsController?.abort()
    closeAddDialog()
    closeEditDialog()
    members.value = []
    roleOptions.value = []
    roleOptionsLoaded.value = false
    refreshPanel()
  }
)

watch(requiresRoleOptions, required => {
  if (required && !roleOptionsLoaded.value && !roleOptionsLoading.value) loadRoleOptions()
})

onMounted(refreshPanel)
onBeforeUnmount(() => {
  membersGeneration += 1
  roleOptionsGeneration += 1
  addDialogGeneration += 1
  editDialogGeneration += 1
  membersController?.abort()
  roleOptionsController?.abort()
})
</script>

<template>
  <el-card class="detail-panel member-panel" shadow="never">
    <template #header>
      <header class="detail-panel__heading">
        <div><p class="sg-eyebrow">MEMBERS</p><h2>项目成员</h2><span>项目角色决定成员在当前项目中的访问与操作权限。</span></div>
        <el-button :icon="Refresh" circle aria-label="刷新成员和角色配置" :loading="loading || roleOptionsLoading" @click="refreshPanel" />
      </header>
    </template>

    <el-alert v-if="requiresRoleOptions && roleOptionsError" :title="roleOptionsError.title" :description="roleOptionsError.message" type="error" show-icon :closable="false">
      <el-button v-if="roleOptionsError.retryable" link type="danger" @click="loadRoleOptions">重试角色配置</el-button>
    </el-alert>
    <el-alert v-else-if="roleConfigurationMessage" title="项目角色配置缺失" :description="roleConfigurationMessage" type="error" show-icon :closable="false">
      <el-button link type="danger" @click="loadRoleOptions">重新检查</el-button>
    </el-alert>
    <ProjectStatePanel v-if="errorState" compact :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadMembers" />
    <template v-else>
      <el-card v-if="canAdd" class="member-add" shadow="never">
        <strong><el-icon><Plus /></el-icon> 添加项目成员</strong>
        <MemberCandidateSelect :project-id="projectId" :exclude-ids="selectedIds" :disabled="!roleOptionsReady" :placeholder="roleOptionsLoading ? '正在加载项目角色配置…' : '按账号或姓名搜索平台用户'" @select="chooseCandidate" />
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
            <div class="member-actions">
              <el-button v-if="canEdit" text type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="canRemove" text type="danger" :disabled="mutationBusy" @click="removeMember(row)">移除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="mutationError && !selectedCandidate && !editingMember" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
    </template>

    <ProjectModal v-if="selectedCandidate" title="添加项目成员" :busy="mutationBusy" @close="closeAddDialog">
      <el-form ref="addFormRef" :model="addForm" :rules="memberRules" class="member-form" size="large" label-position="top">
        <div class="member-identity"><strong>{{ selectedCandidate.nickName || selectedCandidate.userName }}</strong><span>{{ selectedCandidate.userName }} · {{ selectedCandidate.deptName || '未分配部门' }}</span></div>
        <el-form-item label="项目角色" prop="projectRole" required><el-select v-model="addForm.projectRole" class="sg-select" :loading="roleOptionsLoading" :disabled="!roleOptionsReady"><el-option v-for="option in roleOptions" :key="`${option.projectRole}:${option.systemRoleId}`" :label="projectRoleOptionLabel(option)" :value="option.projectRole" /></el-select></el-form-item>
        <el-alert v-if="roleOptionsLoading" title="正在加载项目角色配置…" type="info" show-icon :closable="false" />
        <el-alert v-else-if="roleOptionsError" :title="roleOptionsError.title" :description="roleOptionsError.message" type="error" show-icon :closable="false"><el-button v-if="roleOptionsError.retryable" link type="danger" @click="loadRoleOptions">重试</el-button></el-alert>
        <el-alert v-else-if="roleConfigurationMessage" title="项目角色配置缺失" :description="roleConfigurationMessage" type="error" show-icon :closable="false"><el-button link type="danger" @click="loadRoleOptions">重新检查</el-button></el-alert>
        <el-alert v-if="mutationError" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
        <footer><el-button :disabled="mutationBusy" @click="closeAddDialog">取消</el-button><el-button type="primary" :loading="mutationBusy" :disabled="!roleOptionsReady" @click="submitAdd">添加</el-button></footer>
      </el-form>
    </ProjectModal>

    <ProjectModal v-if="editingMember" title="编辑项目成员" :busy="mutationBusy" @close="closeEditDialog">
      <el-form ref="editFormRef" :model="editForm" :rules="memberRules" class="member-form" size="large" label-position="top">
        <div class="member-identity"><strong>{{ editingMember.nickName || editingMember.userName }}</strong><span>{{ editingMember.userName }}</span></div>
        <el-form-item label="项目角色" prop="projectRole" required><el-select v-model="editForm.projectRole" class="sg-select" :loading="roleOptionsLoading" :disabled="!roleOptionsReady"><el-option v-for="option in roleOptions" :key="`${option.projectRole}:${option.systemRoleId}`" :label="projectRoleOptionLabel(option)" :value="option.projectRole" /></el-select></el-form-item>
        <el-alert v-if="roleOptionsLoading" title="正在加载项目角色配置…" type="info" show-icon :closable="false" />
        <el-alert v-else-if="roleOptionsError" :title="roleOptionsError.title" :description="roleOptionsError.message" type="error" show-icon :closable="false"><el-button v-if="roleOptionsError.retryable" link type="danger" @click="loadRoleOptions">重试</el-button></el-alert>
        <el-alert v-else-if="roleConfigurationMessage" title="项目角色配置缺失" :description="roleConfigurationMessage" type="error" show-icon :closable="false"><el-button link type="danger" @click="loadRoleOptions">重新检查</el-button></el-alert>
        <el-alert v-if="mutationError" :title="mutationError.title" :description="mutationError.message" type="error" show-icon :closable="false" />
        <footer><el-button :disabled="mutationBusy" @click="closeEditDialog">取消</el-button><el-button type="primary" :loading="mutationBusy" :disabled="!roleOptionsReady" @click="submitEdit">保存</el-button></footer>
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
.member-actions { display:flex; gap:4px; align-items:center; }
.member-form { display:grid; gap:18px; }
.member-form :deep(.el-form-item) { margin-bottom:0; }
.member-form :deep(.el-select) { width:100%; }
.member-identity { padding:14px; background:var(--sg-accent-soft); border-radius:10px; }
.member-identity strong, .member-identity span { display:block; }
.member-identity span { margin-top:4px; color:var(--sg-text-muted); font-size:12px; }
footer { display:flex; gap:10px; justify-content:flex-end; }
</style>
