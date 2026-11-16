<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { getAssetRelations, updateAssetRelations, getAssetDetail } from '@/api/shot-grid/assets'
import { getShotDetail } from '@/api/shot-grid/shots'
import { useSessionStore } from '@/store/modules/session'
import { assetStatusMeta, assetTypeMeta } from '../assetPresentation'
import { tagTypeFromTone } from '@/utils/tag'
import AssetRelationSelect from './AssetRelationSelect.vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import RelatedAssetResult from './RelatedAssetResult.vue'
const props = defineProps({ projectId: { type: Number, required: true }, assetId: { type: Number, default: 0 }, shotId: { type: Number, default: 0 } })
const emit = defineEmits(['updated'])
const session = useSessionStore()
const router = useRouter()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const data = ref(null)
const loading = ref(false)
const error = ref('')
const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const uncertain = ref(false)
const formRef = ref(null)
const form = reactive({ relatedAssetIds: [] })
const expanded = ref(['Character', 'Environment', 'Prop'])
const detail = ref(null)
let controller
let generation = 0
let disposed = false
const groups = computed(() => ['Character', 'Environment', 'Prop'].map(type => ({ type, assets: (data.value?.relatedAssets || []).filter(row => row.assetType === type) })).filter(group => group.assets.length))
const canEdit = computed(() => !props.shotId && data.value?.canEdit && allowed('shotgrid:asset:edit') && allowed('shotgrid:asset:list'))
const dirty = computed(() => saving.value || (editing.value && changed.value))
const changed = computed(() => JSON.stringify([...form.relatedAssetIds].sort((a,b) => a-b)) !== JSON.stringify((data.value?.relatedAssets || []).map(row => row.assetId).sort((a,b) => a-b)))
const rules = { relatedAssetIds: [{ validator: (_rule, ids, done) => done(Array.isArray(ids) && ids.length <= 50 && ids.every(id => Number.isSafeInteger(id) && id > 0 && id !== props.assetId) && new Set(ids).size === ids.length ? undefined : new Error('请选择有效且不重复的关联资产（最多 50 项）')), trigger: 'change' }] }
function availability(item) {
  if (item.version?.versionStatus === 'final') return { label: '已通过可用', type: 'success' }
  if (item.version) return { label: '未通过，仅供参考', type: 'warning' }
  if (['preparing', 'in_progress', 'revision'].includes(item.assetStatus)) return { label: '制作中 · 暂无成果', type: 'warning' }
  return { label: '暂无成果', type: 'info' }
}
async function reload() {
  controller?.abort()
  const token = ++generation
  const request = new AbortController()
  controller = request
  data.value = null; editing.value = false; error.value = ''; loading.value = true
  try {
    if (!allowed('shotgrid:asset:query')) throw new Error('没有查看关联资产的权限')
    if (props.shotId) {
      if (!allowed('shotgrid:shot:query')) throw new Error('没有查看镜头关联的权限')
      const { data: shot } = await getShotDetail(props.projectId, props.shotId, { signal: request.signal })
      if (disposed || token !== generation || request.signal.aborted) return
      if (Number(shot.projectId) !== props.projectId || Number(shot.shotId) !== props.shotId) throw new Error('镜头关联归属不匹配')
      const assets = [...new Map((shot.assets || []).map(asset => [Number(asset.assetId), asset])).values()]
      const relatedAssets = []
      // 分批读取既有鉴权详情，避免大量关联同时发出请求。
      for (let index = 0; index < assets.length; index += 4) {
        const batch = await Promise.all(assets.slice(index, index + 4).map(async asset => {
          try {
            const { data: detail } = await getAssetDetail(props.projectId, asset.assetId, { signal: request.signal })
            if (Number(detail.projectId) !== props.projectId || Number(detail.assetId) !== Number(asset.assetId)) throw new Error('资产归属不匹配')
            return { ...detail, items: (detail.items || []).filter(item => item.lifecycleStatus === 'active').map(item => ({ ...item, version: item.finalVersion || item.latestVersion })) }
          } catch (failure) { return { ...asset, items: [], loadError: failure.message || '资产读取失败' } }
        }))
        if (disposed || token !== generation || request.signal.aborted) return
        relatedAssets.push(...batch)
      }
      data.value = { relatedAssets }
      return
    }
    const response = await getAssetRelations(props.projectId, props.assetId, { signal: request.signal })
    if (disposed || token !== generation || request.signal.aborted) return
    const result = response.data
    if (Number(result?.projectId) !== props.projectId || Number(result?.assetId) !== props.assetId || !Array.isArray(result.relatedAssets) || result.relatedAssets.some(row => Number(row.projectId) !== props.projectId || Number(row.assetId) === props.assetId)) throw new Error('关联资料归属不匹配，请刷新')
    data.value = result
  } catch (failure) { if (!disposed && token === generation && !request.signal.aborted) error.value = failure.message || '关联资产加载失败' }
  finally { if (token === generation) loading.value = false }
}
function edit() {
  if (!canEdit.value || saving.value) return
  form.relatedAssetIds = data.value.relatedAssets.map(row => row.assetId)
  saveError.value = ''; uncertain.value = false; editing.value = true
}
async function save() {
  if (saving.value || uncertain.value || !canEdit.value || !changed.value) return
  saving.value = true
  const token = generation
  const projectId = props.projectId, assetId = props.assetId
  try {
    if (!await formRef.value?.validate().catch(() => false) || token !== generation || disposed) return
    await updateAssetRelations(projectId, assetId, { relatedAssetIds: [...form.relatedAssetIds], lockVersion: data.value.lockVersion })
    if (token !== generation || disposed) return
    editing.value = false
    ElMessage.success('关联资产已更新')
    await reload(); saving.value = false; emit('updated')
  } catch (failure) {
    if (token !== generation || disposed) return
    const status = Number(failure.httpStatus || failure.status || failure.response?.status)
    uncertain.value = ![401,403,404,409,422].includes(status) || status === 409
    saveError.value = uncertain.value ? '保存结果需核对，请刷新关联后再调整；当前选择已保留。' : failure.message || '保存失败'
  } finally { saving.value = false }
}
async function canLeave() {
  if (saving.value) { ElMessage.warning('关联正在保存，请稍候'); return false }
  if (editing.value && changed.value) {
    try { await ElMessageBox.confirm('关联修改尚未保存，确定放弃？', '未保存的关联', { type: 'warning' }) } catch { return false }
  }
  return true
}
async function cancel() { if (await canLeave()) editing.value = false }
function openAsset(asset) { router.push(`/projects/${props.projectId}/assets/${asset.assetId}`) }
watch([() => props.projectId, () => props.assetId, () => props.shotId, () => session.permissions.join('|')], reload, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort() })
defineExpose({ canLeave, reload, dirty })
</script>
<template>
  <section class="asset-relations" aria-label="关联资产资料">
    <header><strong>关联资产</strong><el-button v-if="canEdit && !editing" text type="primary" @click="edit">调整关联</el-button><el-button v-if="!editing" text :loading="loading" @click="reload">刷新</el-button></header>
    <el-skeleton v-if="loading" :rows="3" animated />
    <el-alert v-else-if="error" :title="error" type="error" :closable="false"><el-button @click="reload">重试</el-button></el-alert>
    <template v-else>
      <el-form v-if="editing" ref="formRef" :model="form" :rules="rules" label-position="top" aria-label="编辑资产关联">
        <el-form-item label="当前任务需要的资产" prop="relatedAssetIds"><AssetRelationSelect v-model="form.relatedAssetIds" :project-id="projectId" :asset-id="assetId" :initial-assets="data.relatedAssets" :disabled="saving" /></el-form-item>
        <el-alert v-if="saveError" :title="saveError" type="error" :closable="false" />
        <el-form-item><el-button type="primary" :loading="saving" :disabled="!changed || uncertain" @click="save">保存关联</el-button><el-button :disabled="saving" @click="cancel">取消</el-button><el-button v-if="uncertain" :disabled="saving" @click="async () => { if (await canLeave()) reload() }">刷新核对</el-button></el-form-item>
      </el-form>
      <el-collapse v-if="groups.length" v-model="expanded">
        <el-collapse-item v-for="group in groups" :key="group.type" :name="group.type" :title="`${assetTypeMeta(group.type).label} · ${group.assets.length}`">
          <el-card v-for="asset in group.assets" :key="asset.assetId" shadow="never" class="related-asset">
            <template #header><el-button link type="primary" @click="openAsset(asset)">{{ asset.assetName }}</el-button><el-tag v-if="asset.lifecycleStatus === 'archived'" size="small" type="info">已归档</el-tag></template>
            <el-alert v-if="asset.loadError" :title="asset.loadError" type="warning" :closable="false"><el-button text @click="reload">重新加载</el-button></el-alert>
            <div v-for="item in asset.items" :key="item.assetItemId" class="related-item">
              <div><strong>{{ item.productionItem || '未命名分项' }}</strong><el-tag size="small" :type="tagTypeFromTone(assetStatusMeta(item.assetStatus).tone)">{{ assetStatusMeta(item.assetStatus).label }}</el-tag><el-tag size="small" :type="availability(item).type">{{ availability(item).label }}</el-tag></div>
              <el-text size="small">制作人：{{ item.task?.assigneeName || (item.task?.assigneeUserId ? `用户 ${item.task.assigneeUserId}` : '未分配') }}</el-text>
              <template v-if="item.version"><el-text size="small" :type="item.version.versionStatus === 'final' ? 'success' : 'warning'">{{ item.version.versionNumber || `V${String(item.version.versionNo).padStart(3, '0')}` }} · {{ item.version.versionStatus === 'final' ? '已通过成果' : '未通过，仅供参考' }}</el-text><el-button size="small" :disabled="!allowed('shotgrid:version:query')" @click="detail.open(`/versions/${item.version.versionId}`)">查看成果</el-button></template>
              <el-text v-else type="info" size="small">尚未提交成果</el-text>
              <RelatedAssetResult v-if="item.version && item.task?.taskId" :project-id="projectId" :item="item" />
            </div>
            <el-empty v-if="!asset.loadError && !asset.items.length" :image-size="36" description="暂无活动制作分项" />
          </el-card>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else-if="!editing" :image-size="40" :description="canEdit ? '暂未关联资产，可提前添加需要的角色、场景或道具' : '暂未关联资产，需要时请项目管理人关联角色、场景或道具'" />
    </template>
    <RelatedDetailDrawer ref="detail" @closed="async () => { if (!editing) reload() }" />
  </section>
</template>
<style scoped>
.asset-relations{display:grid;gap:10px}.asset-relations>header,.related-item>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.asset-relations>header strong{margin-right:auto}.related-asset{margin:8px 0}.related-item{display:grid;justify-items:start;gap:6px;padding:10px 0;border-bottom:1px solid var(--sg-border)}.related-item:last-child{border:0}.related-item strong{overflow-wrap:anywhere}.asset-relations :deep(.el-card__body){padding:8px 12px}
</style>
