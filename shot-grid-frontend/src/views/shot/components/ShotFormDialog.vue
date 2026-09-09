<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { createShot, getScenePage, updateShot } from '@/api/shot-grid/shots'
import { secondsToDurationMs, shotErrorState } from '@/views/shot/shotPresentation'
import ProjectDrawer from '@/views/project/components/ProjectDrawer.vue'
import ProjectModal from '@/views/project/components/ProjectModal.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  operationGeneration: { type: Number, required: true },
  episodes: { type: Array, required: true },
  initialEpisodeId: { type: [Number, String], default: '' },
  initialSceneId: { type: [Number, String], default: '' },
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
let scenesController = null

const form = reactive({
  episodeId: props.shot?.episodeId
    ? String(props.shot.episodeId)
    : (props.initialEpisodeId ? String(props.initialEpisodeId) : ''),
  sceneId: props.shot?.sceneId
    ? String(props.shot.sceneId)
    : (props.initialSceneId ? String(props.initialSceneId) : ''),
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
  shotNo: props.shot?.shotNo ? String(props.shot.shotNo) : ''
})

const isEdit = computed(() => Boolean(props.shot?.shotId))
const canSubmit = computed(() => !busy.value && !scenesLoading.value)
const MAX_SHOT_NO = 214748364
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
      if (isEdit.value) { callback(); return }
      const shotNo = Number(value)
      if (!/^[0-9]+$/.test(String(value).trim()) || !Number.isSafeInteger(shotNo) || shotNo <= 0 || shotNo > MAX_SHOT_NO) {
        callback(new Error('镜头号须为 1 至 214748364 的整数'))
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
  shotSize: [{ max: 500, message: '景别不能超过 500 个字符', trigger: 'blur' }],
  cameraPosition: [{ max: 500, message: '机位不能超过 500 个字符', trigger: 'blur' }],
  cameraMovement: [{ max: 500, message: '镜头运动不能超过 500 个字符', trigger: 'blur' }],
  focalLength: [{ max: 500, message: '焦段不能超过 500 个字符', trigger: 'blur' }],
  remark: [{ max: 2000, message: '备注不能超过 2000 个字符', trigger: 'blur' }]
}

async function loadScenes(resetScene = false) {
  scenesController?.abort()
  scenes.value = []
  if (resetScene) {
    form.sceneId = ''
    form.shotNo = ''
    shotFormRef.value?.clearValidate('sceneId')
    shotFormRef.value?.clearValidate('shotNo')
  }
  const episodeId = Number(form.episodeId)
  if (!Number.isSafeInteger(episodeId) || episodeId <= 0) return
  const controller = new AbortController()
  scenesController = controller
  scenesLoading.value = true
  try {
    const sceneResponse = await getScenePage(
      operationContext.projectId,
      episodeId,
      { pageNum: 1, pageSize: 100, lifecycleStatus: 'active', orderByColumn: 'sceneNo', isAsc: 'ascending' },
      { signal: controller.signal }
    )
    scenes.value = Array.isArray(sceneResponse.rows) ? sceneResponse.rows : []
    if (form.sceneId && !scenes.value.some(scene => String(scene.sceneId) === String(form.sceneId))) {
      form.sceneId = ''
      form.shotNo = ''
    }
    if (!form.sceneId && scenes.value.length === 1) form.sceneId = String(scenes.value[0].sceneId)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') requestError.value = shotErrorState(error, '场次选项加载失败')
  } finally {
    if (scenesController === controller) scenesLoading.value = false
  }
}

