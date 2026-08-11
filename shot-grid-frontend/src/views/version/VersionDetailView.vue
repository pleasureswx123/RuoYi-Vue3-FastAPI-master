<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Refresh, WarningFilled } from '@element-plus/icons-vue'

import { getVersionDetail } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'
import { versionErrorState } from '@/components/version/versionPresentation'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { useSessionStore } from '@/store/modules/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const version = ref(null)
const loading = ref(false)
const errorState = ref(null)
let controller = null
let generation = 0
let disposed = false

const versionId = computed(() => {
  try {
    return assertPositiveId(route.params.versionId, '版本')
  } catch {
    return null
  }
})
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const canQuery = computed(() => wildcard.value || sessionStore.permissions.includes('shotgrid:version:query'))
const canDownload = computed(() => wildcard.value || sessionStore.permissions.includes('shotgrid:file:download'))

async function loadVersion() {
  controller?.abort()
  controller = null
  version.value = null
  errorState.value = null
  loading.value = false
  const targetVersionId = versionId.value
  const targetGeneration = ++generation
  if (!targetVersionId) {
    errorState.value = versionErrorState({ httpStatus: 404, message: '版本详情地址无效' })
    return
  }
  if (!canQuery.value) {
    errorState.value = versionErrorState({ httpStatus: 403, message: '当前账号没有版本详情权限' })
    return
  }
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  try {
    const response = await getVersionDetail(targetVersionId, { signal: requestController.signal })
    if (disposed || controller !== requestController || requestController.signal.aborted || generation !== targetGeneration || versionId.value !== targetVersionId) return
    version.value = response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !requestController.signal.aborted && generation === targetGeneration) {
      errorState.value = versionErrorState(error, '版本详情加载失败')
    }
  } finally {
    if (controller === requestController) {
      controller = null
      loading.value = false
    }
  }
}

watch(versionId, loadVersion, { immediate: true })
onBeforeUnmount(() => {
  disposed = true
  generation += 1
  controller?.abort()
})
</script>

<template>
  <section class="sg-page version-detail-view">
    <header class="view-heading">
      <div><p class="sg-eyebrow">VERSION</p><h2>版本详情</h2><p>通过专用受保护接口查看不可覆盖的版本文件。</p></div>
      <div><el-button :icon="ArrowLeft" @click="router.back()">返回</el-button><el-button :icon="Refresh" :loading="loading" @click="loadVersion">刷新</el-button></div>
    </header>
    <div v-if="loading" class="view-state">正在加载版本详情…</div>
    <div v-else-if="errorState" class="view-state is-error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ errorState.title }}</strong><p>{{ errorState.message }}</p><code v-if="errorState.errorKey">{{ errorState.errorKey }}</code></div></div>
    <VersionDetailCard v-else-if="version" :version="version" :can-download="canDownload" />
  </section>
</template>

<style scoped lang="scss">
.version-detail-view { display: grid; gap: 18px; }
.view-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; }
.view-heading h2 { margin: 4px 0 7px; font-size: 28px; }
.view-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.view-heading > div:last-child { display: flex; gap: 8px; }
.view-state { display: flex; min-height: 220px; align-items: center; justify-content: center; padding: 30px; color: var(--sg-text-muted); text-align: center; background: var(--sg-surface); border: 1px dashed var(--sg-border); border-radius: var(--sg-radius-lg); }
.view-state.is-error { color: #ffb5ad; gap: 10px; }
.view-state strong,
.view-state p { display: block; margin: 0; }
.view-state p { margin-top: 5px; font-size: 11px; }
.view-state code { font-size: 10px; }

@media (max-width: 700px) {
  .view-heading { align-items: stretch; flex-direction: column; }
}
</style>
