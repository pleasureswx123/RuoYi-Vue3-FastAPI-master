<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { createEpisode, createScene, getEpisodePage, getScenePage } from '@/api/shot-grid/shots'
import ProjectModal from '@/views/project/components/ProjectModal.vue'
import { shotErrorState } from '@/views/shot/shotPresentation'

const props = defineProps({
  projectId: { type: Number, required: true },
  mode: { type: String, required: true, validator: value => ['episode', 'scene'].includes(value) },
  episodes: { type: Array, default: () => [] },
  initialEpisodeId: { type: [Number, String], default: '' }
})
const emit = defineEmits(['close', 'saved'])
const formRef = ref(null)
const busy = ref(false)
const loadingSuggestion = ref(false)
const requestError = ref(null)
let suggestionController = null

const form = reactive({
  episodeId: props.initialEpisodeId ? String(props.initialEpisodeId) : '',
  number: null,
  name: '',
  description: '',
  sortOrder: 0,
  remark: ''
})
const isEpisode = computed(() => props.mode === 'episode')
const title = computed(() => isEpisode.value ? '新建集' : '新建场次')
const numberLabel = computed(() => isEpisode.value ? '集号' : '场次号')
const numberPrefix = computed(() => isEpisode.value ? 'EP' : '')
const rules = {
  episodeId: [{
    validator: (_rule, value, callback) => {
      const id = Number(value)
      if (!isEpisode.value && (!Number.isSafeInteger(id) || id <= 0)) callback(new Error('请选择所属集'))
      else callback()
    },
    trigger: 'change'
  }],
  number: [{
    validator: (_rule, value, callback) => {
      const number = Number(value)
      const minimum = isEpisode.value ? 1 : 0
      if (!Number.isSafeInteger(number) || number < minimum) {
        callback(new Error(isEpisode.value ? '集号必须为正整数' : '场次号必须为非负整数'))
      }
      else callback()
    },
    trigger: 'change'
  }],
  name: [
    { max: 200, message: '名称不能超过 200 个字符', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (isEpisode.value) {
          callback()
          return
        }
        const name = String(value || '').trim()
        if (Number(form.number) === 0 && name !== '序') callback(new Error('000 序场的名称必须为“序”'))
        else if (Number(form.number) > 0 && name === '序') callback(new Error('非 000 场次不能使用“序”作为名称'))
        else callback()
      },
      trigger: ['blur', 'change']
    }
  ],
  description: [{ max: 10000, message: '说明不能超过 10000 个字符', trigger: 'blur' }],
  remark: [{ max: 500, message: '备注不能超过 500 个字符', trigger: 'blur' }]
}

function optionalText(value) {
  const normalized = String(value || '').trim()
  return normalized || null
}

async function fetchAllPages(loader, signal) {
  const rows = []
  for (let pageNum = 1; pageNum <= 100; pageNum += 1) {
    const response = await loader(pageNum, signal)
    rows.push(...(Array.isArray(response.rows) ? response.rows : []))
    if (!response.hasNext) break
  }
  return rows
}

async function loadSuggestion() {
  suggestionController?.abort()
  requestError.value = null
  const episodeId = Number(form.episodeId)
  if (!isEpisode.value && (!Number.isSafeInteger(episodeId) || episodeId <= 0)) {
    form.number = null
    form.sortOrder = 0
    return
  }
  const controller = new AbortController()
  suggestionController = controller
  loadingSuggestion.value = true
  try {
    const rows = isEpisode.value
      ? await fetchAllPages(
        (pageNum, signal) => getEpisodePage(props.projectId, { pageNum, pageSize: 100, orderByColumn: 'episodeNo', isAsc: 'ascending' }, { signal }),
        controller.signal
      )
      : await fetchAllPages(
        (pageNum, signal) => getScenePage(props.projectId, episodeId, { pageNum, pageSize: 100, orderByColumn: 'sceneNo', isAsc: 'ascending' }, { signal }),
        controller.signal
      )
    const numberKey = isEpisode.value ? 'episodeNo' : 'sceneNo'
    const maxNumber = rows.reduce((max, row) => Math.max(max, Number(row[numberKey]) || 0), 0)
    const maxSortOrder = rows.reduce((max, row) => Math.max(max, Number(row.sortOrder) || 0), 0)
    form.number = Math.max(1, maxNumber + 1)
    form.sortOrder = maxSortOrder + 10
    formRef.value?.clearValidate(['number', 'episodeId'])
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') requestError.value = shotErrorState(error, `${title.value}编号建议加载失败`)
  } finally {
    if (suggestionController === controller) loadingSuggestion.value = false
  }
}

