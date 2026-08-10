<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { createProject, listProjects } from '@/api/shot-grid/projects'
import EmptyState from '@/components/EmptyState.vue'
import { useUserStore } from '@/store/modules/user'
import { createIdempotencyKey, domainErrorMessage, normalizeUserIds, PROJECT_STATUS, STORAGE_STATUS } from '@/utils/projectDomain'

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
const form = reactive({ projectName: '', projectCode: '', aspectRatio: '16:9', projectType: 'ai_short_film', projectDescription: '', storageRootId: null, projectDirectoryName: '', directorUserIdsText: '' })
const formError = ref('')
const pathPreview = computed(() => form.storageRootId && form.projectDirectoryName ? `NAS 根目录 #${form.storageRootId} / AI短片 / ${form.projectDirectoryName.trim()}` : '选择 NAS 根目录并填写目录名称后显示')
const rules = {
  projectName: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  projectCode: [{ required: true, pattern: /^[A-Z0-9]{2,12}$/, message: '请输入 2—12 位大写字母或数字', trigger: 'blur' }],
  storageRootId: [{ required: true, message: '请输入已配置的 NAS 根目录 ID', trigger: 'blur' }],
  projectDirectoryName: [{ required: true, message: '请输入项目目录名称', trigger: 'blur' }],
  directorUserIdsText: [{ validator: (_rule, value, callback) => normalizeUserIds(value).length ? callback() : callback(new Error('至少填写一名项目总监用户 ID')), trigger: 'blur' }]
}

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
function resetForm() { Object.assign(form, { projectName: '', projectCode: '', aspectRatio: '16:9', projectType: 'ai_short_film', projectDescription: '', storageRootId: null, projectDirectoryName: '', directorUserIdsText: '' }); formError.value = '' }
function openCreate() { resetForm(); dialogVisible.value = true }

async function submitCreate() {
  if (submitting.value || !(await formRef.value.validate().catch(() => false))) return
  submitting.value = true
  formError.value = ''
  try {
    const result = await createProject({
      projectName: form.projectName.trim(), projectCode: form.projectCode.trim().toUpperCase(), aspectRatio: form.aspectRatio,
      projectType: form.projectType, projectDescription: form.projectDescription.trim() || null,
      storageRootId: Number(form.storageRootId), projectDirectoryName: form.projectDirectoryName.trim(), directorUserIds: normalizeUserIds(form.directorUserIdsText), members: []
    }, createIdempotencyKey())
    dialogVisible.value = false
    await router.push({ name: 'ProjectOverview', params: { projectId: result.projectId } })
  } catch (error) { formError.value = domainErrorMessage(error) } finally { submitting.value = false }
}

onMounted(loadProjects)
onBeforeUnmount(() => { clearTimeout(searchTimer); controller?.abort() })
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
        <div class="form-grid"><el-form-item label="NAS 根目录 ID" prop="storageRootId"><el-input-number v-model="form.storageRootId" :min="1" controls-position="right" /></el-form-item><el-form-item label="项目目录名称" prop="projectDirectoryName"><el-input v-model="form.projectDirectoryName" maxlength="240" /></el-form-item></div>
        <div class="path-preview"><span>路径预览</span><code>{{ pathPreview }}</code><small>最终完整 UNC 路径由后端按已配置根目录生成并校验。</small></div>
        <el-form-item label="项目总监用户 ID" prop="directorUserIdsText"><el-input v-model="form.directorUserIdsText" placeholder="至少一名，多个 ID 用逗号分隔" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="submitting" :disabled="submitting" @click="submitCreate">{{ submitting ? '正在创建' : '创建项目' }}</el-button></template>
    </el-dialog>
  </section>
</template>
