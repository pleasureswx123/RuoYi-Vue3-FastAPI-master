<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'

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
      <div><p class="sg-eyebrow">VERSION</p><h2>版本详情</h2><p>查看版本文件、提交说明与审核信息，历史版本始终保留。</p></div>
      <div><el-button :icon="ArrowLeft" @click="router.back()">返回</el-button><el-button :icon="Refresh" :loading="loading" @click="loadVersion">刷新</el-button></div>
    </header>
    <el-skeleton v-if="loading" class="view-state" :rows="6" animated />
    <el-alert v-else-if="errorState" class="view-state is-error" :title="errorState.title" :description="errorState.message" type="error" :closable="false" show-icon />
    <VersionDetailCard v-else-if="version" :version="version" :can-download="canDownload" />
    <el-empty v-else class="view-state" description="当前没有可展示的版本详情" />
  </section>
</template>

<style scoped lang="scss">
.version-detail-view { display: grid; gap: 18px; }
.view-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; }
.view-heading h2 { margin: 4px 0 7px; font-size: 28px; }
.view-heading p:not(.sg-eyebrow) { margin: 0; color: var(--sg-text-muted); font-size: 12px; }
.view-heading > div:last-child { display: flex; gap: 8px; }
.view-state { min-height: 220px; padding: 30px; background: var(--sg-surface); border: 1px dashed var(--sg-border); border-radius: var(--sg-radius-lg); }
.view-state.is-error { min-height: auto; border-style: solid; }
.view-state code { display: block; margin-top: 6px; font-size: 10px; }

@media (max-width: 700px) {
  .view-heading { align-items: stretch; flex-direction: column; }
}
</style>
