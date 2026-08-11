<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/modules/user'
import ProtectedImagePreview from '@/components/media/ProtectedImagePreview.vue'
import ProtectedVideoPreview from '@/components/media/ProtectedVideoPreview.vue'
import ReviewAnnotationPanel from '@/components/review/ReviewAnnotationPanel.vue'
import { approveVersion, createVersionNote, deferVersion, getTaskVersion, listTaskVersions, listVersionNotes, rejectVersion, replyVersionNote, versionFileUrl } from '@/api/shot-grid/versions'
import { getErrorDetails } from '@/utils/requestErrors'
import { getReviewList } from '@/api/shot-grid/reviews'
import { useRouter } from 'vue-router'

const props = defineProps({ versionId: { type: String, required: true }, projectId: { type: String, default: '' }, taskId: { type: String, default: '' }, reviewListId: { type: String, default: '' } })
const router = useRouter()
const user = useUserStore(), versions = ref([]), version = ref(null), notes = ref([]), loading = ref(false), acting = ref(false)
const validContext = computed(() => /^\d+$/.test(props.projectId) && /^\d+$/.test(props.taskId) && /^\d+$/.test(props.versionId))
const canReview = computed(() => ['approve', 'reject', 'defer'].some(action => user.hasPermission(`shotgrid:review:${action}`)))
const primaryFile = computed(() => version.value?.files?.find(file => file.isPrimary) || version.value?.files?.[0])
const mediaSource = computed(() => primaryFile.value ? { projectId: Number(props.projectId), url: versionFileUrl(props.projectId, props.taskId, props.versionId, primaryFile.value.fileId) } : null)
const isVideo = computed(() => primaryFile.value?.mediaType?.startsWith('video/'))

async function load() {
  if (!validContext.value) return
  loading.value = true
  try { [versions.value, version.value, notes.value] = await Promise.all([listTaskVersions(props.projectId, props.taskId), getTaskVersion(props.projectId, props.taskId, props.versionId), listVersionNotes(props.projectId, props.versionId)]) }
  catch (error) { ElMessage.error(getErrorDetails(error).message) }
  finally { loading.value = false }
}
async function submitNote(payload) { await createVersionNote(props.projectId, props.versionId, payload); notes.value = await listVersionNotes(props.projectId, props.versionId); ElMessage.success('意见已提交') }
async function reply(note) { try { const { value } = await ElMessageBox.prompt('回复将作为不可变历史保留', '回复意见', { inputValidator: value => Boolean(value?.trim()) || '回复不能为空' }); await replyVersionNote(props.projectId, props.versionId, note.noteId, { content: value.trim() }); notes.value = await listVersionNotes(props.projectId, props.versionId) } catch (error) { if (!['cancel', 'close'].includes(error)) ElMessage.error(getErrorDetails(error).message) } }
async function act(action) {
  if (acting.value) return
  let reason = null
  try {
    if (action === 'reject') ({ value: reason } = await ElMessageBox.prompt('退回意见将绑定当前版本并永久保留', '退回修改', { inputValidator: value => Boolean(value?.trim()) || '审核意见不能为空' }))
    else await ElMessageBox.confirm(action === 'approve' ? '确认将当前版本设为唯一最终版本并完成任务？' : '保持待审核状态并记录稍后决定动作？', '确认审核动作')
    acting.value = true
    const fn = { approve: approveVersion, reject: rejectVersion, defer: deferVersion }[action]
    await fn(props.projectId, props.taskId, props.versionId, { lockVersion: version.value.lockVersion, reason: reason?.trim() || null })
    ElMessage.success('审核动作已记录')
    if (props.reviewListId) {
      // 重新读取审核单详情，以持久化 sortOrder 决定下一项，不复用当前页面版本数组。
      const reviewList = await getReviewList(props.projectId, props.reviewListId)
      const ordered = [...reviewList.versions].sort((a, b) => a.sortOrder - b.sortOrder)
      const currentIndex = ordered.findIndex(item => item.versionId === Number(props.versionId))
      const next = ordered.slice(currentIndex + 1).find(item => item.versionStatus === 'pending_review')
      if (next) return router.push({ name: 'VersionReview', params: { versionId: next.versionId }, query: { projectId: props.projectId, taskId: next.taskId, reviewListId: props.reviewListId } })
      ElMessage.success('审核单中已无后续待审核版本')
    }
    await load()
  } catch (error) { if (!['cancel', 'close'].includes(error)) ElMessage.error(getErrorDetails(error).status === 409 ? '审核状态已变化，请刷新后查看最新结果。' : getErrorDetails(error).message) }
  finally { acting.value = false }
}
onMounted(load)
</script>

