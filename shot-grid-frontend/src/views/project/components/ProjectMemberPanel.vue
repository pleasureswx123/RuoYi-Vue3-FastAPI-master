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
import { projectErrorState, formatDateTime } from '@/views/project/projectPresentation'
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
const addForm = reactive({ projectRole: 'creator', producerCode: '' })
const editForm = reactive({ projectRole: 'creator', producerCode: '' })
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
    const response = await getProjectMembers(props.projectId, { signal: requestController.signal })
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
  addForm.producerCode = ''
  mutationError.value = null
}

function openEdit(member) {
  editingMember.value = member
  editForm.projectRole = member.projectRole
  editForm.producerCode = member.producerCode || ''
  mutationError.value = null
}

function normalizeProducerCode(value) {
  const normalized = String(value || '').trim().toUpperCase()
  if (normalized && !/^[A-Z0-9]{2,12}$/.test(normalized)) {
    throw new Error('制作人缩写必须为 2—12 位英文字母或数字')
  }
  return normalized || null
}

async function submitAdd() {
  mutationError.value = null
  let producerCode
  try { producerCode = normalizeProducerCode(addForm.producerCode) } catch (error) {
    mutationError.value = { title: '请检查成员信息', message: error.message }; return
  }
  mutationBusy.value = true
  try {
    await addProjectMember(props.projectId, {
      userId: selectedCandidate.value.userId,
      projectRole: addForm.projectRole,
      producerCode
    })
    selectedCandidate.value = null
    ElMessage.success('项目成员已添加')
    await loadMembers()
  } catch (error) {
    mutationError.value = projectErrorState(error, '添加项目成员失败')
  } finally { mutationBusy.value = false }
}

