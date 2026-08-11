<script setup>
import { computed, onMounted, ref } from 'vue'
import { getReviewList } from '@/api/shot-grid/reviews'
const props = defineProps({ projectId: { type: String, required: true }, reviewListId: { type: String, required: true } })
const detail = ref(null), loading = ref(true)
const ordered = computed(() => [...(detail.value?.versions || [])].sort((a,b) => a.sortOrder - b.sortOrder))
onMounted(async () => { try { detail.value = await getReviewList(props.projectId, props.reviewListId) } finally { loading.value = false } })
</script>
<template><section v-loading="loading"><template v-if="detail"><span class="eyebrow">CONTINUOUS REVIEW</span><h1>{{ detail.name }}</h1><p>以下顺序来自 <code>sg_review_list_version.sort_order</code>，刷新后保持一致。</p><ol><li v-for="item in ordered" :key="item.versionId"><router-link :to="{ name:'VersionReview', params:{versionId:item.versionId}, query:{projectId,taskId:item.taskId,reviewListId} }">{{ item.taskName }} · V{{ item.versionNo }} · {{ item.versionStatus }}</router-link></li></ol><router-link v-if="ordered[0]" :to="{ name:'VersionReview', params:{versionId:ordered[0].versionId}, query:{projectId,taskId:ordered[0].taskId,reviewListId} }"><el-button type="primary">从第一个版本开始</el-button></router-link></template></section></template>
