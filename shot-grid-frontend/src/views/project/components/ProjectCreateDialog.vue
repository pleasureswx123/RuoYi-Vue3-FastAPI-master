<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import {
  createProject,
  getProjectRoleOptions,
  getStorageRootOptions,
  previewProjectPath
} from '@/api/shot-grid/projects'
import { createIdempotencyState } from '@/utils/idempotency'
import {
  normalizeProjectRoleOptions,
  projectErrorState,
  projectRoleMeta,
  projectRoleOptionLabel,
  REQUIRED_PROJECT_ROLES
} from '@/views/project/projectPresentation'
import MemberCandidateSelect from './MemberCandidateSelect.vue'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({ currentUser: { type: Object, required: true } })
const emit = defineEmits(['close', 'created'])
const idempotency = createIdempotencyState('project-create')
const createFormRef = ref(null)
const busy = ref(false)
const requestError = ref(null)
const storageRoots = ref([])
const storageLoading = ref(false)
const storageError = ref(null)
const roleOptions = ref([])
const roleOptionsLoading = ref(false)
const roleOptionsLoaded = ref(false)
const roleOptionsError = ref(null)
const pathPreview = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)
const form = reactive({
  projectCode: '',
  projectName: '',
  projectType: 'ai_short_film',
  projectDescription: '',
  aspectRatio: '16:9',
  storageRootId: '',
  remark: '',
  members: [{
    userId: Number(props.currentUser.userId),
    userName: props.currentUser.userName,
    nickName: props.currentUser.nickName,
    deptName: props.currentUser.dept?.deptName || null,
    projectRole: '',
    isCurrentUser: true
  }]
})
const createRules = {
  projectName: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim()
      if (!normalized) callback(new Error('项目名称不能为空'))
      else if (normalized.length > 200) callback(new Error('项目名称不能超过 200 个字符'))
      else callback()
    },
    trigger: 'change'
  }],
  projectCode: [{
    validator: (_rule, value, callback) => {
      const normalized = String(value || '').trim().toUpperCase()
      if (!/^[A-Z0-9]{2,12}$/.test(normalized)) callback(new Error('项目代号必须为 2—12 位大写英文字母或数字'))
      else callback()
    },
    trigger: 'change'
  }],
  projectType: [{ required: true, type: 'enum', enum: ['ai_short_film'], message: '请选择有效的项目类型', trigger: 'change' }],
  aspectRatio: [{ required: true, type: 'enum', enum: ['16:9', '21:9', '2.39:1', '9:16', '1:1'], message: '请选择有效的画幅', trigger: 'change' }],
  storageRootId: [{
    validator: (_rule, value, callback) => {
      const storageRootId = Number(value)
      if (!Number.isSafeInteger(storageRootId) || storageRootId <= 0) callback(new Error('请选择有效的 NAS 根目录'))
      else callback()
    },
    trigger: 'change'
  }],
  members: [{
    validator: (_rule, value, callback) => {
      if (!roleOptionsReady.value) {
        callback(new Error('项目角色配置未就绪'))
      } else if (!Array.isArray(value) || value.some(member => !isConfiguredProjectRole(member.projectRole))) {
        callback(new Error('项目成员包含未配置的项目角色'))
      } else if (!value.some(member => member.projectRole === 'director')) {
        callback(new Error('项目必须至少有一名项目管理人'))
      } else {
        callback()
      }
    },
    trigger: 'change'
  }],
  remark: [{ max: 500, message: '备注不能超过 500 个字符', trigger: 'change' }]
}
let storageController = null
let roleOptionsController = null
let previewController = null
let previewTimer = null
let storageGeneration = 0
let roleOptionsGeneration = 0
let previewGeneration = 0

const selectedUserIds = computed(() => form.members.map(item => item.userId))
const selectedStorageRoot = computed(() =>
  storageRoots.value.find(root => String(root.storageRootId) === String(form.storageRootId)) || null
)
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
  if (!roleOptionsLoaded.value || roleOptionsLoading.value || roleOptionsError.value || roleOptionsReady.value) return ''
  const labels = missingProjectRoles.value.map(role => projectRoleMeta(role).label).join('、')
  return `项目角色配置不完整：缺少“${labels}”角色，请联系管理员完成配置。`
})
const defaultCreatorRole = computed(() =>
  roleOptions.value.find(option => option.projectRole === 'creator')?.projectRole || ''
)
const canSubmit = computed(() =>
  !busy.value && roleOptionsReady.value && form.projectCode.trim() && form.projectName.trim() && form.storageRootId
)

