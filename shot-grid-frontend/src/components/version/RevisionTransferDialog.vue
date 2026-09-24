<script setup>
import { onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getVersionDetail, getRevisionAssignees, transferRevision } from '@/api/shot-grid/versions'

const emit = defineEmits(['saved'])
const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const version = ref(null)
const formRef = ref(null)
const rejecting = ref(false)
const form = reactive({ assigneeUserId: null, reason: '', handoffNote: '' })
const options = ref([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
const optionsLoading = ref(false)
let controller = null
let searchController = null
let generation = 0
let submitHandler = null
const rules = {
  assigneeUserId: [{ required: true, message: '请选择接手制作人', trigger: 'change' }],
  reason: [{ validator: (_rule, value, callback) => {
    const changed = Number(form.assigneeUserId) !== Number(version.value?.assigneeUserId)
    callback(changed && !value.trim() ? new Error('请填写转交原因') : undefined)
  }, trigger: 'blur' }]
}
async function open(versionId, handler = null) {
  controller?.abort()
  const current = ++generation
  controller = new AbortController()
  submitHandler = handler
  rejecting.value = Boolean(handler)
  visible.value = true
  loading.value = true
  error.value = ''
  version.value = null
  Object.assign(form, { assigneeUserId: null, reason: '', handoffNote: '' })
  options.value = []
  page.value = 1
  keyword.value = ''
  try {
    const response = await getVersionDetail(versionId, { signal: controller.signal })
    if (current !== generation) return
    version.value = response.data
    if (handler) form.assigneeUserId = version.value.assigneeUserId
    await search()
  } catch (err) {
    if (current === generation && err.code !== 'ERR_CANCELED') error.value = err.message || '加载失败，请关闭后重试'
  } finally {
    if (current === generation) loading.value = false
  }
}
async function search(reset = false) {
  if (!version.value) return
  if (reset) page.value = 1
  searchController?.abort()
  const active = new AbortController()
  searchController = active
  optionsLoading.value = true
  try {
    const response = await getRevisionAssignees(version.value.projectId,
      { keyword: keyword.value || undefined, pageNum: page.value, pageSize: 20 }, { signal: active.signal })
    if (active.signal.aborted) return
    options.value = response.rows || response.data?.rows || []
    total.value = response.total ?? response.data?.total ?? 0
  } catch (err) {
    if (!active.signal.aborted) ElMessage.error(err.message || '制作人加载失败')
  } finally {
    if (!active.signal.aborted) optionsLoading.value = false
  }
}
async function submit() {
  if (busy.value || loading.value || !version.value || !(await formRef.value.validate().catch(() => false))) return
  busy.value = true
  error.value = ''
  try {
    const same = Number(form.assigneeUserId) === Number(version.value.assigneeUserId)
    const payload = { assigneeUserId: form.assigneeUserId, reason: form.reason.trim(), handoffNote: form.handoffNote.trim() || null }
    if (submitHandler) {
      if (!(await submitHandler(same ? null : payload))) return
    } else {
      await transferRevision(version.value.versionId, { ...payload, lockVersion: version.value.lockVersion, taskLockVersion: version.value.taskLockVersion })
      ElMessage.success('已转交修改，原版本与审核意见完整保留')
    }
    visible.value = false
    emit('saved')
  } catch (err) {
    error.value = err.message || '转交失败，请刷新后重试'
  } finally {
    busy.value = false
  }
}
function close() {
  generation += 1
  controller?.abort()
  searchController?.abort()
  formRef.value?.clearValidate()
}
onBeforeUnmount(close)
defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" :title="rejecting ? '退回修改 · 确认接手人' : '转交修改'" width="560px" append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @closed="close">
    <el-skeleton v-if="loading" animated :rows="3" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form v-if="version && !loading" ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="busy">
      <p>{{ version.taskName }} · {{ version.versionNumber }}<br>本版提交人：{{ version.submitterName }} · 当前负责人：{{ version.assigneeName }}</p>
      <el-alert title="接手人继续处理已有意见，提交下一版本；历史作品归属及排期保持不变。" type="info" :closable="false" />
      <el-form-item label="修改负责人" prop="assigneeUserId">
        <el-select v-model="form.assigneeUserId" filterable remote :remote-method="value => { keyword = value; search(true) }" :loading="optionsLoading" placeholder="搜索项目内制作人" style="width:100%">
          <el-option v-if="rejecting" :value="version.assigneeUserId" :label="`${version.assigneeName}（原负责人）`" />
          <el-option v-for="item in options.filter(item => Number(item.userId) !== Number(version.assigneeUserId))" :key="item.userId" :value="item.userId" :label="`${item.userName} · ${item.producerCode}`" />
        </el-select>
        <el-pagination v-if="total > 20" v-model:current-page="page" small layout="prev, pager, next" :page-size="20" :total="total" @current-change="search()" />
      </el-form-item>
      <template v-if="Number(form.assigneeUserId) !== Number(version.assigneeUserId)">
        <el-form-item label="转交原因" prop="reason"><el-input v-model="form.reason" type="textarea" :maxlength="1000" show-word-limit /></el-form-item>
        <el-form-item v-show="false" label="交接说明 / 源工程位置（选填）" prop="handoffNote"><el-input v-model="form.handoffNote" type="textarea" :maxlength="2000" show-word-limit /></el-form-item>
      </template>
    </el-form>
    <template #footer><el-button :disabled="busy" @click="visible = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="loading || !version" @click="submit">{{ rejecting ? '确认退回并发送' : '确认转交' }}</el-button></template>
  </el-dialog>
</template>
