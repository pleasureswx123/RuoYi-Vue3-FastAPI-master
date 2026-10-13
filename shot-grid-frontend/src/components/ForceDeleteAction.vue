<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElAlert, ElMessage } from 'element-plus'
import { useSessionStore } from '@/store/modules/session'
import { batchForceDeleteShots } from '@/api/shot-grid/shots'
import { batchForceDeleteAssets } from '@/api/shot-grid/assets'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  entityType: { type: String, required: true },
  compact: { type: Boolean, default: false },
  items: { type: Array, default: () => [] }
})
const emit = defineEmits(['deleted'])
const session = useSessionStore()
const visible = ref(false)
const loading = ref(false)
const formRef = ref()
const form = reactive({ reason: '' })
const rules = { reason: [{ required: true, whitespace: true, message: '请填写删除原因', trigger: 'blur' }, { max: 500, message: '原因不能超过 500 字', trigger: 'blur' }] }
const label = computed(() => props.entityType === 'shot' ? '镜头' : '资产')
const permitted = computed(() => session.permissions.includes('*:*:*') || session.permissions.includes(`shotgrid:${props.entityType}:forceDelete`))
const visibleAction = computed(() => permitted.value && props.items.some(item => item?.allowedActions?.includes(`${props.entityType}.forceDelete`)))
const eligible = computed(() => permitted.value && props.items.length > 0 && props.items.length <= 200 && props.items.every(item => item?.allowedActions?.includes(`${props.entityType}.forceDelete`)))
let generation = 0
let snapshot = null
function invalidate() {
  generation += 1
  visible.value = false
  loading.value = false
  snapshot = null
}
// 表格重绘会重新创建 items 数组，仅业务目标或授权变化时重置弹窗。
watch([
  () => props.projectId,
  () => props.entityType,
  permitted,
  () => props.items.map(item => item?.[`${props.entityType}Id`]).join(',')
], invalidate)
onBeforeUnmount(invalidate)
function open() {
  if (!eligible.value || loading.value) return
  const key = `${props.entityType}Id`
  snapshot = { projectId: props.projectId, kind: props.entityType, generation: ++generation,
    items: props.items.map(item => ({ [key]: item[key], lockVersion: item.lockVersion })) }
  form.reason = ''
  formRef.value?.clearValidate()
  visible.value = true
}
async function submit() {
  if (loading.value || !snapshot || !permitted.value) return
  const context = snapshot
  if (!await formRef.value.validate().catch(() => false)) return
  if (context.generation !== generation || loading.value) return
  loading.value = true
  try {
    const send = context.kind === 'shot' ? batchForceDeleteShots : batchForceDeleteAssets
    const result = await send(context.projectId, context.items, form.reason.trim())
    if (context.generation !== generation) return
    visible.value = false
    ElMessage.success('业务记录已永久删除，文件清理完成后可重新使用原编号或名称')
    emit('deleted', { projectId: context.projectId, purges: result.data?.purges || [] })
  } catch (error) {
    if (context.generation === generation) ElMessage.error(error?.message || '强制删除失败，请刷新后重试')
  } finally {
    if (context.generation === generation) loading.value = false
  }
}
</script>

<template>
  <el-button v-if="visibleAction" type="danger" :text="!compact" :plain="compact" :size="compact ? 'small' : 'default'" :disabled="!eligible || loading" @click="open">强制删除{{ label }}<template v-if="!compact">（{{ items.length }}）</template></el-button>
  <!-- 保留页面滚动条宽度，避免自动列布局跨阈值重建操作单元格。遮罩和焦点约束仍由 Dialog 管理。 -->
  <el-dialog v-model="visible" :title="`强制删除${label}`" width="480px" append-to-body :lock-scroll="false" :close-on-click-modal="false" :close-on-press-escape="!loading" :show-close="!loading" destroy-on-close>
    <el-alert type="warning" :closable="false" :title="`将永久删除 ${snapshot?.items.length || 0} 个${label}、制作历史及独占文件，此操作不可恢复。`" />
    <p>{{ entityType === 'shot' ? '其他镜头编号不变。' : '将同时删除制作分项并解除镜头关联。' }}文件清理完成后，才能重新使用原编号或名称。</p>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="删除原因" prop="reason"><el-input v-model="form.reason" type="textarea" :rows="3" :maxlength="500" show-word-limit :disabled="loading" /></el-form-item>
    </el-form>
    <template #footer><el-button :disabled="loading" @click="visible = false">取消</el-button><el-button type="danger" :loading="loading" :disabled="!permitted" @click="submit">确认强制删除</el-button></template>
  </el-dialog>
</template>
