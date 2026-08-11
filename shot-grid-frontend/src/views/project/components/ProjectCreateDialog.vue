<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import {
  createProject,
  getStorageRootOptions,
  previewProjectPath
} from '@/api/shot-grid/projects'
import { createIdempotencyState } from '@/utils/idempotency'
import { projectErrorState } from '@/views/project/projectPresentation'
import MemberCandidateSelect from './MemberCandidateSelect.vue'
import ProjectModal from './ProjectModal.vue'

const props = defineProps({ currentUser: { type: Object, required: true } })
const emit = defineEmits(['close', 'created'])
const idempotency = createIdempotencyState('project-create')
const busy = ref(false)
const validationMessage = ref('')
const requestError = ref(null)
const storageRoots = ref([])
const storageLoading = ref(false)
const storageError = ref(null)
const pathPreview = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)
const directors = ref([
  {
    userId: Number(props.currentUser.userId),
    userName: props.currentUser.userName,
    nickName: props.currentUser.nickName,
    deptName: props.currentUser.dept?.deptName || null
  }
])
const members = ref([])
const form = reactive({
  projectCode: '', projectName: '', projectDescription: '', aspectRatio: '16:9',
  plannedDurationMinutes: '', deliveryDate: '', storageRootId: '', projectDirectoryName: '', remark: ''
})
let storageController = null
let previewController = null

const selectedUserIds = computed(() => [
  ...directors.value.map(item => item.userId),
  ...members.value.map(item => item.userId)
])
const canSubmit = computed(() =>
  !busy.value && form.projectCode.trim() && form.projectName.trim() && form.storageRootId && directors.value.length
)

async function loadStorageRoots() {
  storageController?.abort()
  storageController = new AbortController()
  storageLoading.value = true
  storageError.value = null
  try {
    const response = await getStorageRootOptions({ signal: storageController.signal })
    storageRoots.value = Array.isArray(response.data) ? response.data : []
    if (storageRoots.value.length === 1 && !form.storageRootId) {
      form.storageRootId = String(storageRoots.value[0].storageRootId)
    }
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      storageRoots.value = []
      storageError.value = projectErrorState(error, 'NAS 根目录选项加载失败')
    }
  } finally {
    storageLoading.value = false
  }
}

function invalidatePathPreview() {
  pathPreview.value = null
  previewError.value = null
  previewController?.abort()
}

async function loadPathPreview() {
  invalidatePathPreview()
  const storageRootId = Number(form.storageRootId)
  if (!storageRootId || !form.projectName.trim() || !form.projectDirectoryName.trim()) {
    previewError.value = { title: '路径预览条件不足', message: '请先选择 NAS 根目录并填写项目名称和目录名称。' }
    return null
  }
  previewController = new AbortController()
  previewLoading.value = true
  try {
    const response = await previewProjectPath(
      storageRootId,
      {
        projectType: 'ai_short_film',
        projectName: form.projectName.trim(),
        projectDirectoryName: form.projectDirectoryName.trim()
      },
      { signal: previewController.signal }
    )
    pathPreview.value = response.data
    if (response.data.pathConflict) {
      previewError.value = { title: '项目目录已被占用', message: '请修改项目目录名称后重新预览。' }
    }
    return response.data
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') previewError.value = projectErrorState(error, 'NAS 路径预览失败')
    return null
  } finally {
    previewLoading.value = false
  }
}

function addDirector(candidate) {
  directors.value.push(candidate)
}

function addMember(candidate) {
  members.value.push({ ...candidate, projectRole: 'creator', producerCode: '' })
}