async function submit() {
  if (busy.value || loadingSuggestion.value) return
  requestError.value = null
  const valid = formRef.value ? await formRef.value.validate().catch(() => false) : false
  if (!valid) return
  busy.value = true
  try {
    const common = {
      description: optionalText(form.description),
      sortOrder: Number(form.sortOrder) || 0,
      remark: optionalText(form.remark)
    }
    const response = isEpisode.value
      ? await createEpisode(props.projectId, {
        episodeNo: Number(form.number),
        episodeName: optionalText(form.name),
        ...common
      })
      : await createScene(props.projectId, Number(form.episodeId), {
        sceneNo: Number(form.number),
        sceneName: optionalText(form.name),
        ...common
      })
    emit('saved', { type: props.mode, entity: response.data, episodeId: Number(form.episodeId) || response.data?.episodeId })
  } catch (error) {
    requestError.value = shotErrorState(error, `${title.value}失败`)
  } finally {
    busy.value = false
  }
}

function closeDialog() {
  if (busy.value) return
  emit('close')
}

watch(() => form.episodeId, () => {
  if (!isEpisode.value) loadSuggestion()
})
watch(() => form.number, (number, previousNumber) => {
  if (isEpisode.value) return
  if (Number(number) === 0 && !String(form.name || '').trim()) form.name = '序'
  else if (Number(previousNumber) === 0 && Number(number) > 0 && form.name === '序') form.name = ''
  formRef.value?.validateField('name').catch(() => {})
})
onMounted(() => {
  if (!isEpisode.value && !form.episodeId && props.episodes.length === 1) {
    form.episodeId = String(props.episodes[0].episodeId)
  }
  loadSuggestion()
})
onBeforeUnmount(() => suggestionController?.abort())
</script>

<template>
  <ProjectModal
    :title="title"
    :description="isEpisode ? '集号在项目内唯一；创建后会异步创建对应 NAS 集目录。' : '场次号在所属集内唯一；000 固定表示名称为“序”的序场。'"
    :busy="busy"
    @close="closeDialog"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" class="hierarchy-form" :aria-label="`${title}表单`">
      <el-form-item v-if="!isEpisode" label="所属集" prop="episodeId" required>
        <el-select v-model="form.episodeId" placeholder="请选择集" :disabled="busy || loadingSuggestion">
          <el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" />
        </el-select>
      </el-form-item>
      <div class="hierarchy-form__grid">
        <el-form-item :label="numberLabel" prop="number" required>
          <el-input-number v-model="form.number" :min="isEpisode ? 1 : 0" :step="1" step-strictly controls-position="right" :disabled="busy || loadingSuggestion" />
          <small>{{ numberPrefix }}{{ String(form.number ?? 0).padStart(3, '0') }}；默认取现有最大编号 + 1，可调整<span v-if="!isEpisode">，000 表示“序”</span>，最终由后端校验唯一性。</small>
        </el-form-item>
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" maxlength="200" :placeholder="isEpisode ? '可选，如：第三集' : '可选，如：控制室'" :disabled="busy" /></el-form-item>
      </div>
      <el-form-item label="说明" prop="description"><el-input v-model="form.description" type="textarea" :rows="3" maxlength="10000" :disabled="busy" /></el-form-item>
      <el-form-item label="备注" prop="remark"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit :disabled="busy" /></el-form-item>
      <el-alert v-if="requestError" type="error" show-icon :closable="false" :title="requestError.title" :description="requestError.message" />
      <footer><el-button :disabled="busy" @click="closeDialog">取消</el-button><el-button type="primary" :loading="busy" :disabled="loadingSuggestion" @click="submit">{{ title }}</el-button></footer>
    </el-form>
  </ProjectModal>
</template>

<style scoped>
.hierarchy-form{display:grid;gap:18px}.hierarchy-form__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.hierarchy-form:deep(.el-form-item){margin-bottom:0}.hierarchy-form:deep(.el-select),.hierarchy-form:deep(.el-input-number){width:100%}.hierarchy-form small{display:block;margin-top:7px;color:var(--sg-text-muted);font-size:11px;line-height:1.5}footer{display:flex;gap:10px;justify-content:flex-end}@media(max-width:700px){.hierarchy-form__grid{grid-template-columns:1fr}}
</style>
