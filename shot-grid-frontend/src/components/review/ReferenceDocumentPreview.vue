<script setup>
import { computed, ref } from 'vue'
defineProps({ kind: { type: String, required: true }, content: { type: Object, required: true } })
const sheetIndex = ref(0)
const page = ref(1)
const pageIndex = computed(() => page.value - 1)
</script>

<template>
  <iframe v-if="kind === 'docx'" class="reference-document" :srcdoc="content.html" sandbox="" title="Word 文档预览" />
  <el-scrollbar v-else-if="kind === 'txt'" max-height="65vh"><pre class="reference-text">{{ content.text || '（空文本）' }}</pre></el-scrollbar>
  <section v-else-if="kind === 'xlsx'" class="reference-workbook">
    <el-select v-model="sheetIndex" aria-label="选择工作表">
      <el-option v-for="(sheet, index) in content.sheets" :key="index" :label="sheet.name" :value="index" />
    </el-select>
    <el-alert title="内容预览显示单元格文字和已保存的公式结果，不重新计算公式或展示图表。" type="info" :closable="false" />
    <template v-if="content.sheets[sheetIndex]">
      <el-alert v-if="content.sheets[sheetIndex].truncated" title="仅展示前 1000 行、100 列，完整内容请下载查看。" type="warning" :closable="false" />
      <el-table :data="content.sheets[sheetIndex].rows" row-key="rowNumber" height="55vh" border>
        <el-table-column prop="rowNumber" label="行" width="70" fixed />
        <el-table-column v-for="column in content.sheets[sheetIndex].columns" :key="column.key" :prop="column.key" :label="column.label" min-width="140" />
      </el-table>
    </template>
    <el-empty v-else description="暂无工作表" />
  </section>
  <section v-else-if="kind === 'pptx'" class="reference-slides">
    <el-alert title="幻灯片文字预览，不包含图片、图表、动画和原始版式；完整效果请下载查看。" type="info" :closable="false" />
    <el-scrollbar max-height="55vh"><pre class="reference-text">{{ content.pages[pageIndex] || '此页无可提取文字' }}</pre></el-scrollbar>
    <el-pagination v-model:current-page="page" :page-size="1" :total="content.pages.length" layout="prev, pager, next, total" />
  </section>
</template>

<style scoped>
.reference-document{width:100%;height:65vh;border:1px solid var(--sg-border);background:white}.reference-text{margin:0;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.8 var(--sg-font-family)}.reference-workbook,.reference-slides{display:grid;gap:12px;width:100%;min-width:0}
</style>
