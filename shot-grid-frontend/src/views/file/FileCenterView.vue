<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { CopyDocument, Download, Files, FolderOpened, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { getProjectFilePage } from '@/api/shot-grid/files'
import { getProjectPage } from '@/api/shot-grid/projects'
import { downloadProtectedVersionFile } from '@/api/shot-grid/versions'
import { useSessionStore } from '@/store/modules/session'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProjectStoragePanel from '@/views/project/components/ProjectStoragePanel.vue'
import {
  fileErrorState,
  fileRoleLabel,
  fileVersionStatusMeta,
  formatFileDateTime,
  formatFileSize
} from './filePresentation'

const sessionStore = useSessionStore()
const projects = ref([])
const selectedProjectId = ref('')
const files = ref([])
const total = ref(0)
const projectsLoading = ref(false)
const filesLoading = ref(false)
const projectsError = ref(null)
const filesError = ref(null)
const downloadingFileId = ref('')
const filters = reactive({ keyword: '', fileRole: '', taskKind: '', versionStatus: '', pageNum: 1, pageSize: 20 })
let projectsController = null
let filesController = null
let downloadController = null

const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canViewAll = computed(() => hasPermission('shotgrid:project:all'))
const canUseFileCenter = computed(() => hasPermission('shotgrid:storage:path'))
const canDownload = computed(() => hasPermission('shotgrid:file:download'))
const canRetry = computed(() => hasPermission('shotgrid:storage:retry'))
const selectedProject = computed(() => projects.value.find(item => String(item.projectId) === selectedProjectId.value) || null)
const canDiagnose = computed(() => wildcard.value || canViewAll.value || selectedProject.value?.myProjectRole === 'director')
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / filters.pageSize)))

async function loadProjects() {
  projectsController?.abort()
  const controller = new AbortController()
  projectsController = controller
  projectsLoading.value = true
  projectsError.value = null
  try {
    const response = await getProjectPage({
      pageNum: 1,
      pageSize: 100,
      scope: canViewAll.value ? 'all' : undefined,
      orderByColumn: 'createTime',
      isAsc: 'descending'
    }, { signal: controller.signal })
    if (projectsController !== controller) return
    projects.value = response.rows || []
    if (!projects.value.some(item => String(item.projectId) === selectedProjectId.value)) {
      selectedProjectId.value = projects.value[0] ? String(projects.value[0].projectId) : ''
    }
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') projectsError.value = fileErrorState(error, '项目范围加载失败')
  } finally {
    if (projectsController === controller) projectsLoading.value = false
  }
}

async function loadFiles() {
  filesController?.abort()
  if (!selectedProjectId.value || !canUseFileCenter.value) {
    files.value = []
    total.value = 0
    if (!canUseFileCenter.value) filesError.value = fileErrorState({ httpStatus: 403, message: '当前账号没有文件与 NAS 访问权限' })
    return
  }
  const controller = new AbortController()
  filesController = controller
  filesLoading.value = true
  filesError.value = null
  try {
    const response = await getProjectFilePage(selectedProjectId.value, {
      keyword: filters.keyword.trim() || undefined,
      fileRole: filters.fileRole || undefined,
      taskKind: filters.taskKind || undefined,
      versionStatus: filters.versionStatus || undefined,
      pageNum: filters.pageNum,
      pageSize: filters.pageSize,
      orderByColumn: 'submittedTime',
      isAsc: 'descending'
    }, { signal: controller.signal })
    if (filesController !== controller) return
    files.value = response.rows || []
    total.value = Number(response.total || 0)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') filesError.value = fileErrorState(error)
  } finally {
    if (filesController === controller) filesLoading.value = false
  }
}

function submitFilters() {
  filters.pageNum = 1
  loadFiles()
}

function changePage(nextPage) {
  if (nextPage < 1 || nextPage > pageCount.value || nextPage === filters.pageNum) return
  filters.pageNum = nextPage
  loadFiles()
}

async function refreshAll() {
  const previousProjectId = selectedProjectId.value
  await loadProjects()
  if (selectedProjectId.value === previousProjectId) await loadFiles()
}

async function copyRelativePath(file) {
  if (!file.nasRelativePath) return
  try {
    await navigator.clipboard.writeText(file.nasRelativePath)
    ElMessage.success('NAS 相对路径已复制')
  } catch {
    ElMessage.error('浏览器未允许复制，请手动选择路径文本')
  }
}

function safeDownloadName(value) {
  const normalized = Array.from(String(value || 'version-file'))
    .map(character => character.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(character) ? '_' : character)
    .join('')
    .trim()
  return normalized || 'version-file'
}

