<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/collapse-item/style/css'
import { getVersionReviewContext, submitBatchFeedback } from '@/api/shot-grid/reviews'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'
import { reviewErrorState } from '@/views/review/reviewPresentation'

const emit = defineEmits(['saved', 'active-change', 'review'])
const visible = ref(false)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const formRef = ref(null)
const issueTableRef = ref(null)
const workspaceRef = ref(null)
const stageTitleRef = ref(null)
const projectId = ref(null)
const action = ref('reject')
const step = ref(0)
const navigating = ref(false)
const activeVersionId = ref(null)
const { referenceAttachments, addReferenceFile, removeReferenceFile, resetReferenceAttachments, uploadPendingReferenceFiles } = useReviewReferenceAttachments({
  canEdit: () => !disabled.value,
  isCurrent: () => current(generation)
})
const form = reactive({ content: '', referenceFiles: referenceAttachments, targets: [], reviewReady: '', feedbackReady: '', bulkComment: '' })
const showReviewErrors = ref(false)
const showFeedbackErrors = ref(false)
const bulkEditing = ref(false)
const selectedIssues = ref([])
const expandedDrafts = ref([])
const activeIndex = computed(() => form.targets.findIndex(row => row.versionId === activeVersionId.value))
const activeTarget = computed(() => form.targets[activeIndex.value])
const issueCount = computed(() => form.targets.reduce((sum, row) => sum + row.issues.length, 0))
const remainingCount = computed(() => form.targets.reduce((sum, row) => sum + row.issues.length - reviewedCount(row), 0))
const draftTargets = computed(() => form.targets.filter(row => row.drafts.length))
const unconfirmedDraftCount = computed(() => draftTargets.value.filter(row => !row.draftsConfirmed).length)
const disabled = computed(() => loading.value || busy.value || navigating.value || Boolean(error.value))
const stageTitles = ['先确认已有问题的状态', '再补充本次反馈', '核对后统一发送']
const stageDescriptions = [
  '制作人的处理说明供你参考；请逐条确认“已解决”或“仍需修改”，完成后再补充新反馈。',
  '核对已有草稿，再按需补充适用于全部所选镜头的新意见。已有待修改问题时，新反馈可不填。',
  '请核对每个镜头的复核结论和意见。确认后发送给制作人，并将这些任务统一退回修改。'
]
const rules = {
  content: [{ validator: (_rule, value, done) => {
    if (referenceAttachments.value.length && !value.trim()) return done(new Error('添加参考内容后，请填写共同反馈说明'))
    if (action.value === 'save_draft' && !value.trim()) return done(new Error('请填写要保存的共同反馈'))
    done()
  }, trigger: 'blur' }],
  reviewReady: [{ validator: (_rule, _value, done) => {
    done(remainingCount.value ? new Error('还有 ' + remainingCount.value + ' 条问题未完成复核，请先补齐结论和修改原因') : undefined)
  } }],
  feedbackReady: [{ validator: (_rule, _value, done) => {
    const row = form.targets.find(target => feedbackError(target))
    done(row ? new Error(row.label + '：' + feedbackError(row)) : undefined)
  } }],
  bulkComment: [{ required: true, whitespace: true, message: '请填写所选问题仍需修改的原因', trigger: 'blur' }]
}
let generation = 0
let controller = null
let validateContext = () => true
let disposed = false

function invalidate() { generation += 1; controller?.abort() }
watch(visible, value => {
  emit('active-change', value)
  if (!value) { invalidate(); resetReferenceAttachments() }
})
onBeforeUnmount(() => { disposed = true; invalidate(); emit('active-change', false) })
const current = token => !disposed && visible.value && generation === token && validateContext()

