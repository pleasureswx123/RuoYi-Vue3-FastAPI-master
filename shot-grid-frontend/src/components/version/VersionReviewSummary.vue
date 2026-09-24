<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useDetailNavigation } from '@/composables/useDetailNavigation'
import { getReviewActions, getTaskIssues } from '@/api/shot-grid/reviews'
import { useSessionStore } from '@/store/modules/session'
import { formatReviewDateTime } from '@/views/review/reviewPresentation'
import { taskVersionStatusMeta } from '@/views/task/taskPresentation'
import { tagTypeFromTone } from '@/utils/tag'

const props = defineProps({ version: { type: Object, required: true } })
const navigate = useDetailNavigation()
const session = useSessionStore()
const allowed = permission => session.permissions.includes('*:*:*') || session.permissions.includes(permission)
const canOpen = computed(() => allowed('shotgrid:reviewList:query'))
const decision = ref(null)
const issueCount = ref(null)
const loading = ref(false)
const failed = ref(false)
const status = computed(() => taskVersionStatusMeta(props.version.versionStatus))
let controller

async function load() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  decision.value = null
  issueCount.value = null
  failed.value = false
  loading.value = true
  const { versionId, taskId } = props.version
  const results = await Promise.allSettled([
    getReviewActions(versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }, { signal: request.signal }),
    allowed('shotgrid:note:list') ? getTaskIssues(taskId, {}, { signal: request.signal }) : Promise.resolve(null)
  ])
  if (request.signal.aborted || controller !== request) return
  const [actions, issues] = results
  if (actions.status === 'fulfilled') decision.value = actions.value.rows?.find(item => ['approve', 'reject', 'defer'].includes(item.actionType)) || null
  if (issues.status === 'fulfilled' && issues.value) issueCount.value = (issues.value.data || []).filter(item => Number(item.originVersionId) === Number(versionId)).length
  failed.value = results.some(item => item.status === 'rejected')
  loading.value = false
}
watch(() => props.version, load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="version-review-summary" aria-label="对应审核信息">
    <div class="summary-main">
      <strong>本版审核</strong>
      <el-tag size="small" :type="tagTypeFromTone(status.tone)">{{ status.label }}</el-tag>
      <span v-if="loading">正在加载审核信息…</span>
      <template v-else>
        <span v-if="version.versionStatus === 'pending_review'">本轮已提交，等待审核人确认</span>
        <span v-if="issueCount !== null">已发布 <b>{{ issueCount }} 条修改意见</b></span>
        <small v-if="decision">审核人 {{ decision.reviewerName || `用户 #${decision.reviewerUserId}` }} · {{ formatReviewDateTime(decision.createTime) }}</small>
      </template>
      <el-button v-if="canOpen && version.autoReviewList" class="review-link" type="primary" plain size="small" @click="navigate(`/reviews/${version.autoReviewList.reviewListId}`)">查看审核详情</el-button>
    </div>
    <p v-if="version.autoReviewList" class="review-name">{{ version.autoReviewList.reviewListName }}</p>
    <p v-else class="review-name">未关联审核单</p>
    <p v-if="decision?.reason" class="decision-reason">{{ decision.reason }}</p>
    <div v-if="failed" class="summary-error">部分审核信息加载失败 <el-button link type="primary" @click="load">重试</el-button></div>
  </section>
</template>

<style scoped>
.version-review-summary { margin-top: 12px; padding: 12px; border: 1px solid var(--sg-border); border-radius: 8px; background: var(--sg-surface-soft); }
.summary-main { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; font-size: 12px; }
.summary-main small, .review-name { color: var(--sg-text-muted); }
.summary-main b { color: var(--sg-accent); }
.review-link { margin-left: auto; }
.review-name, .decision-reason { margin: 8px 0 0; font-size: 12px; overflow-wrap: anywhere; }
.decision-reason { white-space: pre-wrap; }
.summary-error { margin-top: 8px; color: var(--el-color-danger); font-size: 12px; }
</style>
