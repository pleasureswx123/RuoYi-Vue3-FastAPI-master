<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ShotCards from '@/components/shot/ShotCards.vue'
import ShotStoryboard from '@/components/shot/ShotStoryboard.vue'
import ShotTable from '@/components/shot/ShotTable.vue'
import { useShotQueryStore } from '@/store/modules/shotQuery'

const props = defineProps({ projectId: { type: String, default: '' } })
const route = useRoute(), store = useShotQueryStore(), view = ref('table'), debounce = ref()
const project = () => props.projectId || String(route.query.projectId || '')
function search() { clearTimeout(debounce.value); debounce.value = setTimeout(store.fetch, 300) }
function page(pageNum) { store.patchQuery({ pageNum }); store.fetch() }
watch(project, (id) => { store.setProject(id); store.fetch() }, { immediate: true })
watch(() => [store.query.episodeId, store.query.sceneId, store.query.assigneeUserId, store.query.status, store.query.orderBy, store.query.orderDirection], () => { store.patchQuery({ pageNum: 1 }); store.fetch() })
onMounted(() => { if (project()) store.fetch() })
onBeforeUnmount(() => { clearTimeout(debounce.value); store.cancel() })
</script>
<template><section class="page domain-page"><header class="page-heading"><div><span class="eyebrow">SHOTS</span><h1>镜头管理</h1><p class="lead">三种视图共享同一份服务端查询结果和统计口径。</p><router-link v-if="project()" :to="`/projects/${project()}/asset-requirements`"><el-button type="primary" plain>待匹配需求</el-button></router-link></div><el-segmented v-model="view" :options="[{ label: '表格', value: 'table' }, { label: '卡片', value: 'cards' }, { label: '故事板', value: 'storyboard' }]" /></header>
<div class="filter-bar"><el-input v-model="store.query.keyword" clearable placeholder="搜索镜头号或制作内容" @input="search" /><el-input v-model="store.query.episodeId" placeholder="集 ID" /><el-input v-model="store.query.sceneId" placeholder="场次 ID" /><el-input v-model="store.query.assigneeUserId" placeholder="负责人 ID" /><el-select v-model="store.query.status" clearable placeholder="聚合状态"><el-option label="未开始" value="not_started"/><el-option label="制作中" value="in_progress"/><el-option label="待审核" value="pending_review"/><el-option label="已完成" value="completed"/></el-select><el-select v-model="store.query.orderBy"><el-option label="制作顺序" value="sortOrder"/><el-option label="最近更新" value="updateTime"/></el-select></div>
<div v-if="!project()" class="state-panel">请先选择项目。</div><div v-else-if="store.forbidden" class="state-panel state-panel--error">无权限访问当前项目镜头。</div><div v-else-if="store.error" class="state-panel state-panel--error">{{ store.error }} <el-button @click="store.fetch">重试</el-button></div><div v-else v-loading="store.loading" class="shot-results"><template v-if="store.rows.length"><ShotTable v-if="view === 'table'" :rows="store.rows"/><ShotCards v-else-if="view === 'cards'" :rows="store.rows"/><ShotStoryboard v-else :rows="store.rows"/><el-pagination :current-page="store.query.pageNum" :page-size="store.query.pageSize" :total="store.total" layout="total, prev, pager, next" @current-change="page" /></template><div v-else-if="!store.loading" class="state-panel">当前条件下暂无镜头。</div></div></section></template>