function isConfiguredProjectRole(role) {
  return roleOptions.value.some(option => option.projectRole === role)
}

async function loadStorageRoots() {
  storageController?.abort()
  const generation = ++storageGeneration
  const requestController = new AbortController()
  storageController = requestController
  storageLoading.value = true
  storageError.value = null
  try {
    const response = await getStorageRootOptions({ signal: requestController.signal })
    if (generation !== storageGeneration) return
    storageRoots.value = Array.isArray(response.data) ? response.data : []
    if (storageRoots.value.length === 1 && !form.storageRootId) {
      form.storageRootId = String(storageRoots.value[0].storageRootId)
    }
  } catch (error) {
    if (generation === storageGeneration && error?.code !== 'ERR_CANCELED') {
      storageRoots.value = []
      storageError.value = projectErrorState(error, 'NAS 根目录选项加载失败')
    }
  } finally {
    if (generation === storageGeneration) storageLoading.value = false
  }
}

function applyRoleDefaults() {
  const configured = new Set(roleOptions.value.map(option => option.projectRole))
  const directorRole = roleOptions.value.find(option => option.projectRole === 'director')?.projectRole || ''
  const creatorRole = defaultCreatorRole.value
  form.members.forEach(member => {
    if (configured.has(member.projectRole)) return
    member.projectRole = member.isCurrentUser ? directorRole : creatorRole
  })
  createFormRef.value?.clearValidate('members')
}

async function loadRoleOptions() {
  roleOptionsController?.abort()
  const generation = ++roleOptionsGeneration
  const requestController = new AbortController()
  roleOptionsController = requestController
  roleOptionsLoading.value = true
  roleOptionsLoaded.value = false
  roleOptionsError.value = null
  roleOptions.value = []
  try {
    const response = await getProjectRoleOptions({ signal: requestController.signal })
    if (generation !== roleOptionsGeneration) return
    roleOptions.value = normalizeProjectRoleOptions(response.data)
    roleOptionsLoaded.value = true
    applyRoleDefaults()
  } catch (error) {
    if (generation === roleOptionsGeneration && error?.code !== 'ERR_CANCELED') {
      roleOptionsLoaded.value = true
      roleOptionsError.value = projectErrorState(error, '项目角色配置加载失败')
    }
  } finally {
    if (generation === roleOptionsGeneration) roleOptionsLoading.value = false
  }
}

function invalidatePathPreview() {
  previewGeneration += 1
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = null
  pathPreview.value = null
  previewError.value = null
  previewLoading.value = false
  previewController?.abort()
  return previewGeneration
}

async function loadPathPreview() {
  const generation = invalidatePathPreview()
  const storageRootId = Number(form.storageRootId)
  if (!storageRootId || !form.projectName.trim()) {
    return null
  }
  previewController = new AbortController()
  previewLoading.value = true
  try {
    const response = await previewProjectPath(
      storageRootId,
      {
        projectType: 'ai_short_film',
        projectName: form.projectName.trim()
      },
      { signal: previewController.signal }
    )
    if (generation !== previewGeneration) return null
    pathPreview.value = response.data
    if (response.data.pathConflict) {
      previewError.value = { title: '项目目录已被占用', message: '请修改项目名称，系统会自动重新校验。' }
    }
    return response.data
  } catch (error) {
    if (generation === previewGeneration && error?.code !== 'ERR_CANCELED') {
      previewError.value = projectErrorState(error, 'NAS 路径计算失败')
    }
    return null
  } finally {
    if (generation === previewGeneration) previewLoading.value = false
  }
}

function schedulePathPreview() {
  invalidatePathPreview()
  if (!form.storageRootId || !form.projectName.trim()) return
  previewTimer = setTimeout(loadPathPreview, 350)
}

function addMember(candidate) {
  if (!roleOptionsReady.value) return
  form.members.push({ ...candidate, projectRole: defaultCreatorRole.value })
  createFormRef.value?.validateField('members').catch(() => false)
}

function removeMember(index) {
  form.members.splice(index, 1)
  createFormRef.value?.validateField('members').catch(() => false)
}

function buildPayload() {
  const projectCode = form.projectCode.trim().toUpperCase()
  const projectName = form.projectName.trim()
  const storageRootId = Number(form.storageRootId)
  const normalizedMembers = form.members.map(member => ({
    userId: member.userId,
    projectRole: member.projectRole
  }))
  const directorUserIds = normalizedMembers
    .filter(member => member.projectRole === 'director')
    .map(member => member.userId)
  const initialMembers = normalizedMembers.filter(member => member.projectRole !== 'director')
  return {
    projectCode, projectName, projectType: 'ai_short_film',
    projectDescription: form.projectDescription.trim() || null, aspectRatio: form.aspectRatio,
    storageRootId,
    directorUserIds, members: initialMembers,
    remark: form.remark.trim() || null
  }
}

