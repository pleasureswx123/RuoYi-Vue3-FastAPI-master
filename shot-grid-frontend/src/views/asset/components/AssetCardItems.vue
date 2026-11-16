<script setup>
import FinalVersionTag from '@/components/version/FinalVersionTag.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getAssetItems } from '@/api/shot-grid/assets'
import { assetStatusMeta } from '@/views/asset/assetPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({
  projectId: { type: Number, required: true },
  asset: { type: Object, required: true },
  filters: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['open-item'])
const expanded = ref([])
const rows = ref([])
const loading = ref(false)
const error = ref(false)
const loaded = ref(false)
let controller
const visibleRows = computed(() => rows.value.filter(item => {
  if (item.lifecycleStatus !== 'active') return false
  const { assetStatus, assigneeUserId, productionFrom, productionTo } = props.filters
  if (assetStatus && item.assetStatus !== assetStatus) return false
  if (assigneeUserId && Number(item.task?.assigneeUserId) !== Number(assigneeUserId)) return false
  if (productionFrom || productionTo) {
    const start = item.task?.expectedStartTime?.slice(0, 10)
    const end = item.task?.expectedEndTime?.slice(0, 10)
    if (!start || !end || productionFrom && end < productionFrom || productionTo && start > productionTo) return false
  }
  return true
}))
async function load() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = false
  try {
    const { data } = await getAssetItems(props.projectId, props.asset.assetId, { signal: request.signal })
    if (request.signal.aborted) return
    if (!Array.isArray(data) || data.some(item => Number(item.projectId) !== props.projectId || Number(item.assetId) !== Number(props.asset.assetId))) throw new Error('资产分项范围无效')
    rows.value = [...data].sort((a, b) => a.sortOrder - b.sortOrder || a.assetItemId - b.assetItemId)
    loaded.value = true
  } catch (caught) {
    if (!request.signal.aborted && caught?.code !== 'ERR_CANCELED') error.value = true
  } finally { if (!request.signal.aborted) loading.value = false }
}
watch(expanded, value => {
  if (value.length && !loaded.value) load()
  else if (!value.length) { controller?.abort(); loading.value = false }
})
watch(() => [props.projectId, props.asset], () => {
  controller?.abort(); rows.value = []; loaded.value = false; error.value = false
  if (expanded.value.length) load()
})
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="asset-card-items" @click.stop @keydown.stop>
    <el-collapse v-model="expanded"><el-collapse-item name="items" :title="`制作分项 · ${asset.itemCount || 0}`">
      <el-skeleton v-if="loading" animated :rows="2" />
      <el-alert v-else-if="error" type="error" :closable="false" title="分项加载失败"><el-button link type="primary" @click="load">重试</el-button></el-alert>
      <template v-else>
        <el-text v-if="!visibleRows.length" size="small" type="info">当前筛选没有匹配分项</el-text>
        <div v-for="item in visibleRows" :key="item.assetItemId" class="asset-card-items__row">
          <el-button link type="primary" @click="emit('open-item', item)">{{ item.productionItem }}</el-button>
          <FinalVersionTag :row="item" /><small>{{ item.task?.assigneeName || (item.task?.assigneeUserId ? `制作人 ${item.task.assigneeUserId}` : '未分配') }}</small>
          <el-tag size="small" :type="tagTypeFromTone(assetStatusMeta(item.assetStatus).tone)">{{ assetStatusMeta(item.assetStatus).label }}</el-tag>
        </div>
      </template>
    </el-collapse-item></el-collapse>
  </div>
</template>

<style scoped>
.asset-card-items { margin-top: 12px; }
.asset-card-items__row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.asset-card-items__row .el-button { flex: 1; min-width: 0; white-space: normal; text-align: left; justify-content: flex-start; }
.asset-card-items__row small { color: var(--sg-text-muted); }
</style>