function buildPayload() {
  const projectCode = form.projectCode.trim().toUpperCase()
  if (!/^[A-Z0-9]{2,12}$/.test(projectCode)) throw new Error('项目代号必须为 2—12 位大写英文字母或数字')
  const projectName = form.projectName.trim()
  const directoryName = form.projectDirectoryName.trim()
  if (!projectName || !directoryName) throw new Error('项目名称和项目目录名称不能为空')
  const storageRootId = Number(form.storageRootId)
  if (!Number.isSafeInteger(storageRootId) || storageRootId <= 0) throw new Error('请选择有效的 NAS 根目录')
  if (!directors.value.length) throw new Error('项目必须至少有一名项目总监')
  const normalizedMembers = members.value.map((member, index) => {
    const producerCode = member.producerCode.trim().toUpperCase()
    if (producerCode && !/^[A-Z0-9]{2,12}$/.test(producerCode)) {
      throw new Error(`第 ${index + 1} 位成员的制作人缩写必须为 2—12 位英文字母或数字`)
    }
    return { userId: member.userId, projectRole: member.projectRole, producerCode: producerCode || null }
  })
  const producerCodes = normalizedMembers.map(member => member.producerCode).filter(Boolean)
  if (new Set(producerCodes).size !== producerCodes.length) throw new Error('同一项目内制作人缩写不能重复')
  const minutes = form.plannedDurationMinutes === '' ? null : Number(form.plannedDurationMinutes)
  if (minutes !== null && (!Number.isFinite(minutes) || minutes < 0)) throw new Error('计划总时长不能为负数')
  return {
    projectCode, projectName, projectType: 'ai_short_film',
    projectDescription: form.projectDescription.trim() || null, aspectRatio: form.aspectRatio,
    plannedDurationMs: minutes === null ? null : Math.round(minutes * 60000),
    deliveryDate: form.deliveryDate || null, storageRootId, projectDirectoryName: directoryName,
    directorUserIds: directors.value.map(item => item.userId), members: normalizedMembers,
    remark: form.remark.trim() || null
  }
}

async function submit() {
  validationMessage.value = ''
  requestError.value = null
  let payload
  try { payload = buildPayload() } catch (error) { validationMessage.value = error.message; return }
  const preview = pathPreview.value || (await loadPathPreview())
  if (!preview || preview.pathConflict) return
  busy.value = true
  try {
    const response = await createProject(payload, idempotency.forPayload(payload))
    emit('created', response.data)
  } catch (error) {
    requestError.value = projectErrorState(error, '项目创建失败')
  } finally { busy.value = false }
}

onMounted(loadStorageRoots)
onBeforeUnmount(() => { storageController?.abort(); previewController?.abort() })
</script>

<template>
  <ProjectModal title="创建项目" description="先由后端预览并校验 NAS 路径，再以同一幂等键受理项目和目录初始化。" :busy="busy" wide @close="emit('close')">
    <form class="project-form" @submit.prevent="submit">
      <div class="project-form__grid">
        <label><span>项目名称 *</span><input v-model="form.projectName" maxlength="200" placeholder="如：罗刹夫人" @input="invalidatePathPreview" /></label>
        <label><span>项目代号 *</span><input v-model="form.projectCode" maxlength="12" placeholder="如：LCFR" @input="form.projectCode = form.projectCode.toUpperCase()" /></label>
        <label><span>画幅 *</span><select v-model="form.aspectRatio"><option v-for="ratio in ['16:9','21:9','2.39:1','9:16','1:1']" :key="ratio">{{ ratio }}</option></select></label>
        <label><span>项目类型</span><input value="AI 影视短片" disabled /></label>
        <label><span>计划总时长（分钟）</span><input v-model="form.plannedDurationMinutes" type="number" min="0" step="0.1" placeholder="可选" /></label>
        <label><span>交付日期</span><input v-model="form.deliveryDate" type="date" /></label>
        <label>
          <span>NAS 根目录 *</span>
          <select v-model="form.storageRootId" :disabled="storageLoading || !!storageError" @change="invalidatePathPreview">
            <option value="">{{ storageLoading ? '正在加载健康根目录…' : '请选择健康根目录' }}</option>
            <option v-for="root in storageRoots" :key="root.storageRootId" :value="String(root.storageRootId)">{{ root.rootName }}（{{ root.rootCode }}）</option>
          </select>
          <small v-if="!storageError && !storageLoading && storageRoots.length === 0">当前没有已启用且探测健康的 NAS 根目录，请联系管理员。</small>
          <small v-if="storageError" class="field-error">
            {{ storageError.message }}
            <button v-if="storageError.retryable" type="button" @click="loadStorageRoots">重试</button>
          </small>
        </label>
        <label><span>项目目录名称 *</span><input v-model="form.projectDirectoryName" maxlength="240" placeholder="如：罗刹夫人" @input="invalidatePathPreview" /></label>
      </div>

      <section class="path-preview">
        <div>
          <strong>NAS 项目路径预览</strong>
          <p v-if="pathPreview" :class="{ conflict: pathPreview.pathConflict }">{{ pathPreview.projectPathPreview }}</p>
          <p v-else>路径只由后端白名单根目录和规范化规则计算，不接受浏览器提交 UNC 根路径。</p>
          <small v-if="previewError" class="field-error">{{ previewError.message }}</small>
        </div>
        <el-button plain :loading="previewLoading" @click="loadPathPreview">预览路径</el-button>
      </section>

      <section class="people-section">
        <div class="people-section__heading"><div><strong>初始项目总监 *</strong><p>至少一名，默认包含当前账号。</p></div></div>
        <div class="people-pills"><span v-for="(director,index) in directors" :key="director.userId">{{ director.nickName || director.userName }}<button v-if="directors.length > 1" type="button" @click="directors.splice(index,1)">×</button></span></div>
        <MemberCandidateSelect :exclude-ids="selectedUserIds" placeholder="搜索并添加项目总监" @select="addDirector" />
      </section>

      <section class="people-section">
        <div class="people-section__heading"><div><strong>其他初始成员</strong><p>候选仅来自有效平台账号；也可以创建后再维护。</p></div></div>
        <MemberCandidateSelect :exclude-ids="selectedUserIds" @select="addMember" />
        <div v-if="members.length" class="member-rows">
          <div v-for="(member,index) in members" :key="member.userId" class="member-row">
            <div><strong>{{ member.nickName || member.userName }}</strong><small>{{ member.userName }} · {{ member.deptName || '未分配部门' }}</small></div>
            <select v-model="member.projectRole"><option value="creator">制作人员</option><option value="director">项目总监</option></select>
            <input v-model="member.producerCode" maxlength="12" placeholder="制作人缩写（可空）" @input="member.producerCode = member.producerCode.toUpperCase()" />
            <button type="button" @click="members.splice(index,1)">移除</button>
          </div>
        </div>
      </section>

      <label class="project-form__full"><span>项目描述</span><textarea v-model="form.projectDescription" rows="3" /></label>
      <label class="project-form__full"><span>备注</span><textarea v-model="form.remark" rows="2" maxlength="500" /></label>

      <div v-if="validationMessage || requestError" class="form-error" role="alert"><strong>{{ requestError?.title || '请检查表单' }}</strong><span>{{ requestError?.message || validationMessage }}</span><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code></div>
      <footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="busy" :disabled="!canSubmit">创建并初始化 NAS</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.project-form, .project-form label { display: grid; gap: 8px; }
