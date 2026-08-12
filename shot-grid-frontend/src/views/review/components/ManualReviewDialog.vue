<script setup>
import { computed, reactive, ref, watch } from 'vue'
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
const busy = ref(false)
const dialogVisible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value)
})

watch(() => props.modelValue, visible => {
  if (visible) Object.assign(form, { reviewListName: '', description: '', reviewDate: '', versionIds: [] })
})

async function submit() {
  if (!form.reviewListName.trim()) return ElMessage.warning('请填写审核单名称')
  if (!form.versionIds.length) return ElMessage.warning('请至少选择一个待审核版本')
  busy.value = true
  try {
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
    <el-form label-position="top">
      <el-form-item label="审核单名称" required><el-input v-model="form.reviewListName" maxlength="240" show-word-limit placeholder="例如：EP01 本周镜头集中审核" /></el-form-item>
      <div class="dialog-grid"><el-form-item label="审核日期"><el-date-picker v-model="form.reviewDate" type="date" value-format="YYYY-MM-DD" placeholder="选择审核日期" /></el-form-item><el-form-item label="说明"><el-input v-model="form.description" maxlength="1000" placeholder="可选" /></el-form-item></div>
      <el-form-item label="选择待审核版本" required>
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
