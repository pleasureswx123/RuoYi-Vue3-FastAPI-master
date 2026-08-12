<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChatLineSquare, CircleCheck, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import {
  addNoteReply,
  addVersionNote,
  createReviewAction,
  getNoteReplies,
  getReviewActions,
  getReviewListDetail,
  getVersionNotes,
  resolveNote,
  transitionManualReviewList
} from '@/api/shot-grid/reviews'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { getVersionDetail } from '@/api/shot-grid/versions'
import VersionDetailCard from '@/components/version/VersionDetailCard.vue'
import { useSessionStore } from '@/store/modules/session'
import { createIdempotencyState } from '@/utils/idempotency'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ReviewMediaWorkspace from '@/views/review/components/ReviewMediaWorkspace.vue'
import {
  formatMediaTime,
  formatReviewDateTime,
  reviewActionMeta,
  reviewErrorState,
  reviewStatusMeta
} from './reviewPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const review = ref(null)
const version = ref(null)
const notes = ref([])
const actions = ref([])
const repliesByNote = ref({})
const loading = ref(false)
const pageError = ref(null)
const noteBusy = ref(false)
const resolvingNoteId = ref(null)
const replyingNoteId = ref(null)
const actionBusy = ref('')
const actionReason = ref('')
const manualBusy = ref('')
const activeManualVersionId = ref(null)
const selectedNote = ref(null)
const mediaWorkspace = ref(null)
const replyDrafts = reactive({})
const noteDraft = reactive({ content: '', mediaSeconds: '', annotations: null, isMandatory: false })
let pageController = null
let pageGeneration = 0
let actionIdempotency = createIdempotencyState('review-action')

const reviewListId = computed(() => assertPositiveId(route.params.reviewListId, '审核单'))
const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
const canDownload = computed(() => hasPermission('shotgrid:file:download'))
const canQueryReview = computed(() => hasPermission('shotgrid:reviewList:query'))
const canQueryVersion = computed(() => hasPermission('shotgrid:version:query'))
const canListVersions = computed(() => hasPermission('shotgrid:version:list'))
const canListNotes = computed(() => hasPermission('shotgrid:note:list'))
const canAddNote = computed(() => hasPermission('shotgrid:note:add'))
const canReply = computed(() => hasPermission('shotgrid:note:reply'))
const canResolve = computed(() => hasPermission('shotgrid:note:resolve'))
const canReview = computed(() => hasPermission('shotgrid:version:review'))
const canActivateManual = computed(() => hasPermission('shotgrid:reviewList:activate'))
const canCompleteManual = computed(() => hasPermission('shotgrid:reviewList:complete'))
const canArchiveManual = computed(() => hasPermission('shotgrid:reviewList:archive'))
const openMandatoryCount = computed(() => notes.value.filter(item => item.isMandatory && item.noteStatus === 'open').length)
const canSubmitDecision = computed(() => (
  canReview.value && review.value?.reviewStatus === 'active' && version.value?.versionStatus === 'pending_review'
))
const manualVersions = computed(() => review.value?.versions || [])

function isCurrent(controller, generation) {
  return pageController === controller && !controller.signal.aborted && pageGeneration === generation
}

async function loadReplies(noteRows, controller, generation) {
  if (!canListNotes.value || !noteRows.length) {
    repliesByNote.value = {}
    return
  }
  const settled = await Promise.allSettled(noteRows.map(item => getNoteReplies(item.noteId, {
    pageNum: 1,
    pageSize: 100,
    orderByColumn: 'createTime',
    isAsc: 'ascending'
  }, { signal: controller.signal })))
  if (!isCurrent(controller, generation)) return
  repliesByNote.value = Object.fromEntries(noteRows.map((item, index) => [
    item.noteId,
    settled[index].status === 'fulfilled' ? (settled[index].value.rows || []) : []
  ]))
}

