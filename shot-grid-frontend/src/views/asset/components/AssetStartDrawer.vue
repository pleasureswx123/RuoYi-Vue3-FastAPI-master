<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { getAssetDetail } from '@/api/shot-grid/assets'
import { startTask } from '@/api/shot-grid/tasks'
import { useSessionStore } from '@/store/modules/session'
import { canAssetItemAction } from '../assetItemActions'
import { memberUserName } from '../assetPresentation'
import { formatTaskDateTime } from '@/views/task/taskPresentation'
import ProjectDrawer from '@/views/project/components/ProjectDrawer.vue'
const props = defineProps({ projectId: Number, contextKey: String, members: { type: Array, default: () => [] } })
const emit = defineEmits(['changed', 'active-change'])
const session = useSessionStore()
const visible = ref(false), loading = ref(false), saving = ref(false), attempted = ref(false), error = ref('')
const asset = ref(null), selected = ref([]), showUnavailable = ref(false), table = ref(null), formRef = ref(null)
const form = reactive({ confirmed: false })
let generation = 0, controller
const permitted = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const eligible = row => canAssetItemAction(asset.value, row, 'task.start', permitted)
const eligibleRows = computed(() => (asset.value?.items || []).filter(eligible))
const displayRows = computed(() => showUnavailable.value ? asset.value?.items || [] : eligibleRows.value)
const single = computed(() => eligibleRows.value.length === 1)
const rules = { confirmed: [{ validator: (_r, value, done) => done(value ? undefined : new Error('请确认制作条件齐备')) }] }
const name = row => memberUserName(props.members.find(member => Number(member.userId) === Number(row.task?.assigneeUserId)) || { nickName: row.task?.assigneeName, userId: row.task?.assigneeUserId })
function reason(row) {
  if (!row.task) return '需先分配制作人'
  if (row.task.taskStatus !== 'not_started') return '当前状态不可开工'
  if (!row.task.expectedStartTime || !row.task.expectedEndTime) return '需先设置排期'
  return '当前权限或制作条件不满足'
}
function reset() { generation++; controller?.abort(); visible.value = false; saving.value = false; loading.value = false; selected.value = []; asset.value = null }
watch(() => props.contextKey, reset)
watch(visible, value => emit('active-change', value))
onBeforeUnmount(reset)
async function open(parent) {
  if (visible.value || Number(parent.projectId) !== props.projectId || !permitted('shotgrid:asset:query') || !permitted('shotgrid:task:start')) return
  reset(); visible.value = true; loading.value = true; error.value = ''; attempted.value = false; form.confirmed = false; showUnavailable.value = false
  const token = generation
  controller = new AbortController()
  try {
    const { data } = await getAssetDetail(props.projectId, parent.assetId, { signal: controller.signal })
    if (token !== generation) return
    if (Number(data.projectId) !== props.projectId || Number(data.assetId) !== Number(parent.assetId)) throw new Error('资产范围已变化，请刷新后重试')
    asset.value = { ...data, items: data.items.map(row => ({ ...row, result: '' })) }
    loading.value = false
    await nextTick()
    if (token === generation && single.value) selected.value = [...eligibleRows.value]
  } catch (failure) { if (token === generation) error.value = failure.message || '加载失败，请关闭重试' }
  finally { if (token === generation) loading.value = false }
}
async function submit() {
  if (saving.value || attempted.value || loading.value || !selected.value.length || selected.value.length > 100 || !selected.value.every(eligible)) return
  saving.value = true
  const token = generation
  if (!await formRef.value?.validate().catch(() => false) || token !== generation) { if (token === generation) saving.value = false; return }
  attempted.value = true
  const targets = [...selected.value]
  try {
    for (const row of targets) {
      if (token !== generation) return
      row.result = '正在确认'
      const { data } = await startTask(row.task.taskId, { lockVersion: row.task.lockVersion, assetLockVersion: asset.value.lockVersion, assetItemLockVersion: row.lockVersion, startConfirmed: true })
      if (token !== generation) return
      row.result = data?.taskStatus === 'preparing' ? '目录准备中' : '已开工'
    }
  } catch (failure) {
    if (token === generation) {
      const message = failure.message || '结果未知，请刷新核对后重试'
      targets.filter(row => row.result === '正在确认').forEach(row => { row.result = message })
      error.value = `${message}；后续分项未执行，请关闭刷新后核对。`
    }
  } finally {
    if (token === generation) { targets.filter(row => !row.result).forEach(row => { row.result = '未执行' }); saving.value = false; emit('changed') }
  }
}
defineExpose({ open })
</script>
<template>
  <ProjectDrawer v-if="visible" :title="single ? '确认分项开工' : '选择分项开工'" :description="asset?.assetName || '正在加载'" wide :busy="saving" @close="reset">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <div class="start-summary"><el-text>可开工 {{ eligibleRows.length }} 项</el-text><el-switch v-if="asset?.items.length > eligibleRows.length" v-model="showUnavailable" active-text="显示其他分项" :disabled="saving || attempted" /></div>
      <el-table ref="table" v-loading="loading" :data="displayRows" row-key="assetItemId" class="start-table" @selection-change="selected = $event">
        <el-table-column v-if="!single" type="selection" :selectable="row => !saving && !attempted && eligible(row)" width="48" reserve-selection />
        <el-table-column prop="productionItem" label="制作分项" min-width="160" />
        <el-table-column label="制作人" width="110"><template #default="{ row }">{{ name(row) }}</template></el-table-column>
        <el-table-column label="计划时间" min-width="175"><template #default="{ row }"><div>{{ formatTaskDateTime(row.task?.expectedStartTime) }}</div><div>{{ formatTaskDateTime(row.task?.expectedEndTime) }}</div></template></el-table-column>
        <el-table-column label="状态 / 结果" min-width="170"><template #default="{ row }">{{ row.result || (eligible(row) ? '待开工' : reason(row)) }}</template></el-table-column>
        <template #empty><el-empty :image-size="60" description="暂无可开工分项" /></template>
      </el-table>
      <el-form-item v-if="!attempted" prop="confirmed" class="start-confirm"><el-checkbox v-model="form.confirmed" :disabled="loading || saving">我已确认所选分项的制作条件齐备，可以开工</el-checkbox></el-form-item>
    </el-form>
    <template #footer><el-text class="start-count">已选 {{ selected.length }} 项</el-text><el-button :disabled="saving" @click="reset">{{ attempted ? '完成' : '取消' }}</el-button><el-button v-if="!attempted" type="primary" :loading="saving" :disabled="loading || Boolean(error) || !selected.length || selected.length > 100" @click="submit">确认开工{{ single ? '' : `所选 ${selected.length} 项` }}</el-button></template>
  </ProjectDrawer>
</template>
<style scoped>
.start-summary{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.start-table{font-size:12px}.start-confirm{margin-top:20px}.start-count{margin-right:16px}.start-confirm :deep(.el-checkbox__label){white-space:normal}
</style>
