<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { createManualReviewList } from '@/api/shot-grid/reviews'
import { reviewErrorState } from '@/views/review/reviewPresentation'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [String, Number], required: true },
  candidates: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'created'])
const form = reactive({ reviewListName: '', description: '', reviewDate: '', versionIds: [] })
const formRef = ref(null)
const busy = ref(false)
const formRules = {
  reviewListName: [
    { required: true, whitespace: true, message: '请填写审核单名称', trigger: 'blur' },
    { max: 240, message: '审核单名称不能超过 240 个字符', trigger: 'blur' }
  ],
  description: [{ max: 1000, message: '说明不能超过 1000 个字符', trigger: 'blur' }],
  versionIds: [{ type: 'array', required: true, min: 1, message: '请至少选择一个待审核版本', trigger: 'change' }]
}
const dialogVisible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value)
})

watch(() => props.modelValue, async visible => {
  if (!visible) return
  Object.assign(form, { reviewListName: '', description: '', reviewDate: '', versionIds: [] })
  await nextTick()
  formRef.value?.clearValidate()
})

async function submit() {
  if (busy.value) return
  busy.value = true
  try {
    let valid = false
    await formRef.value?.validate(result => {
      valid = result
    })
    if (!valid) return
    const created = await createManualReviewList(props.projectId, {
      reviewListName: form.reviewListName.trim(),
      description: form.description.trim() || null,
      reviewDate: form.reviewDate || null,
      versionIds: form.versionIds
    })
    ElMessage.success('人工批量审核单已创建')
    dialogVisible.value = false
    emit('created', created.data)
  } catch (error) {
    ElMessage.error(reviewErrorState(error, '创建人工审核单失败').message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog v-model="dialogVisible" title="创建人工批量审核单" width="720px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="formRules" label-position="top" aria-label="创建人工批量审核单">
      <el-form-item label="审核单名称" prop="reviewListName"><el-input v-model="form.reviewListName" maxlength="240" show-word-limit placeholder="例如：EP01 本周镜头集中审核" /></el-form-item>
      <div class="dialog-grid"><el-form-item label="审核日期" prop="reviewDate"><el-date-picker v-model="form.reviewDate" type="date" value-format="YYYY-MM-DD" placeholder="选择审核日期" /></el-form-item><el-form-item label="说明" prop="description"><el-input v-model="form.description" maxlength="1000" placeholder="可选" /></el-form-item></div>
      <el-form-item label="选择待审核版本" prop="versionIds">
        <el-select v-model="form.versionIds" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择同项目待审核版本">
          <el-option v-for="item in candidates" :key="item.autoVersionId" :value="item.autoVersionId" :label="`${item.versionNumber} · ${item.reviewListName}`" />
        </el-select>
      </el-form-item>
      <p class="dialog-tip">创建后先保持草稿，可继续调整版本集合和顺序；激活后集合冻结。</p>
    </el-form>
    <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="busy" @click="submit">创建审核单</el-button></template>
  </el-dialog>
</template>

<style scoped>
.dialog-grid{display:grid;grid-template-columns:220px 1fr;gap:14px}.el-select,.el-date-editor{width:100%}.dialog-tip{margin:0;color:var(--sg-text-muted);font-size:11px}@media(max-width:650px){.dialog-grid{grid-template-columns:1fr}}
</style>
