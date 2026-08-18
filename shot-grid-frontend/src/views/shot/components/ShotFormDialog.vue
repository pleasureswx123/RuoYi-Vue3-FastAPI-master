<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { createShot, getScenePage, updateShot } from '@/api/shot-grid/shots'
import { secondsToDurationMs, shotErrorState } from '@/views/shot/shotPresentation'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  episodes: { type: Array, required: true },
  members: { type: Array, default: () => [] },
  shot: { type: Object, default: null }
})
const emit = defineEmits(['close', 'saved', 'refresh'])
const operationContext = Object.freeze({
  projectId: Number(props.projectId),
  shotId: props.shot?.shotId ? Number(props.shot.shotId) : null,
  operationGeneration: Number(props.operationGeneration)
})
const busy = ref(false)
const scenesLoading = ref(false)
const scenes = ref([])
const validationMessage = ref('')
const requestError = ref(null)
let sceneController = null

const form = reactive({
  episodeId: props.shot?.episodeId ? String(props.shot.episodeId) : '',
  sceneId: props.shot?.sceneId ? String(props.shot.sceneId) : '',
  shotNo: props.shot?.shotNo ?? '',
  durationSeconds: props.shot ? Number(props.shot.durationMs || 0) / 1000 : 0,
  shotSize: props.shot?.shotSize || '',
  cameraPosition: props.shot?.cameraPosition || '',
  cameraMovement: props.shot?.cameraMovement || '',
  focalLength: props.shot?.focalLength || '',
  description: props.shot?.description || '',
  dialogue: props.shot?.dialogue || '',
  soundEffect: props.shot?.soundEffect || '',
  colorReference: props.shot?.colorReference || '',
  remark: props.shot?.remark || '',
  sortOrder: props.shot?.sortOrder ?? 0,
  assigneeUserId: props.shot?.assignee?.userId ? String(props.shot.assignee.userId) : ''
})

const isEdit = computed(() => Boolean(props.shot?.shotId))
const assignableMembers = computed(() => props.members.filter(member => member.projectRole === 'creator'))
const canSubmit = computed(() => !busy.value && form.sceneId && form.shotNo && form.description.trim())