async function loadReview() {
  pageController?.abort()
  const controller = new AbortController()
  const generation = ++pageGeneration
  pageController = controller
  loading.value = true
  pageError.value = null
  if (!canQueryReview.value || !canQueryVersion.value) {
    loading.value = false
    pageError.value = reviewErrorState({ httpStatus: 403, message: '当前账号没有审核单或版本详情权限' })
    return
  }
  try {
    const detailResponse = await getReviewListDetail(reviewListId.value, { signal: controller.signal })
    const detail = detailResponse.data
    const versionId = detail.autoVersionId || detail.version?.versionId || detail.versions?.[0]?.versionId
    if (!versionId && detail.reviewStatus !== 'draft') throw new Error('审核单未关联可审核版本')
    if (!versionId) {
      if (!isCurrent(controller, generation)) return
      review.value = detail
      version.value = null
      notes.value = []
      actions.value = []
      return
    }
    const [versionResponse, noteResponse, actionResponse] = await Promise.all([
      getVersionDetail(versionId, { signal: controller.signal }),
      canListNotes.value
        ? getVersionNotes(versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }, { signal: controller.signal })
        : Promise.resolve({ rows: [] }),
      getReviewActions(versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }, { signal: controller.signal })
    ])
    if (!isCurrent(controller, generation)) return
    review.value = detail
    version.value = versionResponse.data
    activeManualVersionId.value = versionId
    selectedNote.value = null
    notes.value = noteResponse.rows || []
    actions.value = actionResponse.rows || []
    await loadReplies(notes.value, controller, generation)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
      pageError.value = reviewErrorState(error, '审核单加载失败')
    }
  } finally {
    if (isCurrent(controller, generation)) loading.value = false
  }
}

async function selectManualVersion(item) {
  if (Number(item.versionId) === Number(version.value?.versionId)) return
  loading.value = true
  try {
    const [versionResponse, noteResponse, actionResponse] = await Promise.all([
      getVersionDetail(item.versionId),
      canListNotes.value ? getVersionNotes(item.versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' }) : Promise.resolve({ rows: [] }),
      getReviewActions(item.versionId, { pageNum: 1, pageSize: 100, orderByColumn: 'createTime', isAsc: 'descending' })
    ])
    version.value = versionResponse.data
    activeManualVersionId.value = item.versionId
    notes.value = noteResponse.rows || []
    actions.value = actionResponse.rows || []
    repliesByNote.value = {}
    selectedNote.value = null
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '切换审核版本失败').message)
  } finally { loading.value = false }
}

async function transitionManual(action) {
  manualBusy.value = action
  try {
    await transitionManualReviewList(review.value.reviewListId, action, { lockVersion: review.value.lockVersion })
    ElMessage.success(action === 'activate' ? '审核单已激活' : action === 'complete' ? '审核单已完成' : '审核单已归档')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '审核单状态更新失败').message)
  } finally { manualBusy.value = '' }
}

async function submitNote() {
  const content = noteDraft.content.trim()
  if (!content) {
    ElMessage.warning('请填写审核意见')
    return
  }
  const seconds = noteDraft.mediaSeconds === '' ? null : Number(noteDraft.mediaSeconds)
  if (seconds !== null && (!Number.isFinite(seconds) || seconds < 0)) {
    ElMessage.warning('时间点必须是大于等于 0 的秒数')
    return
  }
  noteBusy.value = true
  try {
    await addVersionNote(version.value.versionId, {
      content,
      mediaTimeMs: seconds === null ? null : Math.round(seconds * 1000),
      annotations: noteDraft.annotations,
      isMandatory: noteDraft.isMandatory
    })
    Object.assign(noteDraft, { content: '', mediaSeconds: '', annotations: null, isMandatory: false })
    mediaWorkspace.value?.clearDraft()
    ElMessage.success('审核意见已添加')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '添加意见失败').message)
  } finally {
    noteBusy.value = false
  }
}

function captureMediaTime(milliseconds) {
  noteDraft.mediaSeconds = (Number(milliseconds) / 1000).toFixed(3).replace(/\.000$/, '')
}

function updateAnnotations(annotations) {
  noteDraft.annotations = annotations
}

function focusNote(note) {
  selectedNote.value = note
  mediaWorkspace.value?.seekToNote()
}

