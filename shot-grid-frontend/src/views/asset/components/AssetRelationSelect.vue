<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getAssetPage } from '@/api/shot-grid/assets'
import { assetTypeMeta } from '../assetPresentation'
const props = defineProps({ projectId: { type: Number, required: true }, assetId: { type: Number, default: 0 }, modelValue: { type: Array, default: () => [] }, initialAssets: { type: Array, default: () => [] }, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const options = ref([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const page = ref(1)
const more = ref(false)
let controller
let disposed = false
const choices = computed(() => [...new Map([...props.initialAssets, ...options.value].filter(row => Number(row.assetId) !== props.assetId).map(row => [Number(row.assetId), row])).values()])
async function search(value = '', append = false) {
  if (props.disabled || disposed || append && loading.value) return
  controller?.abort()
  const request = new AbortController()
  controller = request
  const projectId = props.projectId
  if (!append) { keyword.value = value; page.value = 1; more.value = false; options.value = options.value.filter(row => props.modelValue.includes(Number(row.assetId))) }
  loading.value = true; error.value = ''
  try {
    const result = await getAssetPage(projectId, { keyword: keyword.value || undefined, pageNum: append ? page.value + 1 : 1, pageSize: 100 }, { signal: request.signal })
    if (disposed || controller !== request || request.signal.aborted || projectId !== props.projectId) return
    if ((result.rows || []).some(row => Number(row.projectId) !== projectId)) throw new Error('资产项目归属不匹配，请重试')
    options.value = [...options.value, ...(result.rows || []).filter(row => row.lifecycleStatus === 'active')]
    if (append) page.value++
    more.value = Boolean(result.hasNext)
  } catch (failure) { if (controller === request && !request.signal.aborted && !disposed) error.value = failure.message || '资产加载失败' }
  finally { if (controller === request) loading.value = false }
}
watch(() => props.projectId, () => { controller?.abort(); options.value = []; error.value = ''; more.value = false; loading.value = false })
onBeforeUnmount(() => { disposed = true; controller?.abort() })
</script>
<template>
  <div class="asset-relation-select">
    <el-select :model-value="modelValue" multiple filterable remote reserve-keyword :remote-method="search" :loading="loading" :disabled="disabled" placeholder="搜索并选择需要的角色、场景或道具" aria-label="选择关联资产" @update:model-value="emit('update:modelValue', $event)" @visible-change="open => { if (open && !options.length) search() }">
      <el-option v-for="asset in choices" :key="asset.assetId" :value="Number(asset.assetId)" :label="`${assetTypeMeta(asset.assetType).label} · ${asset.assetName}${asset.lifecycleStatus === 'archived' ? '（已归档）' : ''}`" :disabled="!modelValue.includes(Number(asset.assetId)) && (asset.lifecycleStatus !== 'active' || modelValue.length >= 50)" />
      <template #footer><el-button v-if="more" text :loading="loading" @click.stop="search(keyword, true)">加载更多资产</el-button><el-text size="small">最多关联 50 个资产，不影响开工</el-text></template>
    </el-select>
    <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button text @click="search(keyword)">重新加载</el-button></el-alert>
  </div>
</template>
<style scoped>.asset-relation-select,.asset-relation-select :deep(.el-select){width:100%}.asset-relation-select{display:grid;gap:8px}</style>
