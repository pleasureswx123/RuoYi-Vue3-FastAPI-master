<script setup>
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { updateCandidateGenerationPrompt } from '@/api/shot-grid/versions'

const props = defineProps({
  candidate: { type: Object, default: null },
  version: { type: Object, default: null }
})
const emit = defineEmits(['saved'])
const editing = ref(false)
const busy = ref(false)
const error = ref('')
const formRef = ref(null)
const form = reactive({ generationPrompt: '' })
let previousPrompt = null
let generation = 0
onBeforeUnmount(() => { generation += 1 })
const rules = {
  generationPrompt: [{ validator: (_rule, value, callback) => {
    if (value.length > 10000) return callback(new Error('提示词最多 10000 字'))
    if ([...value].some(char => /\p{Cc}/u.test(char) && !['\n', '\r', '\t'].includes(char))) {
      return callback(new Error('提示词不能包含控制字符'))
    }
    callback()
  }, trigger: 'blur' }]
}
watch(() => [props.version?.versionId, props.candidate?.candidateId], () => {
  generation += 1
  editing.value = false
  busy.value = false
  error.value = ''
})
function startEditing() {
  previousPrompt = props.candidate?.generationPrompt || null
  form.generationPrompt = previousPrompt || ''
  error.value = ''
  editing.value = true
}
function cancel() {
  editing.value = false
  error.value = ''
  formRef.value?.resetFields()
}
async function save() {
  if (busy.value || !props.version?.canEditGenerationPrompt) return
  const currentGeneration = generation
  if (!await formRef.value?.validate().catch(() => false)) return
  if (busy.value || currentGeneration !== generation) return
  busy.value = true
  error.value = ''
  try {
    const result = await updateCandidateGenerationPrompt(props.version.versionId, props.candidate.candidateId, {
      generationPrompt: form.generationPrompt.trim() || null,
      previousGenerationPrompt: previousPrompt
    })
    if (currentGeneration !== generation) return
    emit('saved', result.data)
    editing.value = false
  } catch (err) {
    if (currentGeneration === generation) error.value = err?.response?.data?.msg || err?.message || '提示词保存失败，请重试'
  } finally {
    if (currentGeneration === generation) busy.value = false
  }
}
</script>

<template>
  <el-card v-if="candidate" class="candidate-generation-prompt" shadow="never">
    <template #header>
      <div class="candidate-generation-prompt__header">
        <strong>{{ candidate.candidateNumber }} · AI 生成提示词</strong>
        <el-button v-if="version?.canEditGenerationPrompt && !editing" type="primary" link @click="startEditing">
          {{ candidate.generationPrompt ? '编辑提示词' : '补充提示词' }}
        </el-button>
      </div>
    </template>
    <el-form v-if="editing" ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="AI 生成提示词（选填）" prop="generationPrompt">
        <el-input v-model="form.generationPrompt" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          :maxlength="10000" show-word-limit :disabled="busy" placeholder="补充生成该文件时使用的提示词" />
      </el-form-item>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <div class="candidate-generation-prompt__actions">
        <el-button :disabled="busy" @click="cancel">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存提示词</el-button>
      </div>
    </el-form>
    <p v-else class="candidate-generation-prompt__text">{{ candidate.generationPrompt || '该文件未填写 AI 生成提示词。' }}</p>
  </el-card>
</template>

<style scoped>
.candidate-generation-prompt__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.candidate-generation-prompt__actions { display: flex; justify-content: flex-end; margin-top: 12px; }
.candidate-generation-prompt__text {
  margin: 0;
  color: var(--sg-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