async function submitEdit() {
  mutationError.value = null
  let producerCode
  try { producerCode = normalizeProducerCode(editForm.producerCode) } catch (error) {
    mutationError.value = { title: '请检查成员信息', message: error.message }; return
  }
  mutationBusy.value = true
  try {
    await updateProjectMember(props.projectId, editingMember.value.userId, {
      projectRole: editForm.projectRole,
      producerCode
    })
    editingMember.value = null
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
  <section class="detail-panel member-panel">
    <header class="detail-panel__heading">
      <div><p class="sg-eyebrow">MEMBERS</p><h2>项目成员</h2><span>项目角色独立于平台系统角色。</span></div>
      <el-button :icon="Refresh" circle aria-label="刷新成员" :loading="loading" @click="loadMembers" />
    </header>

    <ProjectStatePanel v-if="errorState" compact :title="errorState.title" :message="errorState.message" :retryable="errorState.retryable" @retry="loadMembers" />
    <template v-else>
      <div v-if="canAdd" class="member-add">
        <strong><el-icon><Plus /></el-icon> 添加项目成员</strong>
        <MemberCandidateSelect :project-id="projectId" :exclude-ids="selectedIds" @select="chooseCandidate" />
      </div>
      <p v-if="loading && !members.length" class="panel-muted">正在加载项目成员…</p>
      <p v-else-if="!members.length" class="panel-muted">项目当前没有可展示的活动成员。</p>
      <div v-else class="member-table-wrap">
        <table>
          <thead><tr><th>成员</th><th>项目角色</th><th>制作人缩写</th><th>部门</th><th>加入时间</th><th v-if="canEdit || canRemove">操作</th></tr></thead>
          <tbody>
            <tr v-for="member in members" :key="member.userId">
              <td><strong>{{ member.nickName || member.userName }}</strong><small>{{ member.userName }}</small></td>
              <td>{{ member.projectRole === 'director' ? '项目管理人员' : '制作人员' }}</td>
              <td><code>{{ member.producerCode || '—' }}</code></td>
              <td>{{ member.deptName || '—' }}</td>
              <td>{{ formatDateTime(member.joinedTime) }}</td>
              <td v-if="canEdit || canRemove" class="member-actions">
                <button v-if="canEdit" type="button" @click="openEdit(member)">编辑</button>
                <button v-if="canRemove" type="button" class="danger" :disabled="mutationBusy" @click="removeMember(member)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="mutationError && !selectedCandidate && !editingMember" class="inline-error" role="alert">
        <strong>{{ mutationError.title }}</strong><span>{{ mutationError.message }}</span>
      </div>
    </template>

    <ProjectModal v-if="selectedCandidate" title="添加项目成员" :busy="mutationBusy" @close="selectedCandidate = null">
      <form class="member-form" @submit.prevent="submitAdd">
        <div class="member-identity"><strong>{{ selectedCandidate.nickName || selectedCandidate.userName }}</strong><span>{{ selectedCandidate.userName }} · {{ selectedCandidate.deptName || '未分配部门' }}</span></div>
        <label><span>项目角色</span><el-select v-model="addForm.projectRole" class="sg-select"><el-option label="制作人员" value="creator" /><el-option label="项目管理人员" value="director" /></el-select></label>
        <label><span>制作人缩写</span><input v-model="addForm.producerCode" maxlength="12" placeholder="可空；承担任务前需补齐" @input="addForm.producerCode = addForm.producerCode.toUpperCase()" /></label>
        <div v-if="mutationError" class="inline-error" role="alert"><strong>{{ mutationError.title }}</strong><span>{{ mutationError.message }}</span></div>
        <footer><el-button :disabled="mutationBusy" @click="selectedCandidate = null">取消</el-button><el-button type="primary" native-type="submit" :loading="mutationBusy">添加</el-button></footer>
      </form>
    </ProjectModal>

    <ProjectModal v-if="editingMember" title="编辑项目成员" :busy="mutationBusy" @close="editingMember = null">
      <form class="member-form" @submit.prevent="submitEdit">
        <div class="member-identity"><strong>{{ editingMember.nickName || editingMember.userName }}</strong><span>{{ editingMember.userName }}</span></div>
        <label><span>项目角色</span><el-select v-model="editForm.projectRole" class="sg-select"><el-option label="制作人员" value="creator" /><el-option label="项目管理人员" value="director" /></el-select></label>
        <label><span>制作人缩写</span><input v-model="editForm.producerCode" maxlength="12" placeholder="显式留空将清除缩写" @input="editForm.producerCode = editForm.producerCode.toUpperCase()" /></label>
        <div v-if="mutationError" class="inline-error" role="alert"><strong>{{ mutationError.title }}</strong><span>{{ mutationError.message }}</span></div>
        <footer><el-button :disabled="mutationBusy" @click="editingMember = null">取消</el-button><el-button type="primary" native-type="submit" :loading="mutationBusy">保存</el-button></footer>
      </form>
    </ProjectModal>
  </section>
</template>

<style scoped>
.detail-panel { padding: 24px; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: var(--sg-radius-lg); }
.detail-panel__heading { display:flex; gap:16px; align-items:flex-start; justify-content:space-between; margin-bottom:20px; }
.detail-panel__heading h2, .detail-panel__heading span { margin:0; }
.detail-panel__heading h2 { font-size:19px; }
.detail-panel__heading span { display:block; margin-top:6px; color:var(--sg-text-muted); font-size:12px; }
.member-add { display:grid; gap:11px; margin-bottom:18px; padding:14px; background:rgba(255,255,255,.025); border:1px solid var(--sg-border); border-radius:12px; }
.member-add strong { display:flex; gap:7px; align-items:center; font-size:13px; }
.member-table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th, td { padding:13px 12px; text-align:left; border-bottom:1px solid var(--sg-border); white-space:nowrap; }
th { color:var(--sg-text-muted); font-size:10px; letter-spacing:.06em; text-transform:uppercase; }
td { color:var(--sg-text-secondary); font-size:12px; }
td strong, td small { display:block; }
td strong { color:var(--sg-text); font-size:13px; }
td small { margin-top:3px; color:var(--sg-text-muted); }
td code { color:var(--sg-accent); }
.member-actions button { padding:5px 7px; color:var(--sg-accent); cursor:pointer; background:transparent; border:0; }
.member-actions button.danger { color:var(--sg-danger); }
.panel-muted { padding:28px; color:var(--sg-text-muted); font-size:13px; text-align:center; }
.inline-error { display:grid; gap:5px; margin-top:14px; padding:12px 14px; color:#ffb4b4; font-size:12px; background:rgba(255,107,107,.08); border-radius:9px; }
.member-form, .member-form label { display:grid; gap:8px; }
.member-form { gap:18px; }
.member-form label span { font-size:13px; font-weight:600; }
.member-form input { height:42px; padding:0 12px; color:var(--sg-text); background:rgba(255,255,255,.035); border:1px solid var(--sg-border-strong); border-radius:10px; }
.member-identity { padding:14px; background:var(--sg-accent-soft); border-radius:10px; }
.member-identity strong, .member-identity span { display:block; }
.member-identity span { margin-top:4px; color:var(--sg-text-muted); font-size:12px; }
footer { display:flex; gap:10px; justify-content:flex-end; }
</style>