function changeScene() {
  if (!isEdit.value) form.shotNo = ''
  shotFormRef.value?.clearValidate('shotNo')
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

function buildPayload() {
  const sceneId = Number(form.sceneId)
  const durationSeconds = Number(form.durationSeconds)
  const shotNo = Number(form.shotNo)
  if (!Number.isSafeInteger(sceneId) || sceneId <= 0) throw new Error('请选择有效场次')
  const durationMs = secondsToDurationMs(durationSeconds)
  if (!isEdit.value && (!Number.isSafeInteger(shotNo) || shotNo <= 0 || shotNo > MAX_SHOT_NO)) throw new Error('镜头号须为 1 至 214748364 的整数')
  const description = form.description.trim()
  const payload = {
    sceneId,
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
    assetIds: isEdit.value ? (props.shot.assets || []).map(asset => asset.assetId) : []
  }
  if (!isEdit.value) payload.shotNo = shotNo
  if (isEdit.value) payload.lockVersion = props.shot.lockVersion
  return payload
}

async function submit() {
  if (busy.value || scenesLoading.value) return
  busy.value = true
  validationMessage.value = ''
  requestError.value = null
  const valid = shotFormRef.value
    ? await shotFormRef.value.validate().catch(() => false)
    : false
  if (!valid) { busy.value = false; return }
  let payload
  try { payload = buildPayload() } catch (error) { validationMessage.value = error.message; busy.value = false; return }
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
onBeforeUnmount(() => {
  scenesController?.abort()
})
</script>

<template>
  <component
    :is="isEdit ? ProjectDrawer : ProjectModal"
    :title="isEdit ? `编辑 ${shot.shotCode}` : '新建镜头'"
    :description="isEdit ? '镜头号保持不变，可补充制作信息；负责人改派请使用任务分配动作。' : '手动填写镜头号，允许跳号，同一场次不能重复；创建后可继续补充制作信息。'"
    :busy="busy"
    wide
    @close="closeDialog"
  >
    <el-form ref="shotFormRef" :model="form" :rules="shotFormRules" class="shot-form" size="large" label-position="top" aria-label="镜头信息表单">
      <div class="shot-form__grid">
        <el-form-item label="所属集" prop="episodeId" required><el-select v-model="form.episodeId" class="sg-select" placeholder="请选择集" :disabled="isEdit || busy"><el-option label="请选择集" value="" /><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select></el-form-item>
        <el-form-item label="所属场次" prop="sceneId" required><el-select v-model="form.sceneId" class="sg-select" :placeholder="scenesLoading ? '正在加载…' : '请选择场次'" :disabled="isEdit || scenesLoading || busy" @change="changeScene"><el-option :label="scenesLoading ? '正在加载…' : '请选择场次'" value="" /><el-option v-for="scene in scenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select></el-form-item>
        <el-form-item label="镜头号" prop="shotNo" required><el-input v-model="form.shotNo" inputmode="numeric" maxlength="9" placeholder="例如：0010、0030" :disabled="isEdit || !form.sceneId || busy" @keyup.enter="submit" /><small class="shot-form__field-hint">允许不连续，无需从 0001 开始；同一场次内不能重复。</small></el-form-item>
        <el-form-item label="时长（秒）" prop="durationSeconds"><el-input-number v-model="form.durationSeconds" :min="0" :step="0.001" :precision="3" controls-position="right" :disabled="busy" /></el-form-item>
        <el-form-item label="景别" prop="shotSize"><el-input v-model="form.shotSize" maxlength="500" placeholder="如：近景" :disabled="busy" /></el-form-item>
        <el-form-item label="机位" prop="cameraPosition"><el-input v-model="form.cameraPosition" maxlength="500" :disabled="busy" /></el-form-item>
        <el-form-item label="镜头运动" prop="cameraMovement"><el-input v-model="form.cameraMovement" maxlength="500" :disabled="busy" /></el-form-item>
        <el-form-item label="焦段" prop="focalLength"><el-input v-model="form.focalLength" maxlength="500" placeholder="支持 35/25 等文本" :disabled="busy" /></el-form-item>
      </div>
      <p class="shot-form__hint">镜头号由使用者填写，系统统一补齐至少四位显示；创建不会改变其他镜头编号。</p>
      <el-alert v-if="!isEdit" title="创建后状态：未分配" description="创建镜头不会同时创建制作任务；请返回镜头列表或详情，通过“分配任务”完成委派。" type="info" show-icon :closable="false" />
      <el-form-item class="shot-form__full" label="制作内容描述" prop="description"><el-input v-model="form.description" type="textarea" :rows="4" :disabled="busy" /></el-form-item>
      <div class="shot-form__grid shot-form__grid--text">
        <el-form-item label="台词 / 对白" prop="dialogue"><el-input v-model="form.dialogue" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="音效" prop="soundEffect"><el-input v-model="form.soundEffect" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="色调参考" prop="colorReference"><el-input v-model="form.colorReference" type="textarea" :rows="3" :disabled="busy" /></el-form-item>
        <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="3" maxlength="2000" show-word-limit :disabled="busy" /></el-form-item>
      </div>
      <p v-if="isEdit && shot.assets?.length" class="shot-form__hint">当前 {{ shot.assets.length }} 项关联资产将保持不变；如需调整，请前往资产管理。</p>
      <el-alert v-if="validationMessage || requestError" class="shot-form__alert" :type="requestError ? 'error' : 'warning'" :closable="false" show-icon :title="requestError?.title || '请检查表单'"><div class="form-alert-content"><p>{{ requestError?.message || validationMessage }}</p><el-button v-if="requestError?.status === 409" link type="primary" @click="emit('refresh')">刷新镜头后重试</el-button></div></el-alert>
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">{{ isEdit ? '保存修改' : '创建镜头' }}</el-button></footer>
    </el-form>
  </component>
</template>

<style scoped>
.shot-form{display:grid;gap:20px}.shot-form__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.shot-form__grid--text{align-items:start}.shot-form:deep(.el-form-item){margin-bottom:0}.shot-form:deep(.el-form-item__label){height:auto;padding-bottom:8px;color:var(--sg-text);font-size:12px;font-weight:650;line-height:1.2}.shot-form:deep(.el-select),.shot-form:deep(.el-input-number){width:100%}.shot-form__hint{margin:0;padding:12px;color:var(--sg-text-muted);font-size:12px;background:rgba(255,255,255,.025);border-radius:9px}.shot-form__field-hint{display:block;margin-top:7px;color:var(--sg-text-muted);font-size:11px;line-height:1.5}.form-alert-content{display:grid;gap:5px}.form-alert-content p{margin:0}.form-alert-content code,.form-alert-content small{color:var(--sg-text-muted);font-size:11px}.form-alert-content:deep(.el-button){width:max-content;margin:0;padding:0}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:700px){.shot-form__grid{grid-template-columns:1fr}}
</style>