<template>
  <section v-loading="loading" class="review-page">
    <el-alert v-if="!validContext" title="缺少 projectId 或 taskId，无法安全加载审核上下文。" type="error" show-icon />
    <template v-else-if="version">
      <header><div><span class="eyebrow">VERSION / V{{ String(version.versionNo).padStart(3, '0') }}</span><h1>版本审核</h1><p>{{ version.changelog }}</p></div><el-tag>{{ version.versionStatus }}</el-tag></header>
      <nav class="version-strip" aria-label="版本带"><router-link v-for="item in versions" :key="item.versionId" :class="{ active: item.versionId === version.versionId }" :to="{ name: 'VersionReview', params: { versionId: item.versionId }, query: { projectId, taskId } }">V{{ String(item.versionNo).padStart(3, '0') }} · {{ item.versionStatus }}</router-link></nav>
      <div class="review-grid"><main class="media-card"><ProtectedVideoPreview v-if="isVideo" :source="mediaSource" /><ProtectedImagePreview v-else :source="mediaSource" :alt="primaryFile?.businessFileName" /><el-empty v-if="!primaryFile" description="该版本暂无审核媒体" /></main>
      <aside><ReviewAnnotationPanel :version-id="versionId" @submit="submitNote" /><h2>审核意见</h2><el-empty v-if="!notes.length" description="暂无意见" /><article v-for="note in notes" :key="note.noteId" class="note"><p>{{ note.content }}</p><small>{{ note.mediaTimeMs == null ? '无时间点' : `${note.mediaTimeMs} ms` }}</small><div v-for="item in note.replies" :key="item.replyId" class="reply">↳ {{ item.content }}</div><el-button link @click="reply(note)">回复</el-button></article></aside></div>
      <footer v-if="canReview && version.versionStatus === 'pending_review'" class="review-actions"><el-button type="success" :loading="acting" @click="act('approve')">确认通过</el-button><el-button type="danger" :loading="acting" @click="act('reject')">退回修改</el-button><el-button :loading="acting" @click="act('defer')">稍后决定</el-button></footer>
      <el-alert v-else-if="version.versionStatus === 'pending_review'" title="制作人员可查看和回复意见，审核动作仅对项目总监显示。" type="info" show-icon />
    </template>
  </section>
</template>
<style scoped>
.review-page{display:grid;gap:18px}.review-page header{display:flex;justify-content:space-between;align-items:start}.version-strip{display:flex;gap:8px;overflow:auto}.version-strip a{padding:8px 12px;border:1px solid #dcdfe6;border-radius:6px;color:inherit;text-decoration:none;white-space:nowrap}.version-strip a.active{border-color:#409eff;background:#ecf5ff}.review-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(320px,1fr);gap:18px}.media-card,.review-grid aside{padding:16px;background:#fff;border-radius:8px}.note{padding:10px 0;border-top:1px solid #ebeef5}.reply{margin:8px 0 0 12px;color:#606266}.review-actions{position:sticky;bottom:12px;display:flex;justify-content:flex-end;gap:10px;padding:12px;background:#fff;border-radius:8px;box-shadow:0 4px 18px #0002}@media(max-width:900px){.review-grid{grid-template-columns:1fr}}
</style>