function openResubmission() {
  router.push(`/tasks/${review.value.taskId}#version-workspace`)
}

async function submitReply(note) {
  const content = String(replyDrafts[note.noteId] || '').trim()
  if (!content) {
    ElMessage.warning('请填写回复内容')
    return
  }
  replyingNoteId.value = note.noteId
  try {
    await addNoteReply(note.noteId, { content })
    replyDrafts[note.noteId] = ''
    ElMessage.success('回复已添加')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '回复失败').message)
  } finally {
    replyingNoteId.value = null
  }
}

async function markResolved(note) {
  resolvingNoteId.value = note.noteId
  try {
    await resolveNote(note.noteId)
    ElMessage.success('意见已解决')
    await loadReview()
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '解决意见失败').message)
  } finally {
    resolvingNoteId.value = null
  }
}

async function submitDecision(actionType) {
  if (!canSubmitDecision.value) return
  const reason = actionReason.value.trim()
  if (actionType === 'approve' && openMandatoryCount.value) {
    ElMessage.warning(`仍有 ${openMandatoryCount.value} 条必改意见未解决，暂不能通过`)
    return
  }
  if (actionType === 'reject' && !reason) {
    ElMessage.warning('退回修改时请填写原因')
    return
  }
  const payload = {
    actionType,
    reason: reason || null,
    lockVersion: version.value.lockVersion
  }
  const context = { reviewListId: reviewListId.value, versionId: version.value.versionId, ...payload }
  actionBusy.value = actionType
  try {
    await createReviewAction(version.value.versionId, payload, actionIdempotency.forPayload(context))
    actionIdempotency.reset()
    actionReason.value = ''
    ElMessage.success(`${reviewActionMeta(actionType).label}已记录`)
    await loadReview()
  } catch (error) {
    const state = reviewErrorState(error, '审核决定提交失败')
    ElMessage.error(state.status === 409 ? `${state.message}，页面正在刷新` : state.message)
    if (state.status === 409) await loadReview()
  } finally {
    actionBusy.value = ''
  }
}

onMounted(loadReview)
onBeforeUnmount(() => {
  pageGeneration += 1
  pageController?.abort()
})
</script>

