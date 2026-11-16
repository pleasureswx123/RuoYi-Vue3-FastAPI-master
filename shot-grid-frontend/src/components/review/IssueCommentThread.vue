<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getIssueComments, addIssueComment } from '@/api/shot-grid/reviews'
import { createIdempotencyState } from '@/utils/idempotency'
import { formatVersionDateTime } from '@/components/version/versionPresentation'

const props = defineProps({ projectId: Number, versionId: Number, issueId: Number, canComment: Boolean, refreshKey: Number })
const opened = ref(false)
const rows = ref([])
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const submitError = ref('')
const hasMore = ref(false)
const cursor = ref(null)
const form = reactive({ content: '' })
const formRef = ref(null)
const idempotency = createIdempotencyState('issue-comment')
let controller = null
let submitController = null
let generation = 0
let disposed = false
const rules = { content: [{ validator: (_rule, value, callback) => {
  const text = String(value || '').trim()
  callback(!text ? new Error('请输入评论内容') : text.length > 2000 ? new Error('评论最多 2000 字') : undefined)
}, trigger: 'blur' }] }
const dirty = computed(() => Boolean(form.content.trim()))
function validRow(row) {
  if (Number(row?.projectId) !== props.projectId || Number(row?.noteId) !== props.issueId) throw new Error('评论归属不匹配，请刷新')
  return row
}
async function loadMore(append = false) {
  if (!opened.value || (append && (loading.value || !hasMore.value))) return
  controller?.abort()
  const request = new AbortController(); controller = request
  const current = generation
  loading.value = true; error.value = ''
  try {
    const response = await getIssueComments(props.versionId, props.issueId, { pageSize: 20, ...(append ? { beforeId: cursor.value } : {}) }, { signal: request.signal })
    if (disposed || current !== generation || request.signal.aborted) return
    const items = (response.data?.rows || []).map(validRow)
    const next = response.data?.nextCursor
    if (response.data?.hasNext && (!items.length || !Number.isSafeInteger(next) || (append && next >= cursor.value))) throw new Error('评论分页已变化，请刷新')
    rows.value = [...new Map([...(append ? rows.value : []), ...items].map(item => [item.commentId, item])).values()]
    hasMore.value = Boolean(response.data?.hasNext); cursor.value = next
  } catch (err) {
    if (!disposed && current === generation && !request.signal.aborted) error.value = err.message || '评论加载失败'
  } finally { if (controller === request) loading.value = false }
}
async function submit() {
  if (sending.value || !props.canComment) return
  sending.value = true
  const current = generation
  try {
    const valid = await formRef.value?.validate().catch(() => false)
    if (!valid || disposed || current !== generation || !props.canComment) return
    const content = form.content.trim()
    const payload = { content, requestId: idempotency.forPayload({ issueId: props.issueId, content }) }
    const request = new AbortController(); submitController = request
    submitError.value = ''
    const response = await addIssueComment(props.versionId, props.issueId, payload, { signal: request.signal })
    if (disposed || current !== generation || request.signal.aborted) return
    const saved = validRow(response.data)
    rows.value = [saved, ...rows.value.filter(item => item.commentId !== saved.commentId)]
    formRef.value?.resetFields(); form.content = ''; idempotency.reset()
    ElMessage.success('评论已保存')
  } catch (err) {
    if (!disposed && current === generation) submitError.value = err.message || '评论未保存，请重试'
  } finally { if (current === generation) sending.value = false }
}
watch(opened, value => { if (value) loadMore() })
watch(() => props.refreshKey, () => { if (opened.value && !sending.value) loadMore() })
watch(() => [props.projectId, props.versionId, props.issueId], () => {
  generation++; controller?.abort(); submitController?.abort()
  rows.value = []; form.content = ''; error.value = ''; submitError.value = ''; hasMore.value = false; cursor.value = null
  loading.value = false; sending.value = false; idempotency.reset(); formRef.value?.clearValidate()
  if (opened.value) loadMore()
})
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort(); submitController?.abort() })
defineExpose({ dirty, sending })
</script>

<template>
  <section class="issue-comments" aria-label="反馈评论">
    <el-button text type="primary" size="small" :aria-expanded="opened" @click="opened = !opened">{{ opened ? '收起评论' : '查看 / 添加评论' }}</el-button>
    <template v-if="opened">
      <el-skeleton v-if="loading && !rows.length" :rows="2" animated />
      <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button text @click="loadMore()">重新加载</el-button></el-alert>
      <el-text v-else-if="!rows.length && !loading" type="info" size="small">暂无评论，可以在下面记录补充问题。</el-text>
      <article v-for="item in rows" :key="item.commentId" class="comment-row">
        <header><strong>{{ item.authorName }}</strong><time>{{ formatVersionDateTime(item.createTime) }}</time></header>
        <p>{{ item.content }}</p>
      </article>
      <el-button v-if="hasMore" text size="small" :loading="loading" @click="loadMore(true)">更早评论</el-button>
      <el-form v-if="canComment" ref="formRef" :model="form" :rules="rules" label-position="top" class="comment-form">
        <el-form-item prop="content" label="追加评论">
          <el-input v-model="form.content" type="textarea" :rows="2" maxlength="2000" show-word-limit :disabled="sending" placeholder="记录补充问题或沟通结论" />
        </el-form-item>
        <el-alert v-if="submitError" :title="submitError" type="error" :closable="false" />
        <el-button type="primary" size="small" :loading="sending" :disabled="sending" @click="submit">发送评论</el-button>
      </el-form>
      <el-text v-else type="info" size="small">当前账号仅可查看评论</el-text>
    </template>
  </section>
</template>

<style scoped>
.issue-comments { margin-top: 10px; padding-top: 6px; border-top: 1px solid var(--sg-border); }
.comment-row { padding: 8px 0; border-bottom: 1px solid var(--sg-border); }
.comment-row header { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; }.comment-row time { color: var(--sg-text-muted); }
.comment-row p { margin: 6px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; }
.comment-form { margin-top: 12px; }.comment-form :deep(.el-form-item) { margin-bottom: 12px; }
.comment-form .el-alert { margin-bottom: 8px; }
</style>