async function open(project, shots, isCurrent = () => true) {
  if (busy.value || visible.value) return
  invalidate()
  const token = generation
  controller = new AbortController()
  validateContext = isCurrent
  projectId.value = project
  form.content = ''
  resetReferenceAttachments()
  step.value = 0
  action.value = 'reject'
  showReviewErrors.value = false
  showFeedbackErrors.value = false
  clearSelection()
  expandedDrafts.value = []
  form.targets = shots.map(shot => ({
    versionId: shot.latestVersion.versionId,
    label: [shot.episodeCode, shot.sceneCode, shot.shotCode].filter(Boolean).join(' / ') + ' · ' + shot.latestVersion.versionNumber,
    shot, lockVersion: null, issues: [], drafts: [], currentIssues: [], draftsConfirmed: false, loaded: false
  }))
  activeVersionId.value = form.targets[0]?.versionId ?? null
  error.value = ''
  visible.value = true
  loading.value = true
  // 限制并发读取；结果只写回打开时的版本和项目。
  const queue = [...form.targets]
  try {
    await Promise.all(Array.from({ length: Math.min(4, queue.length) }, async () => {
      while (queue.length && current(token)) {
        const row = queue.shift()
        const { data } = await getVersionReviewContext(row.versionId, { signal: controller.signal })
        if (!current(token)) return
        const version = data?.currentVersion
        if (version?.versionId !== row.versionId || version.versionStatus !== 'pending_review' ||
            !Number.isSafeInteger(version.lockVersion) || version.lockVersion < 0) {
          throw new Error(row.label + ' 状态已变化，请关闭并刷新后重新选择')
        }
        row.lockVersion = version.lockVersion
        row.issues = (data.carriedIssues || []).map(issue => ({ ...issue, result: '', comment: '' }))
        row.drafts = data.currentVersionDrafts || []
        row.currentIssues = data.currentVersionIssues || []
        row.loaded = true
      }
    }))
    if (current(token) && form.targets.some(row => !row.loaded)) throw new Error('审核上下文未加载完整，请重新打开')
    if (current(token)) {
      activeVersionId.value = form.targets.find(row => row.issues.length)?.versionId ?? activeVersionId.value
      expandedDrafts.value = draftTargets.value.length ? [draftTargets.value[0].versionId] : []
    }
  } catch (failure) {
    if (current(token)) error.value = reviewErrorState(failure, '审核信息加载失败，请关闭后重试').message
  } finally {
    if (!disposed && generation === token) {
      loading.value = false
      if (!validateContext()) error.value = '项目或所选任务已变化，请关闭并重新选择'
    }
  }
  await nextTick()
  if (current(token)) formRef.value?.clearValidate()
}
function reviewedCount(row) {
  return row.issues.filter(issue => !issueError(issue)).length
}
function issueError(issue) {
  if (!['resolved', 'still_present'].includes(issue.result)) return '请选择复核结论'
  return issue.result === 'still_present' && !issue.comment.trim() ? '请填写仍需修改的具体原因' : ''
}
function feedbackError(row) {
  if (row.drafts.length && !row.draftsConfirmed) return '请核对并确认发送已有草稿'
  if (!form.content.trim() && !row.drafts.length && !row.currentIssues.length && !row.issues.some(issue => issue.result === 'still_present')) {
    return '无待修改内容；如无新意见，请关闭弹窗，取消选择此镜头后转单镜头审核通过'
  }
  return ''
}
function resultCount(row, result) { return row.issues.filter(issue => issue.result === result).length }
function clearSelection() {
  issueTableRef.value?.clearSelection()
  selectedIssues.value = []
  bulkEditing.value = false
  form.bulkComment = ''
  formRef.value?.clearValidate('bulkComment')
}
async function selectTarget(versionId) {
  if (busy.value || loading.value) return
  clearSelection()
  activeVersionId.value = Number(versionId)
  await nextTick()
  workspaceRef.value?.scrollTo?.({ top: 0 })
}
async function locateIssue(row, issue) {
  await selectTarget(row.versionId)
  await nextTick()
  formRef.value?.scrollToField(['targets', String(activeIndex.value), 'issues', String(row.issues.indexOf(issue)), issue.result === 'still_present' ? 'comment' : 'result'])
  const input = issue.result === 'still_present' ? 'textarea' : 'input'
  workspaceRef.value?.querySelector(`[data-issue-id="${issue.issueId}"] ${input}`)?.focus({ preventScroll: true })
}
async function nextUnreviewed() {
  const targets = [...form.targets.slice(activeIndex.value + 1), ...form.targets.slice(0, activeIndex.value + 1)]
  const row = targets.find(target => target.issues.some(issue => issueError(issue)))
  if (row) await locateIssue(row, row.issues.find(issue => issueError(issue)))
}
async function changeStep(value) {
  clearSelection()
  step.value = value
  action.value = 'reject'
  formRef.value?.clearValidate()
  await nextTick()
  stageTitleRef.value?.focus({ preventScroll: true })
}
async function locateFeedback(row) {
  if (row.drafts.length && !row.draftsConfirmed) {
    if (!expandedDrafts.value.includes(row.versionId)) expandedDrafts.value.push(row.versionId)
    await nextTick()
    formRef.value?.scrollToField(['targets', String(form.targets.indexOf(row)), 'draftsConfirmed'])
  } else {
    formRef.value?.scrollToField('content')
  }
}
async function advance() {
  if (disabled.value || !form.targets.length) return
  navigating.value = true
  try {
    action.value = 'reject'
    if (step.value === 0) {
      showReviewErrors.value = true
      if (!await formRef.value?.validateField('reviewReady').catch(() => false)) {
        navigating.value = false
        const row = form.targets.find(target => target.issues.some(issue => issueError(issue)))
        if (row) await locateIssue(row, row.issues.find(issue => issueError(issue)))
        return
      }
    } else {
      showFeedbackErrors.value = true
      if (!await formRef.value?.validateField(['content', 'feedbackReady']).catch(() => false)) {
        const row = form.targets.find(target => feedbackError(target))
        if (row) await locateFeedback(row)
        else formRef.value?.scrollToField('content')
        return
      }
    }
    await changeStep(step.value + 1)
  } finally { navigating.value = false }
}
async function applyBulk(result) {
  if (disabled.value || !selectedIssues.value.length) return
  if (result === 'still_present' && !await formRef.value?.validateField('bulkComment').catch(() => false)) return
  for (const issue of selectedIssues.value) {
    issue.result = result
    issue.comment = result === 'still_present' ? form.bulkComment.trim() : ''
  }
  clearSelection()
  formRef.value?.clearValidate('reviewReady')
}
function resetContent() {
  if (disabled.value) return
  formRef.value?.resetFields(['content'])
  form.content = ''
  resetReferenceAttachments()
  action.value = 'reject'
  formRef.value?.clearValidate('content')
}
async function save(nextAction) {
  if (disabled.value || !form.targets.length) return
  if ((nextAction === 'reject' && step.value !== 2) || (nextAction === 'save_draft' && step.value !== 1)) return
  // 校验通过后再切换提交态，避免对话框重绘清除字段错误。
  navigating.value = true
  action.value = nextAction
  showReviewErrors.value = nextAction === 'reject'
  const token = generation
  const project = projectId.value
  let submitting = false
  try {
    await nextTick()
    const valid = await formRef.value?.validateField(nextAction === 'save_draft' ? 'content' : ['reviewReady', 'feedbackReady']).catch(() => false)
    if (!valid) return
    if (!current(token)) { error.value = '项目或所选任务已变化，请关闭并重新选择'; return }
    busy.value = true
    navigating.value = false
    const referenceFileIds = await uploadPendingReferenceFiles()
    if (!current(token)) return
    const payload = {
      action: nextAction, content: form.content.trim(), referenceFileIds,
      items: form.targets.map(row => ({
        versionId: row.versionId, lockVersion: row.lockVersion,
        drafts: row.drafts.map(draft => ({ draftId: draft.draftId, lockVersion: draft.lockVersion })),
        issueVerifications: nextAction === 'save_draft' ? [] : row.issues.map(issue => ({
          issueId: issue.issueId, result: issue.result, comment: issue.result === 'still_present' ? issue.comment.trim() : null
        }))
      }))
    }
    submitting = true
    await submitBatchFeedback(project, payload)
    if (!current(token)) return
    ElMessage.success(nextAction === 'save_draft'
      ? '已为 ' + form.targets.length + ' 个镜头保存共同反馈草稿，未发送，未提交复核结论'
      : '已为 ' + form.targets.length + ' 个镜头发送反馈并退回修改')
    emit('saved', { projectId: project })
    visible.value = false
  } catch (failure) {
    if (!current(token)) return
    if (!submitting) { ElMessage.error(failure?.message || '参考文件上传失败，请重试；本批反馈尚未提交'); return }
    const status = Number(failure?.httpStatus || failure?.status || failure?.response?.status)
    const message = reviewErrorState(failure, '提交失败').message
    if (status === 422) ElMessage.error(message)
    else error.value = [401, 403, 404, 409].includes(status)
      ? message + '；本批未提交，请关闭并刷新后重新核对。'
      : '提交结果尚未确认，请关闭并刷新核对草稿和任务状态，勿直接重复发送。'
  } finally { if (!disposed) { busy.value = false; navigating.value = false } }
}
defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" class="batch-feedback-dialog" title="批量反馈与复核" width="min(1180px, 96vw)" align-center append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy">
    <template #header="{ titleId, titleClass }">
      <div class="batch-feedback-heading">
        <h2 :id="titleId" :class="titleClass">批量反馈与复核</h2>
        <span class="batch-feedback-meta">已选 {{ form.targets.length }} 个镜头 · 复核结论在最终发送时提交</span>
      </div>
      <el-steps :active="step" finish-status="success" simple class="batch-feedback-steps" aria-label="批量反馈步骤">
        <el-step title="复核已有问题" />
        <el-step title="补充反馈" />
        <el-step title="确认发送" />
      </el-steps>
    </template>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div class="batch-feedback-intro">
      <h3 ref="stageTitleRef" tabindex="-1">{{ step + 1 }}. {{ stageTitles[step] }}</h3>
      <p>{{ stageDescriptions[step] }}</p>
    </div>
    <el-form ref="formRef" :model="form" :rules="rules" :scroll-into-view-options="{ block: 'nearest' }" label-position="top" :disabled="disabled" class="batch-feedback-form">
      <!-- 总体门禁始终挂载，覆盖未显示镜头和最后一步；字段错误在对应步骤定位。 -->
      <el-form-item v-show="step === 0" prop="reviewReady" class="batch-feedback-gate">
        <div class="batch-feedback-progress" aria-live="polite">
          <span v-if="loading">正在读取所选镜头的审核信息…</span>
          <template v-else>
            <span>已有问题已复核 <strong>{{ issueCount - remainingCount }} / {{ issueCount }}</strong> 条</span>
            <el-tag :type="remainingCount ? 'warning' : 'success'" size="small">{{ remainingCount ? '还差 ' + remainingCount + ' 条' : '可以进入下一步' }}</el-tag>
          </template>
        </div>
      </el-form-item>
      <el-form-item v-show="step === 1" prop="feedbackReady" class="batch-feedback-gate">
        <span aria-live="polite">{{ unconfirmedDraftCount ? '还有 ' + unconfirmedDraftCount + ' 个镜头的草稿待确认' : draftTargets.length ? '已有草稿已核对 · 请按需补充新意见' : '无已有草稿 · 请按需补充新意见' }}</span>
      </el-form-item>
      <div v-if="step === 0" v-loading="loading" class="batch-feedback-review">
        <nav class="batch-feedback-nav" aria-label="镜头复核导航">
          <el-menu :default-active="String(activeVersionId)" @select="selectTarget">
            <el-menu-item v-for="row in form.targets" :key="row.versionId" :index="String(row.versionId)" :disabled="busy || loading || navigating">
              <span class="batch-feedback-nav__label">{{ row.label }}</span>
              <el-tag size="small" :type="!row.loaded ? 'info' : reviewedCount(row) < row.issues.length ? 'warning' : 'success'">
                {{ !row.loaded ? '加载中' : !row.issues.length ? '无需复核' : reviewedCount(row) < row.issues.length ? '待复核 ' + (row.issues.length - reviewedCount(row)) + ' 条' : '复核完成' }}
              </el-tag>
            </el-menu-item>
          </el-menu>
        </nav>
        <section v-if="activeTarget" class="batch-feedback-review__detail" aria-label="当前镜头问题">
          <div class="batch-feedback-workspace-heading">
            <div><strong>{{ activeTarget.label }}</strong><p class="batch-feedback-meta">当前镜头：{{ reviewedCount(activeTarget) }} / {{ activeTarget.issues.length }} 条已复核</p></div>
            <el-button v-if="activeTarget.shot.canInspect" :disabled="disabled" link type="primary" @click="emit('review', activeTarget.shot)">查看当前版本画面</el-button>
          </div>
          <div v-if="selectedIssues.length" class="batch-feedback-bulk">
            <div class="batch-feedback-actions">
              <strong>已选当前镜头 {{ selectedIssues.length }} 条问题</strong>
              <el-button size="small" :disabled="disabled" @click="applyBulk('resolved')">批量标记已解决</el-button>
              <el-button size="small" :disabled="disabled" @click="bulkEditing = true">批量标记仍需修改</el-button>
              <el-button size="small" link :disabled="disabled" @click="clearSelection">取消选择</el-button>
            </div>
            <div v-if="bulkEditing" class="batch-feedback-bulk__reason">
              <el-form-item label="所选问题仍需修改的共同原因" prop="bulkComment">
                <el-input v-model="form.bulkComment" maxlength="1000" placeholder="仅应用到当前勾选的问题" />
              </el-form-item>
              <el-button :disabled="disabled" @click="applyBulk('still_present')">应用修改原因</el-button>
            </div>
          </div>
          <div ref="workspaceRef" class="batch-feedback-scroll batch-feedback-issues">
            <el-table v-if="activeTarget.issues.length" :key="activeVersionId" ref="issueTableRef" :data="activeTarget.issues" row-key="issueId" @selection-change="rows => { selectedIssues = rows }">
              <el-table-column type="selection" width="42" :selectable="() => !disabled" />
              <el-table-column label="原问题与制作人说明" min-width="240">
                <template #default="{ row: issue }">
                  <div class="batch-feedback-meta">#{{ issue.issueId }} · {{ issue.originVersionNumber }} · {{ issue.originCandidateId ? '文件反馈' : '整体反馈' }}</div>
                  <div class="batch-feedback-text">{{ issue.content || '画面标注问题' }}</div>
                  <ReviewReferenceFiles v-if="issue.referenceFiles?.length" :files="issue.referenceFiles" compact />
                  <div class="batch-feedback-response"><span class="batch-feedback-meta">制作人处理说明</span><p>{{ issue.currentVersionResponse?.responseText || '未填写处理说明' }}</p></div>
                  <el-button v-if="activeTarget.shot.canInspect && (issue.annotations || issue.mediaTimeMs != null)" link type="primary" :disabled="disabled" @click="emit('review', activeTarget.shot)">查看画面与标注</el-button>
                </template>
              </el-table-column>
              <el-table-column label="你的复核结论" min-width="245">
                <template #default="{ row: issue, $index }">
                  <div :data-issue-id="issue.issueId">
                    <el-form-item :prop="['targets', String(activeIndex), 'issues', String($index), 'result']" :error="showReviewErrors && !issue.result ? '请选择复核结论' : ''">
                      <el-radio-group v-model="issue.result" :aria-label="'问题 ' + issue.issueId + ' 的复核结论'" :disabled="disabled" @change="value => { if (value === 'resolved') issue.comment = '' }">
                        <el-radio-button value="resolved">已解决</el-radio-button>
                        <el-radio-button value="still_present">仍需修改</el-radio-button>
                      </el-radio-group>
                    </el-form-item>
                    <el-form-item v-if="issue.result === 'still_present'" label="仍需修改的原因" :prop="['targets', String(activeIndex), 'issues', String($index), 'comment']" :error="showReviewErrors && !issue.comment.trim() ? '请填写仍需修改的具体原因' : ''">
                      <el-input v-model="issue.comment" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="指出仍未解决的部分，方便制作人继续修改" />
                    </el-form-item>
                    <el-text v-else-if="!issue.result && !showReviewErrors" type="info" size="small">尚未复核，请选择结论</el-text>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else-if="!loading" :image-size="72" description="此镜头没有历史问题，无需复核" />
          </div>
          <div class="batch-feedback-next-target">
            <el-text size="small" type="info">切换镜头会保留已填写的复核结论</el-text>
            <el-button :disabled="disabled || !remainingCount" @click="nextUnreviewed">下一个未复核镜头</el-button>
          </div>
        </section>
        <el-empty v-else description="没有可复核的镜头" />
      </div>
      <div v-else-if="step === 1" class="batch-feedback-scroll batch-feedback-feedback">
        <section v-if="draftTargets.length" class="batch-feedback-section">
          <h4>已有草稿 · 发送前请核对</h4>
          <p class="batch-feedback-meta">这些是尚未发出的意见，将随本次反馈一并发送；请逐个镜头确认。</p>
          <el-collapse v-model="expandedDrafts">
            <el-collapse-item v-for="row in draftTargets" :key="row.versionId" :name="row.versionId">
              <template #title><span class="batch-feedback-collapse-title">{{ row.label }} · {{ row.drafts.length }} 条草稿 <el-tag size="small" :type="row.draftsConfirmed ? 'success' : 'warning'">{{ row.draftsConfirmed ? '已确认发送' : '待确认' }}</el-tag></span></template>
              <div v-for="draft in row.drafts" :key="draft.draftId" class="batch-feedback-draft">
                <div class="batch-feedback-meta">{{ draft.reviewerName || '审核人' }} · {{ draft.candidateId ? '文件反馈 #' + draft.candidateId : '整体反馈' }}</div>
                <div class="batch-feedback-text">{{ draft.content || '画面标注问题' }}</div>
                <ReviewReferenceFiles v-if="draft.referenceFiles?.length" :files="draft.referenceFiles" compact />
                <el-button v-if="row.shot.canInspect && (draft.annotations || draft.mediaTimeMs != null)" :disabled="disabled" link type="primary" @click="emit('review', row.shot)">查看画面与标注</el-button>
              </div>
              <el-form-item :prop="['targets', String(form.targets.indexOf(row)), 'draftsConfirmed']" :error="showFeedbackErrors && !row.draftsConfirmed ? '请确认以上草稿将一并发送' : ''">
                <el-checkbox v-model="row.draftsConfirmed">已核对，发送时一并发布以上 {{ row.drafts.length }} 条草稿</el-checkbox>
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
        </section>
        <section class="batch-feedback-section">
          <div class="batch-feedback-workspace-heading"><h4>本次新增反馈</h4><el-button link :disabled="disabled || (!form.content && !referenceAttachments.length)" @click="resetContent">清空新增反馈</el-button></div>
          <el-alert :title="'以下新增反馈将发送给全部 ' + form.targets.length + ' 个镜头'" type="info" :closable="false" show-icon />
          <el-form-item label="共同整体反馈（按需填写）" prop="content" class="batch-feedback-gap">
            <el-input v-model="form.content" type="textarea" :rows="4" maxlength="10000" show-word-limit placeholder="填写适用于全部所选镜头的新反馈；已有待修改问题时可不填" />
          </el-form-item>
          <el-form-item label="参考内容（可选）" prop="referenceFiles">
            <ReviewReferenceInput :files="referenceAttachments" :disabled="disabled" @add="addReferenceFile" @remove="removeReferenceFile" />
          </el-form-item>
          <p class="batch-feedback-meta">参考内容会随共同反馈用于全部所选镜头，添加后请填写文字说明。保存草稿会暂存文字和参考内容，不发送意见，也不保存第一步的复核结论。</p>
        </section>
        <el-alert v-for="row in form.targets.filter(target => showFeedbackErrors && feedbackError(target))" :key="row.versionId" :title="row.label + '：' + feedbackError(row)" type="warning" :closable="false" show-icon class="batch-feedback-gap" />
      </div>
      <div v-else class="batch-feedback-scroll batch-feedback-confirm">
        <el-alert title="整批提交：全部成功后统一退回修改；任一镜头校验失败，本批均不提交。" type="info" :closable="false" show-icon />
        <div v-if="form.content.trim()" class="batch-feedback-section"><h4>发送给全部 {{ form.targets.length }} 个镜头的新增反馈</h4><p class="batch-feedback-text">{{ form.content.trim() }}</p></div>
        <section v-if="referenceAttachments.length" class="batch-feedback-section"><h4>共同参考内容（{{ referenceAttachments.length }} 个）</h4><ReviewReferenceInput :files="referenceAttachments" readonly /></section>
        <el-table :data="form.targets" row-key="versionId" class="batch-feedback-gap">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="batch-feedback-preview">
                <h4>历史问题复核结论</h4>
                <p v-if="!row.issues.length" class="batch-feedback-meta">无历史问题</p>
                <div v-for="issue in row.issues" :key="issue.issueId" class="batch-feedback-draft">
                  <el-tag size="small" :type="issue.result === 'resolved' ? 'success' : 'warning'">{{ issue.result === 'resolved' ? '已解决' : '仍需修改' }}</el-tag>
                  <p class="batch-feedback-text">#{{ issue.issueId }} · {{ issue.content || '画面标注问题' }}</p>
                  <p v-if="issue.comment" class="batch-feedback-text">修改原因：{{ issue.comment }}</p>
                </div>
                <h4>将发布的已有草稿 · {{ row.drafts.length }} 条</h4>
                <div v-for="draft in row.drafts" :key="draft.draftId" class="batch-feedback-draft">
                  <p class="batch-feedback-text">{{ draft.content || '画面标注问题' }}</p>
                  <ReviewReferenceFiles v-if="draft.referenceFiles?.length" :files="draft.referenceFiles" compact />
                </div>
                <template v-if="row.currentIssues.length">
                  <h4>本轮已发布问题 · {{ row.currentIssues.length }} 条</h4>
                  <p v-for="issue in row.currentIssues" :key="issue.issueId" class="batch-feedback-text">{{ issue.content || '画面标注问题' }}</p>
                </template>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="label" label="镜头 / 版本" min-width="230" />
          <el-table-column label="已解决" width="90"><template #default="{ row }">{{ resultCount(row, 'resolved') }} 条</template></el-table-column>
          <el-table-column label="仍需修改" width="100"><template #default="{ row }">{{ resultCount(row, 'still_present') }} 条</template></el-table-column>
          <el-table-column label="待发布意见" width="115"><template #default="{ row }">{{ row.drafts.length + (form.content.trim() ? 1 : 0) }} 条</template></el-table-column>
          <el-table-column label="本轮已发布" width="115"><template #default="{ row }">{{ row.currentIssues.length }} 条</template></el-table-column>
          <el-table-column label="发送后" width="100"><template #default><el-tag type="warning" size="small">待修改</el-tag></template></el-table-column>
        </el-table>
        <p class="batch-feedback-meta">展开镜头可查看逐条意见；需要调整时，返回上一步，填写内容会保留。</p>
      </div>
    </el-form>
    <template #footer>
      <span class="batch-feedback-footer-note" aria-live="polite">{{ step === 0 && remainingCount ? '还需复核 ' + remainingCount + ' 条问题' : '关闭不会保存本次复核结论' }}</span>
      <el-button :disabled="busy || navigating" @click="visible = false">关闭</el-button>
      <el-button v-if="step > 0" :disabled="busy || navigating" @click="changeStep(step - 1)">上一步</el-button>
      <el-button v-if="step === 1" :disabled="disabled" :loading="busy && action === 'save_draft'" @click="save('save_draft')">保存新增反馈草稿</el-button>
      <el-button v-if="step < 2" type="primary" :disabled="disabled || !form.targets.length" :loading="navigating" @click="advance">{{ step === 0 ? '下一步：补充反馈' : '下一步：确认发送' }}</el-button>
      <el-button v-else type="primary" :disabled="disabled" :loading="busy && action === 'reject'" @click="save('reject')">确认发送并退回修改（{{ form.targets.length }} 个镜头）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
