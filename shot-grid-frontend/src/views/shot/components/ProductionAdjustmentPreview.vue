<script setup>
import { computed, ref } from 'vue'
import { ElCollapse, ElCollapseItem } from 'element-plus'
import 'element-plus/es/components/collapse/style/css'
import 'element-plus/es/components/collapse-item/style/css'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'

const props = defineProps({
  shots: { type: Array, required: true },
  common: Boolean,
  addedFiles: { type: Array, default: () => [] },
  addedDescription: { type: String, default: '' }
})
const expanded = ref(props.shots.length === 1 ? [props.shots[0].key] : [])
const showUnchanged = ref(false)
const fields = computed(() => props.shots[0]?.fields || [])
const hasReferences = computed(() => fields.value.some(field => field.isReference))
const changedCount = shot => shot.fields.filter(field => field.changed).length
</script>

<template>
  <section class="adjust-review" aria-label="核对镜头修改">
    <el-card v-if="shots.length > 1" shadow="never" class="review-summary">
      <p class="review-summary-title">{{ common ? '统一修改' : '逐镜头修改' }} {{ shots.length }} 个镜头</p>
      <el-descriptions v-if="common && shots.length > 1" class="review-common-values" :column="1" border size="small">
        <el-descriptions-item v-for="field in fields.filter(item => !item.isReference)" :key="field.key" :label="field.label"><span class="review-value">{{ field.after === '（清空）' ? '将清空' : field.after }}</span></el-descriptions-item>
      </el-descriptions>
      <section v-if="hasReferences" class="review-additions">
        <strong>本次追加参考内容</strong>
        <p class="review-hint">追加至 {{ shots.length }} 个镜头，保留已有资料。</p>
        <p v-if="addedDescription" class="review-value">{{ addedDescription }}</p>
        <ReviewReferenceInput v-if="addedFiles.length" :files="addedFiles" readonly purpose="调整" />
      </section>
    </el-card>
    <div class="review-toolbar">
      <el-checkbox v-model="showUnchanged">显示未变化字段</el-checkbox>
      <div v-if="shots.length > 1"><el-button text @click="expanded = shots.map(shot => shot.key)">全部展开</el-button><el-button text @click="expanded = []">全部收起</el-button></div>
    </div>
    <el-collapse v-model="expanded" class="review-shots">
      <el-collapse-item v-for="shot in shots" :key="shot.key" :name="shot.key" :disabled="shots.length === 1">
        <template #title><div class="review-shot-title"><strong>{{ shot.label }}</strong><el-tag :type="changedCount(shot) ? 'warning' : 'info'" size="small" effect="plain">{{ changedCount(shot) ? `${changedCount(shot)} 项变更` : '无实际变化' }}</el-tag></div></template>
        <p v-if="!changedCount(shot) && !showUnchanged" class="review-hint">所选字段与当前内容相同。</p>
        <section v-for="field in shot.fields.filter(item => item.changed || showUnchanged)" :key="field.key" class="review-field">
          <div class="review-field-title"><strong>{{ field.label }}</strong><el-tag v-if="!field.changed" type="info" size="small">未变化</el-tag></div>
          <el-descriptions v-if="field.isReference" :column="2" direction="vertical" border size="small">
            <el-descriptions-item label="修改前">
              <p v-if="field.beforeDescription" class="review-value">{{ field.beforeDescription }}</p>
              <ReviewReferenceInput v-if="field.beforeFiles.length" :files="field.beforeFiles" readonly purpose="调整" />
              <p v-if="!field.beforeDescription && !field.beforeFiles.length" class="review-hint">暂无参考内容</p>
            </el-descriptions-item>
            <el-descriptions-item label="修改后">
              <div class="review-new">
                <p v-if="field.beforeDescription || addedDescription" class="review-value">{{ [field.beforeDescription, addedDescription].filter(Boolean).join('\n\n') }}</p>
                <ReviewReferenceInput v-if="field.beforeFiles.length || addedFiles.length" :files="[...field.beforeFiles, ...addedFiles]" readonly purpose="调整" />
                <p v-if="!field.beforeDescription && !addedDescription && !field.beforeFiles.length && !addedFiles.length" class="review-hint">暂无参考内容</p>
              </div>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions v-else :column="2" border size="small">
            <el-descriptions-item label="修改前"><span class="review-value">{{ field.before === '（清空）' ? '未填写' : field.before }}</span></el-descriptions-item>
            <el-descriptions-item label="修改后"><span class="review-value" :class="{ 'review-new': field.changed }">{{ field.after === '（清空）' ? '将清空' : field.after }}</span></el-descriptions-item>
          </el-descriptions>
        </section>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<style scoped>
.adjust-review{display:grid;gap:16px;font-size:12px}
.review-summary{--el-card-padding:16px;border-radius:8px}
.review-hint{color:var(--sg-text-muted);font-size:12px;line-height:1.6;margin:8px 0}
.review-tags,.review-toolbar,.review-shot-title,.review-field-title{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.review-summary-title{margin:0 0 12px;font-weight:600}
.review-toolbar{justify-content:space-between}
.review-shot-title{padding:12px 0}
.review-shots :deep(.el-collapse-item){border:1px solid var(--sg-border);border-radius:8px;padding:0 16px;margin-bottom:12px}
.review-shots :deep(.el-collapse-item__header){height:auto;min-height:52px;color:var(--sg-text);line-height:1.5}
.review-shots :deep(.el-collapse-item__content){padding-bottom:16px}
.review-shots :deep(.el-collapse-item.is-active){border-color:var(--sg-accent);background:var(--sg-accent-soft)}
.review-shots :deep(.el-collapse-item.is-active .el-collapse-item__wrap),.review-shots :deep(.el-collapse-item.is-active .el-collapse-item__content){background:transparent}
.review-shots :deep(.el-collapse-item.is-active .el-collapse-item__header){background:transparent;padding:0 12px;margin:0 -16px;border-radius:7px 7px 0 0}
@media(max-width:600px){.review-shots :deep(.el-collapse-item.is-active .el-collapse-item__header){margin:0 -10px}}
.review-field{padding:12px 0;border-top:1px solid var(--sg-border)}
.review-field-title{margin-bottom:10px}
.review-value{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}
.review-new{display:block;background:var(--sg-surface-soft);padding:8px;border-radius:4px}
.review-additions{margin-top:16px}
.adjust-review :deep(.el-descriptions__table){table-layout:fixed}
.adjust-review :deep(.el-descriptions__label){width:76px}
@media(max-width:600px){.adjust-review :deep(.el-descriptions__label){width:60px}.review-shots :deep(.el-collapse-item){padding:0 10px}}
.adjust-review .review-common-values :deep(.el-descriptions__label){width:128px;white-space:nowrap}
</style>
