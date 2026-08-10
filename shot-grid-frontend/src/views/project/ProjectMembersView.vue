<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { addProjectMember, listProjectMembers, removeProjectMember, updateProjectMember } from '@/api/shot-grid/members'
import { useUserStore } from '@/store/modules/user'
import { domainErrorMessage } from '@/utils/projectDomain'
import ProjectDetailLayout from './ProjectDetailLayout.vue'

const props = defineProps({ projectId: { type: String, required: true } })
const userStore = useUserStore()
const members = ref([]), loading = ref(false), error = ref(''), dialogVisible = ref(false), saving = ref(false), editingUserId = ref(null)
const form = reactive({ userId: null, projectRole: 'creator', producerCode: '' })
let controller
const canAdd = computed(() => userStore.hasPermission('shotgrid:member:add'))
const canEdit = computed(() => userStore.hasPermission('shotgrid:member:edit'))
const canRemove = computed(() => userStore.hasPermission('shotgrid:member:remove'))
async function loadMembers() { controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''; try { const result = await listProjectMembers(props.projectId, { signal: controller.signal }); members.value = result?.rows || [] } catch (reason) { if (reason?.code !== 'ERR_CANCELED') error.value = domainErrorMessage(reason, '成员列表加载失败。') } finally { loading.value = false } }
function openAdd() { editingUserId.value = null; Object.assign(form, { userId: null, projectRole: 'creator', producerCode: '' }); dialogVisible.value = true }
function openEdit(member) { editingUserId.value = member.userId; Object.assign(form, { userId: member.userId, projectRole: member.projectRole, producerCode: member.producerCode || '' }); dialogVisible.value = true }
async function save() { if (saving.value || (!editingUserId.value && !form.userId)) return; saving.value = true; try { const payload = { projectRole: form.projectRole, producerCode: form.producerCode.trim().toUpperCase() || null }; if (editingUserId.value) await updateProjectMember(props.projectId, editingUserId.value, payload); else await addProjectMember(props.projectId, { userId: Number(form.userId), ...payload }); dialogVisible.value = false; ElMessage.success(editingUserId.value ? '成员已更新' : '成员已添加或恢复'); await loadMembers() } catch (reason) { error.value = domainErrorMessage(reason) } finally { saving.value = false } }
async function remove(member) { try { await ElMessageBox.confirm(`确定软移除 ${member.nickName}？成员可通过再次添加恢复。`, '移除成员', { type: 'warning' }); await removeProjectMember(props.projectId, member.userId); ElMessage.success('成员已移除'); await loadMembers() } catch (reason) { if (reason !== 'cancel' && reason !== 'close') error.value = domainErrorMessage(reason) } }
onBeforeUnmount(() => controller?.abort())
onMounted(loadMembers)
</script>
<template><ProjectDetailLayout :project-id="projectId"><section class="members-section"><header><div><h2>项目成员</h2><p>维护项目角色和项目内唯一的制作人缩写。</p></div><el-button v-if="canAdd" type="primary" @click="openAdd">添加 / 恢复成员</el-button></header><el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" /><el-table v-loading="loading" :data="members" empty-text="暂无项目成员"><el-table-column prop="nickName" label="成员"><template #default="{ row }"><strong>{{ row.nickName }}</strong><small class="member-account">{{ row.userName }} · ID {{ row.userId }}</small></template></el-table-column><el-table-column prop="deptName" label="部门" /><el-table-column label="项目角色"><template #default="{ row }"><el-tag :type="row.projectRole === 'director' ? 'success' : 'info'">{{ row.projectRole === 'director' ? '项目总监' : '制作人员' }}</el-tag></template></el-table-column><el-table-column prop="producerCode" label="制作人缩写"><template #default="{ row }">{{ row.producerCode || '—' }}</template></el-table-column><el-table-column label="操作" width="180"><template #default="{ row }"><el-button v-if="canEdit" link @click="openEdit(row)">调整</el-button><el-button v-if="canRemove" link type="danger" @click="remove(row)">软移除</el-button></template></el-table-column></el-table></section>
<el-dialog v-model="dialogVisible" :title="editingUserId ? '调整成员' : '添加或恢复成员'" width="480px"><el-form label-position="top"><el-form-item v-if="!editingUserId" label="平台用户 ID" required><el-input-number v-model="form.userId" :min="1" /></el-form-item><el-form-item label="项目角色" required><el-radio-group v-model="form.projectRole"><el-radio value="creator">制作人员</el-radio><el-radio value="director">项目总监</el-radio></el-radio-group></el-form-item><el-form-item label="制作人缩写"><el-input v-model="form.producerCode" maxlength="12" placeholder="2—12 位大写字母或数字" @input="form.producerCode = form.producerCode.toUpperCase().replace(/[^A-Z0-9]/g, '')" /></el-form-item></el-form><template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="saving" @click="save">保存</el-button></template></el-dialog></ProjectDetailLayout></template>