.project-form { gap: 22px; }
.project-form__grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; }
label > span, .people-section strong, .path-preview strong { font-size: 13px; font-weight: 600; }
input, select, textarea { width: 100%; color: var(--sg-text); background: rgba(255,255,255,.035); border: 1px solid var(--sg-border-strong); border-radius: 10px; }
input, select { height: 42px; padding: 0 12px; }
textarea { padding: 11px 12px; resize: vertical; }
input:focus, select:focus, textarea:focus { border-color: var(--sg-accent); outline: 0; }
input:disabled, select:disabled { color: var(--sg-text-muted); cursor: not-allowed; }
small, .people-section p, .path-preview p { margin: 0; color: var(--sg-text-muted); font-size: 11px; line-height: 1.55; }
.field-error { color: #ffb4b4; }
.field-error button { color: var(--sg-accent); cursor: pointer; background: transparent; border: 0; }
.path-preview, .people-section { padding: 18px; background: rgba(255,255,255,.025); border: 1px solid var(--sg-border); border-radius: 14px; }
.path-preview { display: flex; gap: 18px; align-items: center; justify-content: space-between; }
.path-preview p { margin-top: 6px; overflow-wrap: anywhere; }
.path-preview p.conflict { color: var(--sg-danger); }
.people-section { display: grid; gap: 13px; }
.people-section__heading { display: flex; justify-content: space-between; }
.people-pills { display: flex; flex-wrap: wrap; gap: 8px; }
.people-pills span { padding: 7px 10px; color: var(--sg-text-secondary); font-size: 12px; background: var(--sg-accent-soft); border-radius: 999px; }
.people-pills button { margin-left: 7px; color: var(--sg-danger); cursor: pointer; background: transparent; border: 0; }
.member-rows { display: grid; gap: 9px; }
.member-row { display: grid; grid-template-columns: minmax(150px,1fr) 130px minmax(150px,1fr) auto; gap: 9px; align-items: center; }
.member-row strong, .member-row small { display: block; }
.member-row strong { font-size: 12px; }
.member-row button { color: var(--sg-danger); cursor: pointer; background: transparent; border: 0; }
.form-error { display: grid; gap: 5px; padding: 14px; color: #ffb4b4; font-size: 13px; background: rgba(255,107,107,.08); border-radius: 10px; }
.form-error code { color: var(--sg-text-muted); font-size: 11px; }
footer { display: flex; gap: 10px; justify-content: flex-end; }
@media (max-width:700px) { .project-form__grid, .member-row { grid-template-columns: 1fr; } .path-preview { align-items: stretch; flex-direction: column; } }
</style>
