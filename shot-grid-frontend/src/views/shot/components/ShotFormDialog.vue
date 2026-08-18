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
const shotFormRef = ref(null)
const busy = ref(false)
const scenesLoading = ref(false)
const scenes = ref([])
const validationMessage = ref('')
const requestError = ref(null)
let sceneController = null

const form = reactive({
  episodeId: props.shot?.episodeId ? String(props.shot.episodeId) : '',
  sceneId: props.shot?.sceneId ? String(props.shot.sceneId) : '',
  shotNo: props.shot?.shotNo ?? null,
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
const canSubmit = computed(() => !busy.value && !scenesLoading.value)
const positiveIdRule = message => ({
  validator: (_rule, value, callback) => {
    const id = Number(value)
    if (!Number.isSafeInteger(id) || id <= 0) {
      callback(new Error(message))
      return
    }
    callback()
  },
  trigger: 'change'
})
const shotFormRules = {
  episodeId: [positiveIdRule('请选择有效集')],
  sceneId: [positiveIdRule('请选择有效场次')],
  shotNo: [{
    validator: (_rule, value, callback) => {
      const shotNo = Number(value)
      if (!Number.isSafeInteger(shotNo) || shotNo <= 0) {
        callback(new Error('镜头号必须为正整数'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  sortOrder: [{
    validator: (_rule, value, callback) => {
      const sortOrder = Number(value)
      if (!Number.isSafeInteger(sortOrder) || sortOrder < 0) {
        callback(new Error('成片顺序必须为非负整数'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  durationSeconds: [{
    validator: (_rule, value, callback) => {
      try {
        secondsToDurationMs(value)
        callback()
      } catch (error) {
        callback(new Error(error.message))
      }
    },
    trigger: 'change'
  }],
  description: [{ required: true, whitespace: true, message: '制作内容描述不能为空', trigger: 'blur' }],
  shotSize: [{ max: 40, message: '景别不能超过 40 个字符', trigger: 'blur' }],
  cameraPosition: [{ max: 100, message: '机位不能超过 100 个字符', trigger: 'blur' }],
  cameraMovement: [{ max: 100, message: '镜头运动不能超过 100 个字符', trigger: 'blur' }],
  focalLength: [{ max: 50, message: '焦段不能超过 50 个字符', trigger: 'blur' }],
  remark: [{ max: 500, message: '备注不能超过 500 个字符', trigger: 'blur' }]
}

async function loadScenes(resetScene = false) {
  sceneController?.abort()
  scenes.value = []
  if (resetScene) {
    form.sceneId = ''
    shotFormRef.value?.clearValidate('sceneId')
  }
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

function detailsText(details) {
  if (!details) return ''
  if (typeof details === 'string') return details
  try { return JSON.stringify(details) } catch { return '后端返回了额外诊断信息' }
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
  if (busy.value) return
  validationMessage.value = ''
  requestError.value = null
  const valid = shotFormRef.value
    ? await shotFormRef.value.validate().catch(() => false)
    : false
  if (!valid) return
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

function closeDialog() {
  if (busy.value) return
  shotFormRef.value?.resetFields()
  shotFormRef.value?.clearValidate()
  validationMessage.value = ''
  requestError.value = null
  emit('close')
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
    @close="closeDialog"
  >
    <el-form ref="shotFormRef" :model="form" :rules="shotFormRules" class="shot-form" size="large" label-position="top" aria-label="镜头信息表单">
      <div class="shot-form__grid">
        <el-form-item label="所属集" prop="episodeId" required><el-select v-model="form.episodeId" class="sg-select" placeholder="请选择集" :disabled="isEdit || busy"><el-option label="请选择集" value="" /><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select></el-form-item>
        <el-form-item label="所属场次" prop="sceneId" required><el-select v-model="form.sceneId" class="sg-select" :placeholder="scenesLoading ? '正在加载…' : '请选择场次'" :disabled="scenesLoading || busy"><el-option :label="scenesLoading ? '正在加载…' : '请选择场次'" value="" /><el-option v-for="scene in scenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select></el-form-item>
        <el-form-item label="镜头号" prop="shotNo" required><el-input-number v-model="form.shotNo" :min="1" :step="1" step-strictly controls-position="right" :disabled="isEdit || busy" /></el-form-item>
        <el-form-item label="成片顺序" prop="sortOrder" required><el-input-number v-model="form.sortOrder" :min="0" :step="1" step-strictly controls-position="right" :disabled="busy" /></el-form-item>
        <el-form-item label="时长（秒）" prop="durationSeconds"><el-input-number v-model="form.durationSeconds" :min="0" :step="0.001" :precision="3" controls-position="right" :disabled="busy" /></el-form-item>
        <el-form-item label="景别" prop="shotSize"><el-input v-model="form.shotSize" maxlength="40" placeholder="如：近景" :disabled="busy" /></el-form-item>
        <el-form-item label="机位" prop="cameraPosition"><el-input v-model="form.cameraPosition" maxlength="100" :disabled="busy" /></el-form-item>
        <el-form-item label="镜头运动" prop="cameraMovement"><el-input v-model="form.cameraMovement" maxlength="100" :disabled="busy" /></el-form-item>
        <el-form-item label="焦段" prop="focalLength"><el-input v-model="form.focalLength" maxlength="50" placeholder="支持 35/25 等文本" :disabled="busy" /></el-form-item>
        <el-form-item v-if="!isEdit" label="首次分配制作人" prop="assigneeUserId"><el-select v-model="form.assigneeUserId" class="sg-select" placeholder="暂不分配" :disabled="busy"><el-option label="暂不分配" value="" /><el-option v-for="member in assignableMembers" :key="member.userId" :label="member.userName ? `${member.nickName}（${member.userName}）` : member.nickName" :value="String(member.userId)" /></el-select></el-form-item>
      </div>
      <el-form-item class="shot-form__full" label="制作内容描述" prop="description" required><el-input v-model="form.description" type="textarea" :rows="4" :disabled="busy" /></el-form-item>
      <div class="shot-form__grid shot-form__grid--text">
        <el-form-item label="台词 / 对白" prop="dialogue"><el-input v-model="form.dialogue" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="音效" prop="soundEffect"><el-input v-model="form.soundEffect" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="色调参考" prop="colorReference"><el-input v-model="form.colorReference" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit :disabled="busy" /></el-form-item>
      </div>
      <p v-if="isEdit && shot.assets?.length" class="shot-form__hint">当前 {{ shot.assets.length }} 项资产关系会原样保留；本批不在镜头表单中创建或猜测正式资产。</p>
      <el-alert v-if="validationMessage || requestError" class="shot-form__alert" :type="requestError ? 'error' : 'warning'" :closable="false" show-icon :title="requestError?.title || '请检查表单'"><div class="form-alert-content"><p>{{ requestError?.message || validationMessage }}</p><code v-if="requestError?.errorKey">{{ requestError.errorKey }}</code><small v-if="requestError?.details">{{ detailsText(requestError.details) }}</small><el-button v-if="requestError?.status === 409" link type="primary" @click="emit('refresh')">刷新镜头后重试</el-button></div></el-alert>
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">{{ isEdit ? '保存修改' : '创建镜头' }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.shot-form{display:grid;gap:20px}.shot-form__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.shot-form__grid--text{align-items:start}.shot-form:deep(.el-form-item){margin-bottom:0}.shot-form:deep(.el-form-item__label){height:auto;padding-bottom:8px;color:var(--sg-text);font-size:12px;font-weight:650;line-height:1.2}.shot-form:deep(.el-select),.shot-form:deep(.el-input-number){width:100%}.shot-form__hint{margin:0;padding:12px;color:var(--sg-text-muted);font-size:12px;background:rgba(255,255,255,.025);border-radius:9px}.form-alert-content{display:grid;gap:5px}.form-alert-content p{margin:0}.form-alert-content code,.form-alert-content small{color:var(--sg-text-muted);font-size:11px}.form-alert-content:deep(.el-button){width:max-content;margin:0;padding:0}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:700px){.shot-form__grid{grid-template-columns:1fr}}
</style>