async function loadScenes(resetScene = false) {
  sceneController?.abort()
  scenes.value = []
  if (resetScene) form.sceneId = ''
  const episodeId = Number(form.episodeId)
  if (!Number.isSafeInteger(episodeId) || episodeId <= 0) return
  const controller = new AbortController()
  sceneController = controller
  scenesLoading.value = true
  try {
    const response = await getScenePage(
      operationContext.projectId,
      episodeId,
      { pageNum: 1, pageSize: 100, lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
      { signal: controller.signal }
    )
    scenes.value = Array.isArray(response.rows) ? response.rows : []
    if (!form.sceneId && scenes.value.length === 1) form.sceneId = String(scenes.value[0].sceneId)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') requestError.value = shotErrorState(error, '场次选项加载失败')
  } finally {
    if (sceneController === controller) scenesLoading.value = false
  }
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

function buildPayload() {
  const sceneId = Number(form.sceneId)
  const shotNo = Number(form.shotNo)
  const durationSeconds = Number(form.durationSeconds)
  const sortOrder = Number(form.sortOrder)
  if (!Number.isSafeInteger(sceneId) || sceneId <= 0) throw new Error('请选择有效场次')
  if (!Number.isSafeInteger(shotNo) || shotNo <= 0) throw new Error('镜头号必须为正整数')
  const durationMs = secondsToDurationMs(durationSeconds)
  if (!Number.isSafeInteger(sortOrder) || sortOrder < 0) throw new Error('成片顺序必须为非负整数')
  const description = form.description.trim()
  if (!description) throw new Error('制作内容描述不能为空')
  const payload = {
    sceneId,
    shotNo,
    durationMs,
    shotSize: optionalText(form.shotSize),
    cameraPosition: optionalText(form.cameraPosition),
    cameraMovement: optionalText(form.cameraMovement),
    focalLength: optionalText(form.focalLength),
    description,
    dialogue: optionalText(form.dialogue),
    soundEffect: optionalText(form.soundEffect),
    colorReference: optionalText(form.colorReference),
    remark: optionalText(form.remark),
    sortOrder,
    assetIds: isEdit.value ? (props.shot.assets || []).map(asset => asset.assetId) : []
  }
  if (!isEdit.value && form.assigneeUserId) payload.assigneeUserId = Number(form.assigneeUserId)
  if (isEdit.value) payload.lockVersion = props.shot.lockVersion
  return payload
}

async function submit() {
  validationMessage.value = ''
  requestError.value = null
  let payload
  try { payload = buildPayload() } catch (error) { validationMessage.value = error.message; return }
  busy.value = true
  try {
    const response = isEdit.value
      ? await updateShot(operationContext.projectId, operationContext.shotId, payload)
      : await createShot(operationContext.projectId, payload)
    emit('saved', response.data, operationContext)
  } catch (error) {
    requestError.value = shotErrorState(error, isEdit.value ? '镜头修改失败' : '镜头创建失败')
  } finally { busy.value = false }
}

watch(() => form.episodeId, () => loadScenes(true))
onMounted(() => loadScenes(false))
onBeforeUnmount(() => sceneController?.abort())
</script>

<template>
  <ProjectModal
    :title="isEdit ? `编辑 ${shot.shotCode}` : '新建镜头'"
    description="镜头号在整集内唯一；已有任务的负责人改派必须使用独立任务分配动作。"
    :busy="busy"
    wide
    @close="emit('close')"
  >
    <form class="shot-form" @submit.prevent="submit">
      <div class="shot-form__grid">
        <label><span>所属集 *</span><el-select v-model="form.episodeId" class="sg-select" placeholder="请选择集" :disabled="isEdit"><el-option label="请选择集" value="" /><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select></label>
        <label><span>所属场次 *</span><el-select v-model="form.sceneId" class="sg-select" :placeholder="scenesLoading ? '正在加载…' : '请选择场次'" :disabled="scenesLoading"><el-option :label="scenesLoading ? '正在加载…' : '请选择场次'" value="" /><el-option v-for="scene in scenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select></label>
        <label><span>镜头号 *</span><input v-model="form.shotNo" type="number" min="1" step="1" :disabled="isEdit" /></label>
        <label><span>成片顺序 *</span><input v-model="form.sortOrder" type="number" min="0" step="1" /></label>
        <label><span>时长（秒）</span><input v-model="form.durationSeconds" type="number" min="0" step="0.001" /></label>
        <label><span>景别</span><input v-model="form.shotSize" maxlength="40" placeholder="如：近景" /></label>
        <label><span>机位</span><input v-model="form.cameraPosition" maxlength="100" /></label>
        <label><span>镜头运动</span><input v-model="form.cameraMovement" maxlength="100" /></label>
        <label><span>焦段</span><input v-model="form.focalLength" maxlength="50" placeholder="支持 35/25 等文本" /></label>
        <label v-if="!isEdit"><span>首次分配制作人</span><el-select v-model="form.assigneeUserId" class="sg-select" placeholder="暂不分配"><el-option label="暂不分配" value="" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="member.userName ? `${member.nickName}（${member.userName}）` : member.nickName" :value="String(member.userId)" /></el-select></label>
      </div>
      <label class="shot-form__full"><span>制作内容描述 *</span><textarea v-model="form.description" rows="4" /></label>
      <div class="shot-form__grid shot-form__grid--text">
        <label><span>台词 / 对白</span><textarea v-model="form.dialogue" rows="3" /></label>
        <label><span>音效</span><textarea v-model="form.soundEffect" rows="3" /></label>
        <label><span>色调参考</span><textarea v-model="form.colorReference" rows="3" /></label>
        <label><span>备注</span><textarea v-model="form.remark" rows="3" maxlength="500" /></label>
      </div>
      <p v-if="isEdit && shot.assets?.length" class="shot-form__hint">当前 {{ shot.assets.length }} 项资产关系会原样保留；本批不在镜头表单中创建或猜测正式资产。</p>
      <div v-if="validationMessage || requestError" class="shot-form__error" role="alert"><strong>{{ requestError?.title || '请检查表单' }}</strong><span>{{ requestError?.message || validationMessage }}</span><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><button v-if="requestError?.status === 409" type="button" @click="emit('refresh')">刷新镜头后重试</button></div>
      <footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" native-type="submit" :loading="busy" :disabled="!canSubmit">{{ isEdit ? '保存修改' : '创建镜头' }}</el-button></footer>
    </form>
  </ProjectModal>
</template>

<style scoped>
.shot-form,.shot-form label{display:grid;gap:8px}.shot-form{gap:20px}.shot-form__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.shot-form__grid--text{align-items:start}.shot-form label>span{font-size:12px;font-weight:650}input,select,textarea{width:100%;color:var(--sg-text);background:rgba(255,255,255,.035);border:1px solid var(--sg-border-strong);border-radius:10px}input,select{height:42px;padding:0 12px}textarea{padding:11px 12px;resize:vertical}input:focus,select:focus,textarea:focus{border-color:var(--sg-accent);outline:0}input:disabled,select:disabled{color:var(--sg-text-muted);cursor:not-allowed}.shot-form__hint{margin:0;padding:12px;color:var(--sg-text-muted);font-size:12px;background:rgba(255,255,255,.025);border-radius:9px}.shot-form__error{display:grid;gap:5px;padding:14px;color:#ffb4b4;font-size:13px;background:rgba(255,107,107,.08);border-radius:10px}.shot-form__error button{width:max-content;padding:0;color:var(--sg-accent);cursor:pointer;background:transparent;border:0}.shot-form__error code{color:var(--sg-text-muted);font-size:11px}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:700px){.shot-form__grid{grid-template-columns:1fr}}
</style>
