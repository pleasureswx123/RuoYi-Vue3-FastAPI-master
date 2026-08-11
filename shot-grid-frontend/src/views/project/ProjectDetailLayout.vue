<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getProject, getProjectStorage } from '@/api/shot-grid/projects'
import { canWriteBusiness, domainErrorMessage, PROJECT_STATUS, STORAGE_STATUS } from '@/utils/projectDomain'

const props = defineProps({ projectId: { type: String, required: true } })
const router = useRouter()
const project = ref(null)
const storage = ref(null)
const loading = ref(false)
const error = ref('')
let controller
const validProjectId = computed(() => /^\d+$/.test(props.projectId) && Number(props.projectId) > 0)
const writeEnabled = computed(() => canWriteBusiness(storage.value?.storageStatus || project.value?.storageStatus))
const storageMeta = computed(() => STORAGE_STATUS[storage.value?.storageStatus || project.value?.storageStatus] || {})

async function load() {
  if (!validProjectId.value) { error.value = '项目 ID 不正确。'; return }
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try { [project.value, storage.value] = await Promise.all([getProject(props.projectId, { signal: controller.signal }), getProjectStorage(props.projectId, { signal: controller.signal })]) }
  catch (reason) { if (reason?.code !== 'ERR_CANCELED') error.value = domainErrorMessage(reason, '项目详情加载失败。') }
  finally { loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="page project-detail-page" v-loading="loading">
    <div v-if="error" class="state-panel state-panel--error"><strong>项目不可用</strong><p>{{ error }}</p><el-button @click="load">重试</el-button></div>
    <template v-else-if="project">
      <header class="project-detail-header"><div><span class="eyebrow">{{ project.projectCode }}</span><h1>{{ project.projectName }}</h1><div class="tag-row"><el-tag :type="PROJECT_STATUS[project.projectStatus]?.type">{{ PROJECT_STATUS[project.projectStatus]?.label }}</el-tag><el-tag :type="storageMeta.type">{{ storageMeta.label }}</el-tag></div></div><div class="project-actions"><el-button :disabled="!writeEnabled" @click="router.push({ name: 'ShotImport', params: { projectId } })">导入镜头</el-button><el-button :disabled="!writeEnabled" @click="router.push({ name: 'AssetImport', params: { projectId } })">导入资产</el-button><el-button type="primary" :disabled="!writeEnabled">新建业务数据</el-button></div></header>
      <el-alert v-if="!writeEnabled" :title="storageMeta.description" :description="storage?.lastErrorMessage || '存储就绪前仍可查看项目、查看概览和维护成员。目录重试由后端受控任务执行。'" :type="storage?.storageStatus === 'failed' ? 'error' : 'warning'" show-icon :closable="false"><template #default><el-button v-if="storage?.storageStatus === 'failed'" text @click="load">刷新状态</el-button></template></el-alert>
      <nav class="project-tabs" aria-label="项目导航"><RouterLink :to="`/projects/${projectId}/overview`">概览</RouterLink><RouterLink :to="`/projects/${projectId}/scenes`">场次</RouterLink><RouterLink :to="`/projects/${projectId}/shots`">镜头</RouterLink><RouterLink :to="`/projects/${projectId}/assets`">资产</RouterLink><RouterLink :to="`/projects/${projectId}/reviews`">审核</RouterLink><RouterLink :to="`/projects/${projectId}/members`">成员</RouterLink></nav>
      <slot :project="project" :storage="storage" :write-enabled="writeEnabled" :refresh="load" />
    </template>
  </section>
</template>