async function downloadFile(file) {
  if (!canDownload.value || downloadingFileId.value) return
  downloadController?.abort()
  const controller = new AbortController()
  downloadController = controller
  downloadingFileId.value = file.fileId
  let objectUrl = null
  try {
    const blob = await downloadProtectedVersionFile(file.versionId, file.fileId, { signal: controller.signal })
    if (downloadController !== controller || controller.signal.aborted) return
    objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = safeDownloadName(file.businessFileName || file.originalName)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') ElMessage.error(fileErrorState(error, '文件下载失败').message)
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    if (downloadController === controller) {
      downloadController = null
      downloadingFileId.value = ''
    }
  }
}

watch(selectedProjectId, () => {
  filters.pageNum = 1
  files.value = []
  loadFiles()
})
onMounted(loadProjects)
onBeforeUnmount(() => {
  projectsController?.abort()
  filesController?.abort()
  downloadController?.abort()
})
</script>

<template>
  <section class="sg-page file-center-page">
    <header class="sg-page-heading">
      <div><p class="sg-eyebrow">FILES & NAS</p><h2 class="sg-page-title">文件与 NAS</h2><p class="sg-page-description">追溯正式版本文件、鉴权下载，并查看项目存储绑定与目录操作状态。</p></div>
      <el-button :icon="Refresh" :loading="projectsLoading || filesLoading" @click="refreshAll">刷新</el-button>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <section class="file-toolbar">
        <label class="project-select"><span>当前项目</span><el-select v-model="selectedProjectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :disabled="projectsLoading"><el-option v-for="project in projects" :key="project.projectId" :label="`${project.projectCode} · ${project.projectName}`" :value="String(project.projectId)" /></el-select></label>
        <form class="file-search" @submit.prevent="submitFilters"><label><span>文件搜索</span><div><input v-model="filters.keyword" maxlength="200" placeholder="业务文件名、原文件名或任务名" /><el-button native-type="submit" :icon="Search">搜索</el-button></div></label></form>
      </section>

      <section v-if="selectedProjectId" class="file-panel">
        <header><div><p class="sg-eyebrow">BUSINESS FILES</p><h3>正式版本文件</h3></div><span>{{ total }} 个文件</span></header>
        <div class="file-filters">
          <el-select v-model="filters.fileRole" class="sg-select" placeholder="全部用途" @change="submitFilters"><el-option label="全部用途" value="" /><el-option label="审核文件" value="review_media" /><el-option label="缩略图" value="thumbnail" /><el-option label="代理文件" value="proxy_media" /><el-option label="原始生成文件" value="source_original" /><el-option label="修复后文件" value="source_repaired" /><el-option label="首帧" value="first_frame" /><el-option label="尾帧" value="last_frame" /><el-option label="参考文件" value="reference" /></el-select>
          <el-select v-model="filters.taskKind" class="sg-select" placeholder="全部对象" @change="submitFilters"><el-option label="全部对象" value="" /><el-option label="镜头视频" value="shot_video" /><el-option label="资产图片" value="asset_image" /></el-select>
          <el-select v-model="filters.versionStatus" class="sg-select" placeholder="全部版本状态" @change="submitFilters"><el-option label="全部版本状态" value="" /><el-option label="待审核" value="pending_review" /><el-option label="已退回" value="rejected" /><el-option label="最终版本" value="final" /></el-select>
        </div>

        <ProjectStatePanel v-if="filesError" compact :title="filesError.title" :message="filesError.message" :retryable="filesError.retryable" @retry="loadFiles" />
        <div v-else-if="filesLoading && !files.length" class="file-empty" role="status">正在加载业务文件…</div>
        <div v-else-if="files.length" class="file-list" :class="{ 'is-refreshing': filesLoading }">
          <article v-for="file in files" :key="`${file.versionId}:${file.fileId}:${file.role}`">
            <span class="file-icon"><el-icon><Files /></el-icon></span>
            <div class="file-main"><header><strong>{{ file.businessFileName }}</strong><span class="file-state" :data-tone="fileVersionStatusMeta(file.versionStatus).tone">{{ fileVersionStatusMeta(file.versionStatus).label }}</span><span v-if="file.isPrimary" class="primary-chip">主文件</span></header><p>{{ file.taskName }} · {{ file.versionNumber }} · {{ fileRoleLabel(file.role) }}</p><small>{{ file.originalName }} · {{ formatFileSize(file.fileSize) }} · 提交于 {{ formatFileDateTime(file.submittedTime) }}</small><code v-if="file.nasRelativePath">{{ file.nasRelativePath }}</code></div>
            <div class="file-actions"><el-button v-if="file.nasRelativePath" text :icon="CopyDocument" @click="copyRelativePath(file)">复制路径</el-button><el-button v-if="canDownload" type="primary" plain :icon="Download" :loading="downloadingFileId === file.fileId" :disabled="Boolean(downloadingFileId)" @click="downloadFile(file)">下载</el-button></div>
          </article>
        </div>
        <div v-else class="file-empty"><el-icon><FolderOpened /></el-icon><strong>当前筛选没有正式版本文件</strong><span>只有版本发布并提交成功后，文件才会出现在这里。</span></div>
        <nav v-if="pageCount > 1" class="file-pagination"><el-button :disabled="filters.pageNum <= 1" @click="changePage(filters.pageNum - 1)">上一页</el-button><span>{{ filters.pageNum }} / {{ pageCount }}</span><el-button :disabled="filters.pageNum >= pageCount" @click="changePage(filters.pageNum + 1)">下一页</el-button></nav>
      </section>

      <ProjectStoragePanel
        v-if="selectedProject"
        :key="selectedProject.projectId"
        :project-id="selectedProject.projectId"
        :can-diagnose="canDiagnose"
        :can-retry-project="canDiagnose && canRetry"
        :can-retry-operation="canDiagnose && canRetry"
      />
      <div v-else class="file-empty"><el-icon><FolderOpened /></el-icon><strong>当前范围暂无项目</strong><span>请先创建或加入项目。</span></div>
    </template>
  </section>