async function submit() {
  if (busy.value || !roleOptionsReady.value) return
  requestError.value = null
  busy.value = true
  try {
    const isValid = createFormRef.value
      ? await createFormRef.value.validate().catch(() => false)
      : false
    if (!isValid) return

    const payload = buildPayload()
    const preview = pathPreview.value || (await loadPathPreview())
    if (!preview || preview.pathConflict) return

    const response = await createProject(payload, idempotency.forPayload(payload))
    emit('created', response.data)
  } catch (error) {
    requestError.value = projectErrorState(error, '项目创建失败')
  } finally { busy.value = false }
}

function closeDialog() {
  storageGeneration += 1
  roleOptionsGeneration += 1
  storageController?.abort()
  roleOptionsController?.abort()
  invalidatePathPreview()
  createFormRef.value?.resetFields()
  requestError.value = null
  emit('close')
}

watch(
  () => [form.storageRootId, form.projectName],
  schedulePathPreview
)

onMounted(() => {
  loadStorageRoots()
  loadRoleOptions()
})
onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  storageGeneration += 1
  roleOptionsGeneration += 1
  storageController?.abort()
  roleOptionsController?.abort()
  previewController?.abort()
})
</script>

<template>
  <ProjectModal title="创建项目" description="项目名称同时作为 NAS 项目目录名称，系统自动计算并校验保存路径。" :busy="busy" wide @close="closeDialog">
    <el-form ref="createFormRef" :model="form" :rules="createRules" class="project-form" size="large" label-position="top">
      <div class="project-form__grid">
        <el-form-item label="项目名称" prop="projectName" required>
          <el-input v-model="form.projectName" maxlength="200" placeholder="如：罗刹夫人" />
        </el-form-item>
        <el-form-item label="项目代号" prop="projectCode" required>
          <el-input v-model="form.projectCode" maxlength="12" placeholder="如：LCFR" @input="value => form.projectCode = value.toUpperCase()" />
        </el-form-item>
        <el-form-item label="画幅" prop="aspectRatio" required>
          <el-select v-model="form.aspectRatio" class="sg-select"><el-option v-for="ratio in ['16:9','21:9','2.39:1','9:16','1:1']" :key="ratio" :label="ratio" :value="ratio" /></el-select>
        </el-form-item>
        <el-form-item label="项目类型" prop="projectType">
          <el-input model-value="AI 影视短片" disabled />
        </el-form-item>
        <el-form-item label="NAS 根目录" prop="storageRootId" required>
          <el-select v-model="form.storageRootId" class="sg-select" :placeholder="storageLoading ? '正在加载可用根目录…' : '请选择可用根目录'" :loading="storageLoading" :disabled="storageLoading || !!storageError">
            <el-option :label="storageLoading ? '正在加载可用根目录…' : '请选择可用根目录'" value="" />
            <el-option v-for="root in storageRoots" :key="root.storageRootId" :label="`${root.rootName}（${root.rootCode}）`" :value="String(root.storageRootId)" />
          </el-select>
          <small v-if="!storageError && !storageLoading && storageRoots.length === 0">当前没有可用的 NAS 根目录，请联系管理员。</small>
          <el-alert v-if="storageError" class="field-alert" :title="storageError.message" type="error" show-icon :closable="false"><el-button v-if="storageError.retryable" link type="danger" @click="loadStorageRoots">重试</el-button></el-alert>
        </el-form-item>
      </div>

      <el-card class="path-preview" shadow="never">
        <template #header><strong>项目保存路径</strong></template>
        <el-skeleton v-if="previewLoading" :rows="2" animated />
        <el-descriptions v-else :column="1" border>
          <el-descriptions-item label="NAS 根目录"><code v-if="selectedStorageRoot">{{ selectedStorageRoot.uncRootPath }}</code><span v-else>请选择 NAS 根目录</span></el-descriptions-item>
          <el-descriptions-item label="完整路径"><code v-if="pathPreview" :class="{ conflict: pathPreview.pathConflict }">{{ pathPreview.projectPathPreview }}</code><span v-else-if="selectedStorageRoot">填写项目名称后自动计算</span><span v-else>—</span></el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="previewError" :title="previewError.title" :description="previewError.message" type="error" show-icon :closable="false" />
      </el-card>

      <el-form-item prop="members" class="project-form__members">
        <el-card class="people-section" shadow="never">
          <template #header><div class="people-section__heading"><div><strong>项目成员</strong><p>当前账号默认加入项目；所有成员均可设置为项目管理人或制作人员，且至少需要一名项目管理人。</p></div></div></template>
          <el-alert v-if="roleOptionsLoading" title="正在加载项目角色配置…" type="info" show-icon :closable="false" />
          <el-alert v-else-if="roleOptionsError" :title="roleOptionsError.title" :description="roleOptionsError.message" type="error" show-icon :closable="false">
            <el-button v-if="roleOptionsError.retryable" link type="danger" @click="loadRoleOptions">重试</el-button>
          </el-alert>
          <el-alert v-else-if="roleConfigurationMessage" title="项目角色配置缺失" :description="roleConfigurationMessage" type="error" show-icon :closable="false">
            <el-button link type="danger" @click="loadRoleOptions">重新检查</el-button>
          </el-alert>
          <MemberCandidateSelect :department-id="currentUser.dept?.deptId" :exclude-ids="selectedUserIds" :disabled="!roleOptionsReady" @select="addMember" />
          <el-table class="member-rows" :data="form.members" row-key="userId" empty-text="尚未添加项目成员">
            <el-table-column label="成员" min-width="210"><template #default="{ row }"><strong>{{ row.nickName || row.userName }}</strong><small>{{ row.userName }} · {{ row.deptName || '未分配部门' }}<template v-if="row.isCurrentUser"> · 当前登录账号</template></small></template></el-table-column>
            <el-table-column label="项目角色" min-width="250"><template #default="{ row }"><el-select v-model="row.projectRole" class="sg-select" size="default" aria-label="项目角色" :loading="roleOptionsLoading" :disabled="!roleOptionsReady"><el-option v-for="option in roleOptions" :key="`${option.projectRole}:${option.systemRoleId}`" :label="projectRoleOptionLabel(option)" :value="option.projectRole" /></el-select></template></el-table-column>
            <el-table-column label="操作" width="90"><template #default="{ row, $index }"><el-button v-if="!row.isCurrentUser" link type="danger" @click="removeMember($index)">移除</el-button><el-tag v-else size="small" type="info" effect="plain">本人</el-tag></template></el-table-column>
          </el-table>
        </el-card>
      </el-form-item>

      <el-form-item label="项目描述" prop="projectDescription" class="project-form__full">
        <el-input v-model="form.projectDescription" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="备注" prop="remark" class="project-form__full">
        <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
      </el-form-item>

      <el-alert v-if="requestError" :title="requestError.title" :description="requestError.message" type="error" show-icon :closable="false" />
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">创建并初始化 NAS</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.project-form { display: grid; gap: 22px; }
.project-form__grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; }
.project-form :deep(.el-form-item) { margin-bottom: 0; }
.project-form :deep(.el-input),
.project-form :deep(.el-select) { width: 100%; }
.project-form :deep(.el-textarea__inner) { resize: vertical; }
.project-form__members :deep(.el-form-item__content) { display: block; }
.people-section strong, .path-preview strong { font-size: 13px; font-weight: 600; }
small, .people-section p, .path-preview p { margin: 0; color: var(--sg-text-muted); font-size: 11px; line-height: 1.55; }
.field-error { color: #ffb4b4; }
.path-preview, .people-section { background: rgba(255,255,255,.025); border-color: var(--sg-border); border-radius: 14px; }
.path-preview :deep(.el-card__header),.people-section :deep(.el-card__header){padding:14px 16px;border-bottom-color:var(--sg-border)}.path-preview :deep(.el-card__body),.people-section :deep(.el-card__body){display:grid;gap:13px;padding:16px}.path-preview code { color: var(--sg-text-secondary); font-family: Consolas, 'Courier New', monospace; white-space: normal; overflow-wrap: anywhere; }.path-preview code.conflict{color:var(--sg-danger)}
.people-section__heading { display: flex; justify-content: space-between; }
.member-rows { --el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);--el-table-border-color:var(--sg-border);width:100% }.member-rows strong,.member-rows small{display:block}.member-rows small{margin-top:3px;color:var(--sg-text-muted)}
footer { display: flex; gap: 10px; justify-content: flex-end; }
@media (max-width:700px) { .project-form__grid { grid-template-columns: 1fr; } }
</style>