:global(.batch-feedback-dialog) { display: flex; flex-direction: column; height: min(800px, calc(100dvh - 48px)); margin: 24px auto; }
:global(.batch-feedback-dialog .el-dialog__header), :global(.batch-feedback-dialog .el-dialog__footer) { flex-shrink: 0; }
:global(.batch-feedback-dialog .el-dialog__body) { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
:global(.batch-feedback-dialog .el-dialog__footer) { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--el-border-color-lighter); padding-top: 16px; }
:global(.batch-feedback-dialog .el-dialog__footer .el-button + .el-button) { margin-left: 0; }
.batch-feedback-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; }
.batch-feedback-heading h2 { margin: 0; }
.batch-feedback-steps { margin-top: 18px; }
.batch-feedback-intro { padding: 14px 0 8px; }
.batch-feedback-intro h3 { margin: 0 0 6px; font-size: 16px; }
.batch-feedback-intro h3:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }
.batch-feedback-intro p, .batch-feedback-workspace-heading p { margin: 0; }
.batch-feedback-intro p { color: var(--el-text-color-secondary); line-height: 1.6; }
.batch-feedback-form { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.batch-feedback-gate { flex-shrink: 0; margin-bottom: 20px; }
.batch-feedback-progress, .batch-feedback-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.batch-feedback-review { display: grid; grid-template-columns: 250px minmax(0, 1fr); flex: 1; min-height: 0; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; overflow: hidden; }
.batch-feedback-nav { min-height: 0; overflow: auto; background: var(--el-fill-color-light); border-right: 1px solid var(--el-border-color-lighter); }
.batch-feedback-nav :deep(.el-menu) { border: 0; background: transparent; }
.batch-feedback-nav :deep(.el-menu-item) { height: auto; min-height: 82px; padding: 14px 16px; flex-direction: column; align-items: flex-start; justify-content: center; gap: 8px; line-height: 1.4; white-space: normal; }
.batch-feedback-nav :deep(.el-menu-item.is-active) { background: var(--el-color-primary-light-9); box-shadow: inset 3px 0 var(--el-color-primary); }
.batch-feedback-nav__label { overflow-wrap: anywhere; font-weight: 600; }
.batch-feedback-review__detail { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.batch-feedback-workspace-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; padding: 14px 16px; }
.batch-feedback-workspace-heading h4 { margin: 0; }
.batch-feedback-scroll { min-height: 0; overflow: auto; overscroll-behavior: contain; }
.batch-feedback-issues { flex: 1; }
.batch-feedback-issues :deep(.el-form-item) { margin-bottom: 18px; }
.batch-feedback-issues :deep(.el-form-item__label) { font-size: 12px; }
.batch-feedback-issues :deep(.el-table__cell) { vertical-align: top; padding-top: 14px; }
.batch-feedback-bulk { padding: 10px 16px; background: var(--el-color-primary-light-9); }
.batch-feedback-bulk__reason { display: flex; align-items: center; gap: 12px; }
.batch-feedback-bulk__reason .el-form-item { flex: 1; margin-top: 12px; }
.batch-feedback-next-target { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 16px; border-top: 1px solid var(--el-border-color-lighter); }
.batch-feedback-feedback, .batch-feedback-confirm { flex: 1; padding: 0 4px 16px; }
.batch-feedback-section { padding: 16px; margin-bottom: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; }
.batch-feedback-section h4 { margin: 0 0 10px; }
.batch-feedback-section > .batch-feedback-workspace-heading { padding: 0 0 10px; }
.batch-feedback-collapse-title { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; text-align: left; line-height: 1.6; padding: 8px 0; }
.batch-feedback-section :deep(.el-collapse-item__header) { min-height: 48px; height: auto; }
.batch-feedback-section :deep(.el-checkbox) { height: auto; white-space: normal; }
.batch-feedback-section :deep(.el-checkbox__label) { white-space: normal; }
.batch-feedback-gap { margin-top: 14px; }
.batch-feedback-meta, .batch-feedback-footer-note { color: var(--el-text-color-secondary); font-size: 12px; }
.batch-feedback-footer-note { margin-right: auto; }
.batch-feedback-text, .batch-feedback-response { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; }
.batch-feedback-response { padding: 10px; margin-top: 10px; background: var(--el-fill-color-light); border-radius: 4px; }
.batch-feedback-response p { margin: 4px 0 0; }
.batch-feedback-draft { border-bottom: 1px solid var(--el-border-color-lighter); padding: 10px 0; margin-bottom: 12px; }
.batch-feedback-preview { padding: 4px 20px 16px; }
@media (max-width: 760px) {
  :global(.batch-feedback-dialog) { height: calc(100dvh - 24px); margin: 12px auto; }
  .batch-feedback-review { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
  .batch-feedback-nav { max-height: 100px; border-right: 0; border-bottom: 1px solid var(--el-border-color-lighter); }
  .batch-feedback-nav :deep(.el-menu) { display: flex; }
  .batch-feedback-nav :deep(.el-menu-item) { min-width: 190px; }
  .batch-feedback-steps { padding: 12px 8px; }
  .batch-feedback-steps :deep(.el-step__title) { font-size: 12px; }
  .batch-feedback-footer-note { flex-basis: 100%; }
}
</style>