</template>

<style scoped>
.file-center-page{display:grid;gap:18px}.file-toolbar{display:grid;grid-template-columns:minmax(260px,.7fr) minmax(320px,1.3fr);gap:12px;padding:16px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.file-toolbar label{display:grid;gap:6px}.file-toolbar label>span{color:var(--sg-text-muted);font-size:10px}.file-search label>div{display:grid;grid-template-columns:1fr auto}.file-search input{min-width:0;padding:0 12px;color:var(--sg-text);font:inherit;background:rgba(255,255,255,.03);border:1px solid var(--sg-border-strong);border-right:0;border-radius:9px 0 0 9px;outline:none}.file-search input:focus{border-color:var(--sg-accent)}.file-search .el-button{border-radius:0 9px 9px 0}.file-panel{padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-lg)}.file-panel>header{display:flex;justify-content:space-between;align-items:flex-start}.file-panel h3{margin:3px 0 0;font-size:18px}.file-panel>header>span{color:var(--sg-text-muted);font-size:11px}.file-filters{display:flex;gap:9px;margin:16px 0 13px}.file-filters .sg-select{width:180px}.file-list{display:grid;gap:9px}.file-list.is-refreshing{opacity:.55;pointer-events:none}.file-list article{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:13px;align-items:center;padding:14px;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:11px}.file-icon{display:grid;width:38px;height:38px;color:var(--sg-accent);background:var(--sg-accent-soft);border-radius:10px;place-items:center}.file-main{min-width:0}.file-main header{display:flex;gap:7px;align-items:center}.file-main strong,.file-main p,.file-main small,.file-main code{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-main strong{font-size:12px}.file-main p{margin:5px 0;color:var(--sg-text-secondary);font-size:11px}.file-main small{color:var(--sg-text-muted);font-size:9px}.file-main code{margin-top:7px;color:var(--sg-accent);font-size:9px}.file-state,.primary-chip{padding:3px 6px;font-size:8px;border-radius:999px}.file-state{color:var(--sg-text-muted);background:rgba(255,255,255,.05)}.file-state[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.file-state[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.file-state[data-tone=danger]{color:var(--sg-danger);background:rgba(244,92,92,.1)}.primary-chip{color:var(--sg-accent);border:1px solid rgba(255,182,87,.25)}.file-actions{display:flex;gap:5px}.file-empty{display:grid;min-height:180px;padding:30px;color:var(--sg-text-muted);text-align:center;place-content:center;gap:8px}.file-empty>.el-icon{margin:auto;color:var(--sg-accent);font-size:32px}.file-empty strong{color:var(--sg-text-secondary);font-size:13px}.file-empty span{font-size:11px}.file-pagination{display:flex;gap:12px;align-items:center;justify-content:center;margin-top:14px;color:var(--sg-text-muted);font-size:11px}@media(max-width:820px){.file-toolbar{grid-template-columns:1fr}.file-list article{grid-template-columns:auto 1fr}.file-actions{grid-column:2;justify-content:flex-start}.file-filters{align-items:stretch;flex-direction:column}.file-filters .sg-select{width:100%}}@media(max-width:520px){.file-list article{grid-template-columns:1fr}.file-icon{display:none}.file-actions{grid-column:1}}
</style>
