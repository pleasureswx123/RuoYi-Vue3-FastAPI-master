<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { archiveReviewList, createReviewList, getReviewList, listEligibleReviewVersions, listReviewLists, reorderReviewList } from '@/api/shot-grid/reviews'
import { getErrorDetails } from '@/utils/requestErrors'

const props = defineProps({ projectId: { type: String, default: '' } })
const rows = ref([]), loading = ref(false), dialog = ref(false), eligible = ref([]), selected = ref([])
const form = ref({ reviewListName: '', description: '', reviewDate: '' })
const editing = ref(null)
let dragged = null
const validProject = () => /^\d+$/.test(props.projectId)
async function load() { if (!validProject()) return; loading.value = true; try { rows.value = (await listReviewLists(props.projectId)).rows } catch (e) { ElMessage.error(getErrorDetails(e).message) } finally { loading.value = false } }
async function openCreate() { editing.value = null; eligible.value = await listEligibleReviewVersions(props.projectId); selected.value = []; form.value = { reviewListName: '', description: '', reviewDate: '' }; dialog.value = true }
async function openOrder(row) { const detail = await getReviewList(props.projectId, row.reviewListId); editing.value = detail; selected.value = detail.versions; eligible.value = detail.versions; form.value = { reviewListName: detail.name, description: detail.description || '', reviewDate: detail.reviewDate || '' }; dialog.value = true }
function toggle(item) { const i = selected.value.findIndex(v => v.versionId === item.versionId); i < 0 ? selected.value.push(item) : selected.value.splice(i, 1) }
function drop(index) { if (dragged == null || dragged === index) return; const [item] = selected.value.splice(dragged, 1); selected.value.splice(index, 0, item); dragged = null }
const orderPayload = () => selected.value.map((item, sortOrder) => ({ versionId: item.versionId, sortOrder }))
async function create() { try { if (editing.value) await reorderReviewList(props.projectId, editing.value.reviewListId, { lockVersion: editing.value.lockVersion, versions: orderPayload() }); else await createReviewList(props.projectId, { ...form.value, reviewDate: form.value.reviewDate || null, versions: orderPayload() }); dialog.value = false; ElMessage.success(editing.value ? '顺序已按版本 ID 持久化' : '人工审核单已创建'); await load() } catch (e) { ElMessage.error(getErrorDetails(e).status === 409 ? '审核单已并发修改或版本状态已变化，请刷新。' : getErrorDetails(e).message) } }
async function archive(row) { try { await archiveReviewList(props.projectId, row.reviewListId, row.lockVersion); await load() } catch (e) { ElMessage.error(getErrorDetails(e).message) } }
onMounted(load)
</script>

<template><section class="page" v-loading="loading"><span class="eyebrow">REVIEWS</span><h1>审核单</h1>
  <el-alert v-if="!validProject()" title="请从项目内进入审核单，避免缺失项目权限上下文。" type="info" show-icon />
  <template v-else><div class="toolbar"><p class="lead">人工审核单按数据库顺序连续审核；自动单由版本正式提交事务创建。</p><el-button type="primary" @click="openCreate">创建人工审核单</el-button></div>
  <el-empty v-if="!rows.length" description="暂无审核单"/><el-card v-for="row in rows" :key="row.reviewListId" class="list-card"><div class="card-head"><div><h3>{{ row.name }}</h3><el-tag>{{ row.mode === 'auto_single' ? '自动单版本' : '人工批量' }}</el-tag> <el-tag>{{ row.status }}</el-tag></div><div><router-link :to="{ name:'ReviewWorkspace', params:{ projectId, reviewListId:row.reviewListId } }"><el-button type="primary" plain>连续审核</el-button></router-link><el-button v-if="row.mode === 'manual_batch'" @click="openOrder(row)">拖动排序</el-button><el-button @click="archive(row)">归档</el-button></div></div></el-card></template>
  <el-dialog v-model="dialog" :title="editing ? '编辑审核顺序' : '创建人工审核单'" width="720"><el-form v-if="!editing" label-position="top"><el-form-item label="名称"><el-input v-model="form.reviewListName" maxlength="240"/></el-form-item><el-form-item label="说明"><el-input v-model="form.description" type="textarea"/></el-form-item><el-form-item label="审核日期"><el-date-picker v-model="form.reviewDate" value-format="YYYY-MM-DD"/></el-form-item></el-form><template v-if="!editing"><h3>选择可审核版本</h3><div class="picker"><el-checkbox v-for="item in eligible" :key="item.versionId" :model-value="selected.some(v => v.versionId === item.versionId)" @change="toggle(item)">{{ item.taskName }} · V{{ item.versionNo }}</el-checkbox></div></template><h3>拖动排序</h3><ol class="order"><li v-for="(item,index) in selected" :key="item.versionId" draggable="true" @dragstart="dragged=index" @dragover.prevent @drop="drop(index)">☰ {{ item.taskName }} · V{{ item.versionNo }} <small>ID {{ item.versionId }}</small></li></ol><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :disabled="!form.reviewListName.trim() || !selected.length" @click="create">{{ editing ? '保存顺序' : '创建' }}</el-button></template></el-dialog>
</section></template>
<style scoped>.toolbar,.card-head{display:flex;justify-content:space-between;align-items:center;gap:16px}.list-card{margin:12px 0}.picker{display:grid;grid-template-columns:1fr 1fr;gap:8px;max-height:180px;overflow:auto}.order li{margin:8px 0;padding:10px;background:#f5f7fa;border:1px solid #dcdfe6;border-radius:6px;cursor:grab}.order small{float:right;color:#909399}</style>
