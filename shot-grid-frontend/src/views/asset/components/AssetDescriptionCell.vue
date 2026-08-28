<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

const props = defineProps({
  commonDescription: { type: String, default: '' },
  itemDescription: { type: String, default: '' },
  isItem: { type: Boolean, default: false }
})
const cell = ref(null)
const preview = ref(null)
const expanded = ref(false)
const overflowing = ref(false)
const contentId = useId()
let observer

const parts = computed(() => {
  const common = String(props.commonDescription || '').trim()
  const item = String(props.itemDescription || '').trim()
  const result = common ? [{ label: props.isItem ? '共有说明' : '', text: common }] : []
  // 只在展示时去掉完全相同的重复内容，不推断共有说明，也不改写历史字段。
  if (props.isItem && item && item !== common) {
    result.push({ label: common ? '分项补充' : '分项说明', text: item })
  }
  return result
})

function measureOverflow() {
  if (expanded.value) return
  const element = preview.value?.$el
  overflowing.value = Boolean(element && element.scrollHeight > element.clientHeight + 1)
}

watch(parts, async () => {
  expanded.value = false
  await nextTick()
  measureOverflow()
})
watch(expanded, async () => {
  await nextTick()
  measureOverflow()
})
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measureOverflow)
    observer.observe(cell.value)
  }
  measureOverflow()
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="cell" class="asset-description">
    <el-text v-if="parts.length" :id="contentId" ref="preview" tag="p" class="asset-description-preview" :line-clamp="expanded ? undefined : 3">
      <template v-for="(part, index) in parts" :key="part.label">
        <br v-if="index" />
        <strong v-if="part.label" class="asset-description-label">{{ part.label }}：</strong>{{ part.text }}
      </template>
    </el-text>
    <el-text v-else type="info" size="small">{{ isItem ? '暂无分项说明' : '共有说明未填写' }}</el-text>
    <el-button v-if="overflowing || expanded" link type="primary" size="small" :aria-controls="contentId" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? '收起说明' : '展开说明' }}
    </el-button>
  </div>
</template>

<style scoped>
.asset-description { min-width: 0; }
.asset-description-preview { width: 100%; margin: 0; color: var(--sg-text-secondary); font-size: 12px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.asset-description-label { font-weight: 500; color: var(--sg-text-muted); }
.asset-description .el-button { margin-top: 4px; }
</style>
