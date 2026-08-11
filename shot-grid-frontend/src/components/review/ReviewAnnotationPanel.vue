<script setup>
import { reactive, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { createReviewDraft, guardVersionSwitch, prepareDraftSubmission } from './annotationDraft.js'

const props = defineProps({ versionId: { type: [String, Number], required: true } })
const emit = defineEmits(['submit', 'cancel', 'switch-blocked'])
const draft = reactive(createReviewDraft(props.versionId))

const reset = versionId => Object.assign(draft, createReviewDraft(versionId))
const cancel = () => { reset(props.versionId); emit('cancel') }
const submit = () => emit('submit', prepareDraftSubmission(draft, props.versionId))

watch(() => props.versionId, async next => {
  const guarded = await guardVersionSwitch(draft, next, () => ElMessageBox.confirm(
    '切换版本将丢弃尚未提交的批注，是否继续？', '未提交批注', { type: 'warning' }
  ).then(() => true, () => false))
  if (!guarded) return emit('switch-blocked', draft.versionId)
  Object.assign(draft, guarded)
})
</script>

<template>
  <section class="review-annotation-panel">
    <label for="review-note">审核意见（纯文本）</label>
    <el-input id="review-note" v-model="draft.content" type="textarea" :rows="4" maxlength="4000" show-word-limit />
    <div class="actions">
      <el-button @click="cancel">取消</el-button>
      <el-button type="primary" :disabled="!draft.content.trim()" @click="submit">明确提交</el-button>
    </div>
  </section>
</template>

<style scoped>
.review-annotation-panel { display: grid; gap: 12px; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>

