<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { createProject, listProjects } from '@/api/shot-grid/projects'
import { listProjectStorageRoots, previewProjectPath, searchProjectUsers } from '@/api/shot-grid/projectCreation'
import EmptyState from '@/components/EmptyState.vue'
import { useUserStore } from '@/store/modules/user'
import { createIdempotencyKey, domainErrorMessage, PROJECT_STATUS, STORAGE_STATUS } from '@/utils/projectDomain'
import { createLatestPreview, hasDirector, uniqueUserIds } from '@/utils/projectCreation'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const loadError = ref(null)
const forbidden = ref(false)
const projects = ref([])
const total = ref(0)
const submitting = ref(false)
const dialogVisible = ref(false)
const formRef = ref()
let searchTimer
let controller

const query = reactive({ pageNum: 1, pageSize: 10, keyword: '', projectStatus: '' })
const form = reactive({ projectName: '', projectCode: '', aspectRatio: '16:9', projectType: 'ai_short_film', projectDescription: '', storageRootId: null, projectDirectoryName: '', directorUserIds: [] })
const formError = ref('')
const storageRoots = ref([])
const rootsLoading = ref(false)
const rootsError = ref('')
const userOptions = ref([])
const usersLoading = ref(false)
const pathPreview = ref(null)
const previewLoading = ref(false)
const previewError = ref('')
const latestPreview = createLatestPreview(
  (value) => { pathPreview.value = value; previewError.value = ''; previewLoading.value = false },
  (error) => { pathPreview.value = null; previewError.value = domainErrorMessage(error, '路径预览失败'); previewLoading.value = false }
)
const rules = {
  projectName: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  projectCode: [{ required: true, pattern: /^[A-Z0-9]{2,12}$/, message: '请输入 2—12 位大写字母或数字', trigger: 'blur' }],
  storageRootId: [{ required: true, message: '请选择可用 NAS 根目录', trigger: 'change' }],
  projectDirectoryName: [{ required: true, message: '请输入项目目录名称', trigger: 'blur' }],
  directorUserIds: [{ validator: (_rule, value, callback) => hasDirector(value) ? callback() : callback(new Error('至少选择一名项目总监')), trigger: 'change' }]
}

async function loadStorageRoots() {
  rootsLoading.value = true; rootsError.value = ''
  try { storageRoots.value = await listProjectStorageRoots() || []; if (!storageRoots.value.length) rootsError.value = '当前没有可用且可写的 NAS 根目录' }
  catch (error) { rootsError.value = domainErrorMessage(error, 'NAS 根目录加载失败') }
  finally { rootsLoading.value = false }
}
async function loadUsers(keyword = '') {
  usersLoading.value = true
  try { userOptions.value = await searchProjectUsers(keyword) || [] }
  catch (error) { formError.value = domainErrorMessage(error, '用户候选加载失败，请确认项目创建权限') }
  finally { usersLoading.value = false }
}
function refreshPathPreview() {
  pathPreview.value = null; previewError.value = ''
  if (!form.storageRootId || !form.projectDirectoryName.trim()) { latestPreview.cancel(); previewLoading.value = false; return }
  previewLoading.value = true
  latestPreview.run((signal) => previewProjectPath({ storageRootId: form.storageRootId, projectType: form.projectType, projectDirectoryName: form.projectDirectoryName.trim() }, { signal }))
}
watch(() => [form.storageRootId, form.projectType, form.projectDirectoryName], refreshPathPreview)

async function loadProjects() {
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  loadError.value = null
  forbidden.value = false
  try {
    const result = await listProjects({ ...query, keyword: query.keyword || undefined, projectStatus: query.projectStatus || undefined }, { signal: controller.signal })
    projects.value = result?.rows || []
    total.value = result?.total || 0
  } catch (error) {
    if (error?.code === 'ERR_CANCELED') return
    forbidden.value = error?.status === 403
    loadError.value = domainErrorMessage(error, '项目列表加载失败，请重试。')
  } finally {
    loading.value = false
  }
}

function search() { clearTimeout(searchTimer); searchTimer = setTimeout(() => { query.pageNum = 1; loadProjects() }, 300) }
function resetForm() { Object.assign(form, { projectName: '', projectCode: '', aspectRatio: '16:9', projectType: 'ai_short_film', projectDescription: '', storageRootId: null, projectDirectoryName: '', directorUserIds: [] }); formError.value = ''; pathPreview.value = null }
function openCreate() { resetForm(); dialogVisible.value = true; loadStorageRoots(); loadUsers() }

async function submitCreate() {
  if (submitting.value || !(await formRef.value.validate().catch(() => false))) return
  submitting.value = true
  formError.value = ''
  try {
    const result = await createProject({
      projectName: form.projectName.trim(), projectCode: form.projectCode.trim().toUpperCase(), aspectRatio: form.aspectRatio,
      projectType: form.projectType, projectDescription: form.projectDescription.trim() || null,
      storageRootId: Number(form.storageRootId), projectDirectoryName: form.projectDirectoryName.trim(), directorUserIds: uniqueUserIds(form.directorUserIds), members: []
    }, createIdempotencyKey())
    dialogVisible.value = false
    await router.push({ name: 'ProjectOverview', params: { projectId: result.projectId } })
  } catch (error) { formError.value = domainErrorMessage(error) } finally { submitting.value = false }
}

onMounted(loadProjects)
onBeforeUnmount(() => { clearTimeout(searchTimer); controller?.abort(); latestPreview.cancel() })
</script>

