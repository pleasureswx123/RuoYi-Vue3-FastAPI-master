<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElPagination, ElTable, ElTableColumn, ElMessage } from 'element-plus'
import { listTargetPurges, retryTargetPurge } from '@/api/shot-grid/targetPurges'
import { useSessionStore } from '@/store/modules/session'

const props = defineProps({ projectId: { type: [Number, String], default: null }, entityType: { type: String, required: true }, refreshKey: { type: Number, default: 0 } })
const session = useSessionStore()
const permitted = computed(() => session.permissions.includes('*:*:*') || session.permissions.includes(`shotgrid:${props.entityType}:forceDelete`))
const rows = ref([])
const total = ref(0)
const page = ref(1)
const error = ref('')
const retrying = ref(null)
let generation = 0
let timer
let controller
const labels = { pending: '等待清理', processing: '正在清理', retry_wait: '等待重试', failed: '清理失败', succeeded: '清理完成' }
function cancel() {
  generation += 1
  clearTimeout(timer)
  controller?.abort()
}
async function load() {
  cancel()
  if (!props.projectId || !permitted.value) { rows.value = []; total.value = 0; return }
  const current = generation
  controller = new AbortController()
  try {
    const result = await listTargetPurges(props.projectId, { targetKind: props.entityType, pageNum: page.value, pageSize: 20, unfinishedOnly: true }, controller.signal)
    if (current !== generation) return
    rows.value = result.rows || []
    total.value = result.total || 0
    error.value = ''
    if (total.value) timer = setTimeout(load, 5000)
  } catch (failure) {
    if (current !== generation) return
    error.value = failure?.message || '清理状态暂时无法获取'
  }
}
async function retry(row) {
  if (retrying.value || !permitted.value) return
  const current = generation
  retrying.value = row.purgeId
  try {
    await retryTargetPurge(props.projectId, row.purgeId)
    if (current === generation) await load()
  } catch (failure) {
    if (current === generation) ElMessage.error(failure?.message || '重试失败')
  } finally {
    retrying.value = null
  }
}
watch([() => props.projectId, () => props.entityType, permitted, () => props.refreshKey], () => { page.value = 1; rows.value = []; total.value = 0; error.value = ''; load() }, { immediate: true })
onBeforeUnmount(cancel)
</script>

<template>
  <div v-if="permitted && (total || error)" class="target-purge-status">
    <el-alert v-if="error" :title="error" type="warning" :closable="false"><el-button text @click="load">刷新清理状态</el-button></el-alert>
    <template v-else>
      <el-alert title="业务记录已永久删除，文件仍在清理。清理完成后可重新使用原编号或名称。" type="warning" :closable="false" />
      <el-table :data="rows" row-key="purgeId" size="small">
        <el-table-column prop="targetLabel" label="目标" />
        <el-table-column label="清理状态"><template #default="{ row }">{{ labels[row.purgeStatus] }}</template></el-table-column>
        <el-table-column prop="lastErrorMessage" label="说明" />
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="row.canRetry" text :loading="retrying === row.purgeId" :disabled="Boolean(retrying)" @click="retry(row)">重试清理</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" />
    </template>
  </div>
</template>