<template>
  <section class="sg-page review-detail-page">
    <header class="sg-page-heading">
      <div class="review-detail-heading">
        <el-button circle :icon="ArrowLeft" aria-label="返回审核列表" @click="router.push('/reviews')" />
        <div><p class="sg-eyebrow">REVIEW DETAIL</p><h2 class="sg-page-title">{{ review?.reviewListName || '审核单详情' }}</h2><p class="sg-page-description">审核动作与意见固定绑定当前版本，已提交历史不会覆盖。</p></div>
      </div>
      <div class="heading-actions"><span v-if="review" class="review-state" :data-tone="reviewStatusMeta(review.reviewStatus).tone">{{ reviewStatusMeta(review.reviewStatus).label }}</span><el-button :icon="Refresh" :loading="loading" @click="loadReview">刷新</el-button></div>
    </header>

    <ProjectStatePanel v-if="pageError" :title="pageError.title" :message="pageError.message" :retryable="pageError.retryable" @retry="loadReview" />
    <div v-else-if="loading && !version" class="review-detail-loading" role="status">正在加载审核内容…</div>
    <template v-else-if="review">
      <section class="review-context">
        <div><span>审核模式</span><strong>{{ review.reviewMode === 'auto_single' ? '自动单版本审核' : '人工批量审核' }}</strong></div>
        <div><span>审核日期</span><strong>{{ formatReviewDateTime(review.reviewDate) }}</strong></div>
        <div><span>关联任务</span><strong>{{ version?.taskId ? `#${version.taskId}` : '批量队列' }}</strong></div>
        <div><span>未解决必改</span><strong :class="{ danger: openMandatoryCount }">{{ openMandatoryCount }}</strong></div>
      </section>

      <section v-if="review.reviewMode === 'manual_batch'" class="manual-strip">
        <header><div><p class="sg-eyebrow">BATCH QUEUE</p><h3>审核版本队列</h3></div><div><el-button v-if="review.reviewStatus === 'draft' && canActivateManual" type="primary" :loading="manualBusy === 'activate'" @click="transitionManual('activate')">激活审核单</el-button><el-button v-if="review.reviewStatus === 'active' && canCompleteManual" type="success" :loading="manualBusy === 'complete'" @click="transitionManual('complete')">完成审核单</el-button><el-button v-if="review.reviewStatus !== 'archived' && canArchiveManual" :loading="manualBusy === 'archive'" @click="transitionManual('archive')">归档</el-button></div></header>
        <div v-if="manualVersions.length" class="manual-version-list"><el-button v-for="item in manualVersions" :key="item.versionId" :type="Number(activeManualVersionId) === Number(item.versionId) ? 'primary' : 'default'" @click="selectManualVersion(item)">{{ item.versionNumber }} · 任务 #{{ item.taskId }}</el-button></div><p v-else class="empty-block">当前草稿还没有版本，请返回审核列表添加版本。</p>
      </section>

      <div v-if="version" class="review-detail-grid">
        <main class="review-main">
          <ReviewMediaWorkspace ref="mediaWorkspace" :version="version" :selected-note="selectedNote" :can-download="canDownload" :can-compare="canListVersions" :can-annotate="canAddNote" @capture-time="captureMediaTime" @annotations-change="updateAnnotations" />

          <VersionDetailCard :version="version" :can-download="canDownload" />

          <section class="decision-panel">
            <header><div><p class="sg-eyebrow">DECISION</p><h3>审核决定</h3></div><small v-if="!canSubmitDecision">当前版本已经完成决定，或你没有审核权限。</small></header>
            <textarea v-model="actionReason" rows="3" maxlength="1000" :disabled="!canSubmitDecision" placeholder="填写审核说明；退回修改时必填" />
            <div class="decision-actions">
              <el-button type="success" :loading="actionBusy === 'approve'" :disabled="!canSubmitDecision || openMandatoryCount > 0 || Boolean(actionBusy)" @click="submitDecision('approve')">确认通过</el-button>
              <el-button type="danger" plain :loading="actionBusy === 'reject'" :disabled="!canSubmitDecision || Boolean(actionBusy)" @click="submitDecision('reject')">退回修改</el-button>
              <el-button :loading="actionBusy === 'defer'" :disabled="!canSubmitDecision || Boolean(actionBusy)" @click="submitDecision('defer')">稍后决定</el-button>
            </div>
            <el-button v-if="version.versionStatus === 'rejected'" class="resubmit-link" type="primary" plain @click="openResubmission">前往任务提交修订版本</el-button>
            <p v-if="openMandatoryCount" class="decision-warning"><el-icon><WarningFilled /></el-icon>解决全部必改意见后才能确认通过。</p>
          </section>

          <section class="action-history">
            <header><div><p class="sg-eyebrow">HISTORY</p><h3>审核动作记录</h3></div><span>{{ actions.length }} 条</span></header>
            <div v-if="actions.length" class="action-list">
              <article v-for="item in actions" :key="item.actionId"><span class="action-dot" :data-tone="reviewActionMeta(item.actionType).tone" /><div><strong>{{ reviewActionMeta(item.actionType).label }}</strong><p>{{ item.reason || '未填写说明' }}</p><small>{{ item.reviewerName || `用户 #${item.reviewerUserId}` }} · {{ formatReviewDateTime(item.createTime) }} · {{ item.fromStatus }} → {{ item.toStatus }}</small></div></article>
            </div>
            <p v-else class="empty-block">尚无审核动作。</p>
          </section>
        </main>

        <aside class="notes-panel">
          <header><div><p class="sg-eyebrow">NOTES</p><h3>审核意见</h3></div><span>{{ notes.length }} 条</span></header>
          <form v-if="canAddNote" class="note-compose" @submit.prevent="submitNote">
            <textarea v-model="noteDraft.content" rows="4" maxlength="2000" placeholder="指出需要调整的内容…" />
            <div><label><span>时间点（秒，可选）</span><input v-model="noteDraft.mediaSeconds" type="number" min="0" step="0.001" placeholder="例如 12.5" /></label><el-checkbox v-model="noteDraft.isMandatory">标记为必改</el-checkbox></div>
            <el-button native-type="submit" type="primary" :loading="noteBusy">添加意见</el-button>
          </form>
          <p v-else-if="!canListNotes" class="permission-hint">你没有查看审核意见的权限。</p>

          <div v-if="canListNotes && notes.length" class="note-list">
            <article v-for="note in notes" :key="note.noteId" class="note-card" :class="{ 'is-selected': selectedNote?.noteId === note.noteId }" :data-status="note.noteStatus" @click="focusNote(note)">
              <header><div><strong>{{ note.reviewerName || `用户 #${note.reviewerUserId}` }}</strong><span v-if="note.isMandatory" class="mandatory-chip">必改</span><span v-if="note.mediaTimeMs !== null && note.mediaTimeMs !== undefined" class="time-chip">{{ formatMediaTime(note.mediaTimeMs) }}</span></div><span class="note-status">{{ note.noteStatus === 'resolved' ? '已解决' : '待处理' }}</span></header>
              <p>{{ note.content }}</p>
              <small>{{ formatReviewDateTime(note.createTime) }}</small>
              <div v-if="repliesByNote[note.noteId]?.length" class="reply-list"><div v-for="reply in repliesByNote[note.noteId]" :key="reply.replyId"><el-icon><ChatLineSquare /></el-icon><p><strong>{{ reply.replyUserName || `用户 #${reply.replyUserId}` }}</strong>{{ reply.content }}<small>{{ formatReviewDateTime(reply.createTime) }}</small></p></div></div>
              <form v-if="canReply" class="reply-compose" @submit.prevent="submitReply(note)"><input v-model="replyDrafts[note.noteId]" maxlength="1000" placeholder="回复这条意见…" /><el-button native-type="submit" size="small" :loading="replyingNoteId === note.noteId">回复</el-button></form>
              <el-button v-if="canResolve && note.noteStatus === 'open'" class="resolve-button" text type="success" :icon="CircleCheck" :loading="resolvingNoteId === note.noteId" @click="markResolved(note)">标记已解决</el-button>
            </article>
          </div>
          <p v-else-if="canListNotes" class="empty-block">当前版本还没有审核意见。</p>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.manual-strip{display:grid;gap:14px;padding:18px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.manual-strip>header{display:flex;gap:14px;align-items:center;justify-content:space-between}.manual-strip h3{margin:3px 0 0;font-size:16px}.manual-strip>header>div:last-child,.manual-version-list{display:flex;gap:8px;flex-wrap:wrap}
.review-detail-page{display:grid;gap:18px}.review-detail-heading,.heading-actions{display:flex;gap:13px;align-items:center}.review-state{padding:6px 10px;color:var(--sg-text-secondary);font-size:11px;background:rgba(255,255,255,.05);border-radius:999px}.review-state[data-tone=warning]{color:var(--sg-accent);background:var(--sg-accent-soft)}.review-state[data-tone=success]{color:var(--sg-success);background:rgba(98,212,155,.1)}.review-detail-loading{display:grid;min-height:320px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg);place-items:center}.review-context{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.review-context>div{display:grid;gap:6px;padding:13px 15px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:10px}.review-context span{color:var(--sg-text-muted);font-size:10px}.review-context strong{font-size:12px}.review-context strong.danger{color:var(--sg-danger)}.review-detail-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(330px,.75fr);gap:18px;align-items:start}.review-main{display:grid;gap:18px}.decision-panel,.action-history,.notes-panel{padding:20px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.decision-panel>header,.action-history>header,.notes-panel>header{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.decision-panel h3,.action-history h3,.notes-panel h3{margin:3px 0 0;font-size:16px}.decision-panel header small,.action-history header>span,.notes-panel header>span{color:var(--sg-text-muted);font-size:10px}.decision-panel textarea,.note-compose textarea,.note-compose input,.reply-compose input{box-sizing:border-box;width:100%;color:var(--sg-text);font:inherit;background:rgba(255,255,255,.03);border:1px solid var(--sg-border-strong);border-radius:9px;outline:none}.decision-panel textarea,.note-compose textarea{padding:11px;margin-top:15px;resize:vertical}.decision-panel textarea:focus,.note-compose textarea:focus,.note-compose input:focus,.reply-compose input:focus{border-color:var(--sg-accent)}.decision-actions{display:flex;gap:9px;margin-top:10px;flex-wrap:wrap}.resubmit-link{margin-top:10px}.decision-warning{display:flex;gap:6px;align-items:center;margin:10px 0 0;color:var(--sg-danger);font-size:10px}.action-list{display:grid;gap:12px;margin-top:15px}.action-list article{display:grid;grid-template-columns:auto 1fr;gap:10px}.action-dot{width:9px;height:9px;margin-top:4px;background:var(--sg-text-muted);border-radius:50%}.action-dot[data-tone=success]{background:var(--sg-success)}.action-dot[data-tone=danger]{background:var(--sg-danger)}.action-dot[data-tone=warning]{background:var(--sg-accent)}.action-list strong,.action-list p,.action-list small{display:block;margin:0}.action-list p{margin:4px 0;color:var(--sg-text-secondary);font-size:11px}.action-list small{color:var(--sg-text-muted);font-size:9px}.notes-panel{position:sticky;top:18px}.note-compose{display:grid;gap:10px;padding:12px;margin-top:15px;background:rgba(0,0,0,.12);border-radius:10px}.note-compose textarea{margin-top:0}.note-compose>div{display:flex;gap:12px;align-items:end;justify-content:space-between}.note-compose label{display:grid;min-width:0;gap:5px;color:var(--sg-text-muted);font-size:9px}.note-compose input{height:34px;padding:0 9px}.note-compose>.el-button{justify-self:end}.note-list{display:grid;gap:11px;margin-top:15px}.note-card{padding:13px;cursor:pointer;background:rgba(255,255,255,.025);border:1px solid var(--sg-border);border-radius:10px}.note-card.is-selected{border-color:var(--sg-accent);box-shadow:0 0 0 1px var(--sg-accent-soft)}.note-card[data-status=resolved]{opacity:.72}.note-card>header{display:flex;gap:8px;align-items:center;justify-content:space-between}.note-card>header>div{display:flex;gap:6px;align-items:center}.note-card strong{font-size:11px}.mandatory-chip,.time-chip,.note-status{padding:3px 6px;font-size:8px;border-radius:999px}.mandatory-chip{color:var(--sg-danger);background:rgba(244,92,92,.1)}.time-chip{color:var(--sg-accent);background:var(--sg-accent-soft)}.note-status{color:var(--sg-text-muted);background:rgba(255,255,255,.05)}.note-card>p{margin:10px 0 7px;color:var(--sg-text-secondary);font-size:11px;line-height:1.65;white-space:pre-wrap}.note-card>small{color:var(--sg-text-muted);font-size:9px}.reply-list{display:grid;gap:7px;padding:10px;margin-top:10px;background:rgba(0,0,0,.13);border-radius:8px}.reply-list>div{display:grid;grid-template-columns:auto 1fr;gap:7px;color:var(--sg-text-muted)}.reply-list p{display:grid;gap:3px;margin:0;color:var(--sg-text-secondary);font-size:10px}.reply-list small{color:var(--sg-text-muted);font-size:8px}.reply-compose{display:grid;grid-template-columns:1fr auto;gap:7px;margin-top:10px}.reply-compose input{height:32px;padding:0 9px;font-size:10px}.resolve-button{margin-top:6px}.empty-block,.permission-hint{padding:24px 8px;margin:12px 0 0;color:var(--sg-text-muted);font-size:11px;text-align:center}.permission-hint{color:var(--sg-danger)}@media(max-width:1050px){.review-detail-grid{grid-template-columns:1fr}.notes-panel{position:static}}@media(max-width:700px){.review-context{grid-template-columns:1fr 1fr}.sg-page-heading{align-items:flex-start}.heading-actions{align-items:flex-end;flex-direction:column}.note-compose>div{align-items:flex-start;flex-direction:column}}
</style>