<template>
  <section class="page project-list-page">
    <header class="page-heading"><div><span class="eyebrow">PROJECTS</span><h1>项目</h1><p class="lead">只显示你有权访问的影视制作项目。</p></div><el-button v-if="userStore.hasPermission('shotgrid:project:add')" type="primary" size="large" @click="openCreate">创建项目</el-button></header>
    <div class="toolbar">
      <el-input v-model="query.keyword" clearable placeholder="搜索项目名称或代号" :prefix-icon="Search" @input="search" @clear="search" />
      <el-select v-model="query.projectStatus" placeholder="全部状态" clearable @change="query.pageNum = 1; loadProjects()"><el-option v-for="(value, key) in PROJECT_STATUS" :key="key" :label="value.label" :value="key" /></el-select>
    </div>
    <div v-if="forbidden" class="state-panel"><strong>无权查看项目</strong><p>当前账号缺少项目列表权限，请联系管理员。</p></div>
    <div v-else-if="loadError" class="state-panel state-panel--error"><strong>加载失败</strong><p>{{ loadError }}</p><el-button @click="loadProjects">重试</el-button></div>
    <div v-else v-loading="loading" class="project-results">
      <EmptyState v-if="!loading && !projects.length" title="暂无项目" description="尝试调整搜索条件，或创建第一个项目。" />
      <div v-else class="project-grid">
        <article v-for="project in projects" :key="project.projectId" class="project-card" tabindex="0" @click="router.push(`/projects/${project.projectId}/overview`)" @keydown.enter="router.push(`/projects/${project.projectId}/overview`)">
          <div class="project-card__top"><span class="project-code">{{ project.projectCode }}</span><el-tag :type="PROJECT_STATUS[project.projectStatus]?.type">{{ PROJECT_STATUS[project.projectStatus]?.label || project.projectStatus }}</el-tag></div>
          <h2>{{ project.projectName }}</h2><p>{{ project.aspectRatio }} · {{ project.projectTypeName }}</p>
          <div class="project-card__stats"><span><b>{{ project.totalShots }}</b> 镜头</span><span><b>{{ project.totalAssets }}</b> 资产</span><span><b>{{ project.overallProgress }}%</b> 进度</span></div>
          <div class="storage-line"><i :class="`is-${project.storageStatus}`" />{{ STORAGE_STATUS[project.storageStatus]?.label || project.storageStatus }}</div>
        </article>
      </div>
      <el-pagination v-if="total" v-model:current-page="query.pageNum" v-model:page-size="query.pageSize" layout="total, sizes, prev, pager, next" :total="total" @current-change="loadProjects" @size-change="query.pageNum = 1; loadProjects()" />
    </div>

    <el-dialog v-model="dialogVisible" title="创建项目" width="min(680px, 92vw)" destroy-on-close>
      <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="project-form">
        <div class="form-grid"><el-form-item label="项目名称" prop="projectName"><el-input v-model="form.projectName" maxlength="200" /></el-form-item><el-form-item label="唯一项目代号" prop="projectCode"><el-input v-model="form.projectCode" maxlength="12" placeholder="如 SG01" @input="form.projectCode = form.projectCode.toUpperCase().replace(/[^A-Z0-9]/g, '')" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="画幅" prop="aspectRatio"><el-select v-model="form.aspectRatio"><el-option v-for="item in ['16:9','21:9','2.39:1','9:16','1:1']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="项目类型" prop="projectType"><el-select v-model="form.projectType"><el-option label="AI 短片" value="ai_short_film" /></el-select></el-form-item></div>
        <el-form-item label="项目描述" prop="projectDescription"><el-input v-model="form.projectDescription" type="textarea" :rows="3" /></el-form-item>
        <div class="form-grid"><el-form-item label="NAS 根目录" prop="storageRootId"><el-select v-model="form.storageRootId" :loading="rootsLoading" :disabled="!storageRoots.length" placeholder="请选择可用根目录"><el-option v-for="root in storageRoots" :key="root.storageRootId" :label="root.rootName" :value="root.storageRootId"><span>{{ root.rootName }}</span><small> · 当前可用</small></el-option></el-select><small v-if="rootsError" class="field-error">{{ rootsError }}</small></el-form-item><el-form-item label="项目目录名称" prop="projectDirectoryName"><el-input v-model="form.projectDirectoryName" maxlength="240" /></el-form-item></div>
        <div class="path-preview" v-loading="previewLoading"><span>后端路径预览</span><template v-if="pathPreview"><strong>{{ pathPreview.rootName }} · 当前可用</strong><code>{{ pathPreview.finalPath }}</code></template><small v-else-if="previewError" class="field-error">{{ previewError }}</small><small v-else>选择根目录并填写目录名称后，由后端计算并校验冲突。</small></div>
        <el-form-item label="项目总监" prop="directorUserIds"><el-select v-model="form.directorUserIds" multiple filterable remote :remote-method="loadUsers" :loading="usersLoading" placeholder="搜索并选择至少一名有效用户"><el-option v-for="user in userOptions" :key="user.userId" :label="`${user.nickName} (${user.userName})`" :value="user.userId"><span>{{ user.nickName }} ({{ user.userName }})</span><small v-if="user.deptName"> · {{ user.deptName }}</small></el-option></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="submitting" :disabled="submitting || !pathPreview || !storageRoots.length" @click="submitCreate">{{ submitting ? '正在创建' : '创建项目' }}</el-button></template>
    </el-dialog>
  </section>
</template>
